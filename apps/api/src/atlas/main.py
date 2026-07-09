import asyncio
import contextlib

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from atlas import ws
from atlas.routers import settings, tasks


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    listener = asyncio.create_task(ws.escuchar_postgres())
    yield
    listener.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await listener


app = FastAPI(title="Atlas API", version="0.5.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    # cualquier puerto de localhost (la .app corre en :3005, dev en otros); todo es local
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(tasks.router)
app.include_router(settings.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket(sock: WebSocket):
    await ws.manager.connect(sock)
    try:
        while True:
            await sock.receive_text()  # keepalive del cliente
    except WebSocketDisconnect:
        ws.manager.disconnect(sock)
