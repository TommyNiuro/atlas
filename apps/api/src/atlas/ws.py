"""WebSocket push: el orchestrator hace NOTIFY atlas_tasks en Postgres y la
API lo retransmite a los dashboards conectados (sin recargar)."""
import asyncio
import contextlib
import json
import logging

from fastapi import WebSocket

from atlas.core.config import DATABASE_URL

log = logging.getLogger("atlas.ws")


class Manager:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    async def broadcast(self, payload: dict) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_text(json.dumps(payload))
            except Exception:  # noqa: BLE001 - cliente muerto, fuera
                self.disconnect(ws)


manager = Manager()


async def escuchar_postgres() -> None:
    """LISTEN atlas_tasks -> broadcast. Reintenta si la conexion cae."""
    import asyncpg

    dsn = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    loop = asyncio.get_running_loop()
    while True:
        conn = None
        try:
            conn = await asyncpg.connect(dsn)

            def on_notify(_conn, _pid, _channel, payload):
                loop.create_task(
                    manager.broadcast({"type": "tasks_changed", "detail": payload})
                )

            await conn.add_listener("atlas_tasks", on_notify)
            while not conn.is_closed():
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            if conn:
                with contextlib.suppress(Exception):
                    await conn.close()
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("listener de postgres caido, reintento en 5s: %s", e)
            if conn:
                with contextlib.suppress(Exception):
                    await conn.close()
            await asyncio.sleep(5)
