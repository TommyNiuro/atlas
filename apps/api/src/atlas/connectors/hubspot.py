"""Conector HubSpot via la CRM Search API v3.

Auth: un Private App token (pat-...) que Tomas genera en HubSpot
(Settings > Integrations > Private Apps) y pega en HUBSPOT_TOKEN. Se cifra en
SOURCE.auth_meta como el resto. Camino headless estable, apto para launchd.

Sync: pull incremental por hs_lastmodifieddate (el mas alto visto, en epoch ms,
se guarda en SOURCE.sync_cursor y se reusa como filtro GTE). Trae engagements
(notes, tasks, calls, emails, meetings) y deals, y los normaliza a crm_activity.
El texto de cada engagement es la senal para extraer tareas; el deal aporta
estado de pipeline.

Regla del handoff: deals_sin_actividad() es una query SQL sobre raw_item que
marca deals abiertos sin actividad reciente. v1 opera sobre los deals ya
sincronizados; para cubrir deals viejos que nunca se tocaron, el primer sync
usa una ventana amplia. Deferido: snapshot completo de deals con upsert-on-change.

Scopes del Private App (lectura): crm.objects.deals.read,
crm.objects.contacts.read, sales-email-read, y los de engagements
(crm.objects.* segun tu portal). Ver la tarea auth-hubspot.
"""
import asyncio
import re
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import text as _sql

from atlas.core import config
from atlas.core.config import DEFAULT_USER_ID
from atlas.connectors.base import ConnectorHealth, NewRawItem, register

HUBSPOT_API = "https://api.hubapi.com/crm/v3/objects"
VENTANA_INICIAL_DIAS = 30  # primer sync: ultimo mes (deals viven mas que un mail)
PAGE_SIZE = 100
_TAGS = re.compile(r"<[^>]+>")


def _strip_html(s: str | None) -> str:
    return _TAGS.sub(" ", s or "").strip()


# objeto -> (propiedades a pedir, funcion que arma el texto plano)
OBJETOS: dict[str, tuple[list[str], object]] = {
    "notes": (
        ["hs_note_body", "hs_lastmodifieddate"],
        lambda p: _strip_html(p.get("hs_note_body")),
    ),
    "tasks": (
        ["hs_task_subject", "hs_task_body", "hs_task_status", "hs_lastmodifieddate"],
        lambda p: f"{p.get('hs_task_subject', '')}\n{_strip_html(p.get('hs_task_body'))}".strip(),
    ),
    "calls": (
        ["hs_call_title", "hs_call_body", "hs_lastmodifieddate"],
        lambda p: f"{p.get('hs_call_title', '')}\n{_strip_html(p.get('hs_call_body'))}".strip(),
    ),
    "emails": (
        ["hs_email_subject", "hs_email_text", "hs_lastmodifieddate"],
        lambda p: f"{p.get('hs_email_subject', '')}\n{_strip_html(p.get('hs_email_text'))}".strip(),
    ),
    "meetings": (
        ["hs_meeting_title", "hs_meeting_body", "hs_lastmodifieddate"],
        lambda p: f"{p.get('hs_meeting_title', '')}\n{_strip_html(p.get('hs_meeting_body'))}".strip(),
    ),
    "deals": (
        ["dealname", "amount", "dealstage", "pipeline", "closedate", "hs_is_closed",
         "hs_last_sales_activity_timestamp", "hs_lastmodifieddate"],
        lambda p: f"{p.get('dealname', '')} ({p.get('dealstage', '')})".strip(),
    ),
}


def _ms(iso: str) -> int:
    """ISO-8601 (con Z o +00:00) a epoch en milisegundos, que es lo que
    espera el filtro de fecha de la Search API."""
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def es_ruido(obj: str, texto: str) -> bool:
    """Los deals nunca son ruido (aportan estado). Un engagement sin texto no
    tiene senal para extraer tareas."""
    if obj == "deals":
        return False
    return not texto.strip()


async def _search(
    client: httpx.AsyncClient, obj: str, token: str, body: dict, intentos: int = 3
) -> dict:
    """POST al search de un objeto con reintentos: respeta Retry-After en 429
    (limite: 5 req/s) y backoff en 5xx."""
    for i in range(intentos):
        r = await client.post(
            f"{HUBSPOT_API}/{obj}/search",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
        )
        if r.status_code == 429 and i < intentos - 1:
            await asyncio.sleep(int(r.headers.get("Retry-After", 2 ** i)))
            continue
        if r.status_code >= 500 and i < intentos - 1:
            await asyncio.sleep(2 ** i)
            continue
        r.raise_for_status()
        return r.json()
    return {}


@register
class HubSpotConnector:
    kind = "hubspot"

    def __init__(self, auth_meta: dict | None = None):
        self.auth_meta = auth_meta or {}

    def _token(self) -> str:
        token = self.auth_meta.get("token") or config.HUBSPOT_TOKEN
        if not token:
            raise RuntimeError("Falta el token de HubSpot: corre `task auth-hubspot`")
        return token

    async def _pull_objeto(
        self, client: httpx.AsyncClient, obj: str, token: str, desde_ms: int
    ) -> list[dict]:
        """Pagina el search de un objeto filtrando por hs_lastmodifieddate GTE
        desde_ms, ordenado ascendente (incremental estable)."""
        props, _ = OBJETOS[obj]
        out: list[dict] = []
        after: str | None = None
        while True:
            body = {
                "filterGroups": [{"filters": [
                    {"propertyName": "hs_lastmodifieddate", "operator": "GTE", "value": str(desde_ms)}
                ]}],
                "sorts": [{"propertyName": "hs_lastmodifieddate", "direction": "ASCENDING"}],
                "properties": props,
                "limit": PAGE_SIZE,
            }
            if after:
                body["after"] = after
            try:
                data = await _search(client, obj, token, body)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 403:  # scope faltante para este objeto: se salta, no aborta el sync
                    return out
                raise
            out.extend(data.get("results", []))
            after = ((data.get("paging") or {}).get("next") or {}).get("after")
            if not after:
                return out

    async def authenticate(self) -> dict:
        token = config.HUBSPOT_TOKEN
        if not token:
            raise RuntimeError(
                "Pon HUBSPOT_TOKEN en .env (Private App token pat-..., de HubSpot: "
                "Settings > Integrations > Private Apps > Create a private app)"
            )
        async with httpx.AsyncClient(timeout=15) as client:
            # valida el token con un search minimo: 200 = ok, 401 = token invalido
            await _search(client, "deals", token, {"limit": 1})
        print("hubspot: token valido")
        return {"token": token}

    async def pull_incremental(self, cursor: str | None) -> tuple[list[NewRawItem], str | None]:
        token = self._token()
        desde_ms = int(cursor) if cursor else int(
            (datetime.now(timezone.utc) - timedelta(days=VENTANA_INICIAL_DIAS)).timestamp() * 1000
        )
        max_ms = desde_ms
        items: list[NewRawItem] = []
        async with httpx.AsyncClient(timeout=60) as client:
            for obj, (_, hacer_texto) in OBJETOS.items():
                for rec in await self._pull_objeto(client, obj, token, desde_ms):
                    props = rec.get("properties") or {}
                    lm = props.get("hs_lastmodifieddate") or rec.get("updatedAt")
                    if lm:
                        max_ms = max(max_ms, _ms(lm))  # avanza aun sobre ruido: no re-pull
                    texto = hacer_texto(props)
                    if es_ruido(obj, texto):
                        continue
                    creado = rec.get("createdAt") or lm
                    items.append(
                        NewRawItem(
                            external_id=f"{obj}:{rec['id']}",
                            kind="crm_activity",
                            payload={"_object": obj, "id": rec["id"], "properties": props,
                                     "createdAt": rec.get("createdAt"), "updatedAt": rec.get("updatedAt")},
                            occurred_at=datetime.fromisoformat(creado.replace("Z", "+00:00")),
                            text=texto or props.get("dealname", ""),
                        )
                    )
        return items, str(max_ms)

    async def health(self) -> ConnectorHealth:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                await _search(client, "deals", self._token(), {"limit": 1})
            return ConnectorHealth(ok=True)
        except Exception as e:  # noqa: BLE001 - health nunca revienta
            return ConnectorHealth(ok=False, detail=str(e))


# --- Regla del handoff: deals sin actividad (query SQL, cero LLM) -------------

_DEALS_SIN_ACTIVIDAD = _sql(
    """
    SELECT payload->>'id'                                              AS deal_id,
           payload->'properties'->>'dealname'                          AS dealname,
           payload->'properties'->>'dealstage'                         AS dealstage,
           payload->'properties'->>'amount'                            AS amount,
           payload->'properties'->>'hs_last_sales_activity_timestamp'  AS ultima_actividad
    FROM raw_item
    WHERE user_id = :uid
      AND kind = 'crm_activity'
      AND payload->>'_object' = 'deals'
      AND COALESCE(payload->'properties'->>'hs_is_closed', 'false') = 'false'
      AND (
            payload->'properties'->>'hs_last_sales_activity_timestamp' IS NULL
            OR (payload->'properties'->>'hs_last_sales_activity_timestamp')::timestamptz
               < now() - make_interval(days => :dias)
      )
    ORDER BY ultima_actividad ASC NULLS FIRST
    """
)


async def deals_sin_actividad(session, dias: int = 14, user_id=DEFAULT_USER_ID) -> list[dict]:
    """Deals abiertos (hs_is_closed=false) sin actividad de ventas en los ultimos
    `dias` (o sin ninguna). Regla determinista en SQL sobre los deals ya
    sincronizados en raw_item. Devuelve filas listas para armar un seguimiento."""
    rows = (await session.execute(_DEALS_SIN_ACTIVIDAD, {"uid": user_id, "dias": dias})).mappings().all()
    return [dict(r) for r in rows]

