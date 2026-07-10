"""Conector Granola via su API publica oficial.

Auth: una API key (grn_...) que Tomas genera en el app de Granola
(Settings > Connectors > API keys) y pega en GRANOLA_API_KEY. Se cifra en
SOURCE.auth_meta como el resto. Es el camino headless estable: sin keychain,
sin fingerprinting, apta para el launchd de Atlas.

Sync: lista /v1/notes de forma incremental por created_at (el created_at mas
alto visto se guarda en SOURCE.sync_cursor y se reusa como `created_after`).
Por cada nota trae su detalle (/v1/notes/{id}) para quedarse con el resumen,
que es la senal real para extraer tareas. El transcript NO se pide (mucho ruido
y peso; el resumen ya destila los acuerdos).

Scopes de la key: "Personal notes" alcanza (tus notas y las compartidas
contigo). "Public notes" suma las del Team space si lo quieres mas adelante.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from atlas.core import config
from atlas.connectors.base import ConnectorHealth, NewRawItem, register

GRANOLA_API = "https://public-api.granola.ai/v1"
VENTANA_INICIAL_DIAS = 7  # primer sync: ultima semana, no toda la historia
PAGE_SIZE = 30  # maximo que permite la API


def _iso(dt: datetime) -> str:
    """ISO-8601 UTC con sufijo Z, que es lo que espera created_after."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(s: str) -> datetime:
    """created_at/updated_at vienen como '2026-01-27T15:30:00Z'."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


async def _granola_get(
    client: httpx.AsyncClient, path: str, token: str, params: dict | None = None, intentos: int = 3
) -> dict | None:
    """GET a la API con reintentos: respeta Retry-After en 429 (limite: 5 req/s,
    burst 25) y hace backoff en 5xx. Un 404 (nota sin resumen aun) devuelve None
    para saltarla sin abortar el sync."""
    for i in range(intentos):
        r = await client.get(
            f"{GRANOLA_API}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params or {},
        )
        if r.status_code == 429 and i < intentos - 1:
            await asyncio.sleep(int(r.headers.get("Retry-After", 2 ** i)))
            continue
        if r.status_code >= 500 and i < intentos - 1:
            await asyncio.sleep(2 ** i)
            continue
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    return None


def es_ruido(nota: dict) -> bool:
    """Filtro barato: una nota sin resumen no tiene senal para extraer tareas.
    La API ya excluye notas sin summary+transcript, esto es defensa extra."""
    resumen = (nota.get("summary_markdown") or nota.get("summary_text") or "").strip()
    return not resumen


@register
class GranolaConnector:
    kind = "granola"

    def __init__(self, auth_meta: dict | None = None):
        self.auth_meta = auth_meta or {}

    def _token(self) -> str:
        token = self.auth_meta.get("token") or config.GRANOLA_API_KEY
        if not token:
            raise RuntimeError("Falta la API key de Granola: corre `task auth-granola`")
        return token

    async def _listar(self, client: httpx.AsyncClient, token: str, created_after: str) -> list[dict]:
        """Sigue el cursor de paginacion y concatena todas las NoteSummary
        creadas despues de `created_after`."""
        out: list[dict] = []
        cursor: str | None = None
        while True:
            params = {"created_after": created_after, "page_size": PAGE_SIZE}
            if cursor:
                params["cursor"] = cursor
            data = await _granola_get(client, "/notes", token, params)
            if not data:
                return out
            out.extend(data.get("notes", []))
            if not data.get("hasMore"):
                return out
            cursor = data.get("cursor")
            if not cursor:
                return out

    async def authenticate(self) -> dict:
        token = config.GRANOLA_API_KEY
        if not token:
            raise RuntimeError(
                "Pon GRANOLA_API_KEY en .env (API key grn_..., del app de Granola: "
                "Settings > Connectors > API keys > Create new key)"
            )
        async with httpx.AsyncClient(timeout=15) as client:
            # valida la key con un listado minimo: 200 = ok, 401 = key invalida
            await _granola_get(client, "/notes", token, {"page_size": 1})
        print("granola: API key valida")
        return {"token": token}

    async def pull_incremental(self, cursor: str | None) -> tuple[list[NewRawItem], str | None]:
        token = self._token()
        desde = cursor or _iso(datetime.now(timezone.utc) - timedelta(days=VENTANA_INICIAL_DIAS))
        max_created = _parse(cursor) if cursor else None
        items: list[NewRawItem] = []
        async with httpx.AsyncClient(timeout=60) as client:
            for resumen in await self._listar(client, token, desde):
                creada = _parse(resumen["created_at"])
                if max_created is None or creada > max_created:  # avanza aun sobre notas filtradas
                    max_created = creada
                nota = await _granola_get(client, f"/notes/{resumen['id']}", token)
                if not nota or es_ruido(nota):
                    continue
                nota.pop("transcript", None)  # no lo pedimos; si viniera, fuera (peso)
                titulo = nota.get("title") or "(sin titulo)"
                resumen_txt = nota.get("summary_markdown") or nota.get("summary_text") or ""
                cal = nota.get("calendar_event") or {}
                inicio = cal.get("scheduled_start_time")
                items.append(
                    NewRawItem(
                        external_id=nota["id"],
                        kind="meeting_note",
                        payload=nota,
                        occurred_at=_parse(inicio) if inicio else creada,
                        text=f"{titulo}\n\n{resumen_txt}",
                    )
                )
        return items, (_iso(max_created) if max_created else cursor)

    async def health(self) -> ConnectorHealth:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                await _granola_get(client, "/notes", self._token(), {"page_size": 1})
            return ConnectorHealth(ok=True)
        except Exception as e:  # noqa: BLE001 - health nunca revienta
            return ConnectorHealth(ok=False, detail=str(e))
