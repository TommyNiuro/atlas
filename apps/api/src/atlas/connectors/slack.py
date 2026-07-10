"""Conector Slack via Web API.

Auth: un user token (xoxp-...) que Tomas pega en SLACK_TOKEN. Se cifra en
SOURCE.auth_meta como el resto. Sync: lee DMs, group DMs y los canales de
config/channels.yaml con conversations.history, incremental por ts (el ts
mas alto visto se guarda en SOURCE.sync_cursor y se reusa como `oldest`).

Necesita un USER token (no bot): los bots no ven los DMs de una persona.
Scopes: im:read im:history mpim:read mpim:history channels:read channels:history
groups:read groups:history.
"""
import asyncio
from datetime import datetime, timezone

import httpx
import yaml

from atlas.core import config
from atlas.connectors.base import ConnectorHealth, NewRawItem, register

SLACK_API = "https://slack.com/api"
VENTANA_INICIAL_DIAS = 7  # primer sync: ultima semana, no toda la historia

# subtipos de sistema (joins, cambios de topic, mensajes de bot): cero senal de tarea
SUBTYPES_RUIDO = {
    "channel_join", "channel_leave", "channel_topic", "channel_purpose",
    "channel_name", "channel_archive", "channel_unarchive",
    "bot_message", "pinned_item", "unpinned_item",
}


async def _slack_call(client: httpx.AsyncClient, method: str, token: str, params: dict, intentos: int = 3) -> dict:
    """GET a la Web API con reintentos: respeta Retry-After en 429 y el
    error ratelimited de Slack, para que un rate-limit no aborte el sync."""
    for i in range(intentos):
        r = await client.get(
            f"{SLACK_API}/{method}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        if r.status_code == 429 and i < intentos - 1:
            await asyncio.sleep(int(r.headers.get("Retry-After", 2 ** i)))
            continue
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            err = data.get("error", "desconocido")
            if err == "ratelimited" and i < intentos - 1:
                await asyncio.sleep(2 ** i)
                continue
            raise RuntimeError(f"Slack {method}: {err}")
        return data
    return {}


async def _paginate(client: httpx.AsyncClient, method: str, token: str, params: dict, key: str) -> list[dict]:
    """Sigue response_metadata.next_cursor y concatena data[key]."""
    out: list[dict] = []
    cursor = ""
    while True:
        p = {**params, "limit": 200}
        if cursor:
            p["cursor"] = cursor
        data = await _slack_call(client, method, token, p)
        out.extend(data.get(key, []))
        cursor = (data.get("response_metadata") or {}).get("next_cursor") or ""
        if not cursor:
            return out


def es_ruido(msg: dict, yo: str | None) -> bool:
    """Filtro barato: mensajes de sistema/bot, los mios (no son pedidos
    entrantes) y los vacios no gastan nada en el pipeline."""
    if msg.get("subtype") in SUBTYPES_RUIDO or msg.get("bot_id"):
        return True
    if yo and msg.get("user") == yo:  # ponytail: mis propios mensajes no me asignan tareas
        return True
    return not (msg.get("text") or "").strip()


def _canales_configurados() -> set[str]:
    path = config.REPO_ROOT / "config" / "channels.yaml"
    if not path.exists():
        return set()
    data = yaml.safe_load(path.read_text()) or {}
    return {c.lstrip("#") for c in (data.get("channels") or [])}


@register
class SlackConnector:
    kind = "slack"

    def __init__(self, auth_meta: dict | None = None):
        self.auth_meta = auth_meta or {}

    def _token(self) -> str:
        token = self.auth_meta.get("token") or config.SLACK_TOKEN
        if not token:
            raise RuntimeError("Falta el token de Slack: corre `task auth-slack`")
        return token

    async def _conversaciones(self, client: httpx.AsyncClient, token: str) -> list[tuple[str, str]]:
        # DMs y group DMs: siempre. Ahi es donde te piden cosas directo.
        ims = await _paginate(
            client, "conversations.list", token,
            {"types": "im,mpim", "exclude_archived": "true"}, "channels",
        )
        convs = [(c["id"], c.get("user") or c.get("name") or c["id"]) for c in ims]
        nombres = _canales_configurados()
        if nombres:
            chans = await _paginate(
                client, "conversations.list", token,
                {"types": "public_channel,private_channel", "exclude_archived": "true"}, "channels",
            )
            convs += [(c["id"], c["name"]) for c in chans if c.get("name") in nombres]
        return convs

    async def authenticate(self) -> dict:
        token = config.SLACK_TOKEN
        if not token:
            raise RuntimeError(
                "Pon SLACK_TOKEN en .env (user token xoxp-... con scopes im/mpim/channels history+read)"
            )
        async with httpx.AsyncClient(timeout=15) as client:
            data = await _slack_call(client, "auth.test", token, {})
        print(f"slack: autenticado como {data.get('user')} en {data.get('team')}")
        return {"token": token}

    async def pull_incremental(self, cursor: str | None) -> tuple[list[NewRawItem], str | None]:
        token = self._token()
        oldest = cursor or f"{datetime.now(timezone.utc).timestamp() - VENTANA_INICIAL_DIAS * 86400:.6f}"
        max_ts = float(cursor) if cursor else 0.0
        items: list[NewRawItem] = []
        async with httpx.AsyncClient(timeout=60) as client:
            yo = (await _slack_call(client, "auth.test", token, {})).get("user_id")
            for cid, cname in await self._conversaciones(client, token):
                msgs = await _paginate(
                    client, "conversations.history", token,
                    {"channel": cid, "oldest": oldest}, "messages",
                )
                for m in msgs:
                    ts = m["ts"]
                    max_ts = max(max_ts, float(ts))  # avanza el cursor aun sobre ruido: no re-pull
                    if es_ruido(m, yo):
                        continue
                    items.append(
                        NewRawItem(
                            external_id=f"{cid}:{ts}",
                            kind="message",
                            payload={**m, "_channel_id": cid, "_channel_name": cname},
                            occurred_at=datetime.fromtimestamp(float(ts), tz=timezone.utc),
                            text=m.get("text", ""),
                        )
                    )
        return items, (f"{max_ts:.6f}" if max_ts else cursor)

    async def health(self) -> ConnectorHealth:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                await _slack_call(client, "auth.test", self._token(), {})
            return ConnectorHealth(ok=True)
        except Exception as e:  # noqa: BLE001 - health nunca revienta
            return ConnectorHealth(ok=False, detail=str(e))
