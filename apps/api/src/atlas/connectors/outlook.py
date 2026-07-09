"""Conector Outlook Mail via Microsoft Graph.

Auth: device code flow de MSAL (cliente publico, sin secreto). El token cache
serializado viaja cifrado en SOURCE.auth_meta. Sync: delta queries de Graph,
el deltaLink se guarda en SOURCE.sync_cursor.
"""
from datetime import datetime

import httpx
import msal

from atlas.core import config
from atlas.connectors.base import ConnectorHealth, NewRawItem, register

GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = ["Mail.Read"]
DELTA_INICIAL = (
    f"{GRAPH}/me/mailFolders/inbox/messages/delta"
    "?$select=subject,from,receivedDateTime,bodyPreview,webLink,internetMessageHeaders"
)

REMITENTES_RUIDO = ("no-reply", "noreply", "notifications", "mailer-daemon", "newsletter")


def es_ruido(msg: dict) -> bool:
    """Filtro barato previo: newsletters y notificaciones no gastan nada."""
    sender = (msg.get("from", {}).get("emailAddress", {}).get("address") or "").lower()
    if any(p in sender for p in REMITENTES_RUIDO):
        return True
    for h in msg.get("internetMessageHeaders") or []:
        name = h.get("name", "").lower()
        if name == "list-unsubscribe":
            return True
        if name == "auto-submitted" and h.get("value", "").lower() != "no":
            return True
    return False


@register
class OutlookMailConnector:
    kind = "outlook_mail"

    def __init__(self, auth_meta: dict | None = None):
        self.auth_meta = auth_meta or {}

    def _msal_app(self, cache: msal.SerializableTokenCache) -> msal.PublicClientApplication:
        if not config.MS_CLIENT_ID:
            raise RuntimeError("Falta MS_CLIENT_ID en .env (app registrada en Entra ID)")
        return msal.PublicClientApplication(
            config.MS_CLIENT_ID,
            authority=f"https://login.microsoftonline.com/{config.MS_TENANT_ID}",
            token_cache=cache,
        )

    async def authenticate(self) -> dict:
        cache = msal.SerializableTokenCache()
        app = self._msal_app(cache)
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"Device flow fallo: {flow}")
        print(f"\n{flow['message']}\n")  # imprime el codigo para pegar en el navegador
        result = app.acquire_token_by_device_flow(flow)  # bloquea hasta autorizar
        if "access_token" not in result:
            raise RuntimeError(f"Auth fallo: {result.get('error_description')}")
        return {"token_cache": cache.serialize()}

    def get_access_token(self) -> str:
        cache = msal.SerializableTokenCache()
        if tc := self.auth_meta.get("token_cache"):
            cache.deserialize(tc)
        app = self._msal_app(cache)
        accounts = app.get_accounts()
        result = app.acquire_token_silent(SCOPES, account=accounts[0] if accounts else None)
        if not result or "access_token" not in result:
            raise RuntimeError("Token vencido: corre `task auth-outlook` de nuevo")
        if cache.has_state_changed:
            self.auth_meta["token_cache"] = cache.serialize()
        return result["access_token"]

    async def pull_incremental(self, cursor: str | None) -> tuple[list[NewRawItem], str | None]:
        token = self.get_access_token()
        url = cursor or DELTA_INICIAL
        items: list[NewRawItem] = []
        async with httpx.AsyncClient(timeout=60) as client:
            while url:
                r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
                r.raise_for_status()
                data = r.json()
                for msg in data.get("value", []):
                    if msg.get("@removed") or es_ruido(msg):
                        continue
                    items.append(
                        NewRawItem(
                            external_id=msg["id"],
                            kind="email",
                            payload=msg,
                            occurred_at=datetime.fromisoformat(msg["receivedDateTime"]),
                            text=f"{msg.get('subject', '')}\n{msg.get('bodyPreview', '')}",
                        )
                    )
                if delta := data.get("@odata.deltaLink"):
                    return items, delta
                url = data.get("@odata.nextLink")
        return items, cursor

    async def health(self) -> ConnectorHealth:
        try:
            token = self.get_access_token()
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(f"{GRAPH}/me", headers={"Authorization": f"Bearer {token}"})
                r.raise_for_status()
            return ConnectorHealth(ok=True)
        except Exception as e:  # noqa: BLE001 - health nunca revienta
            return ConnectorHealth(ok=False, detail=str(e))
