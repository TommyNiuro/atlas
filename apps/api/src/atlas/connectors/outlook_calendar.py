"""Conector Outlook Calendar: gemelo del de Mail (misma app de Entra ID,
permiso Calendars.Read), eventos de los proximos 14 dias via delta query."""
from datetime import datetime, timedelta, timezone

import httpx

from atlas.connectors.base import ConnectorHealth, NewRawItem, register
from atlas.connectors.outlook import GRAPH, OutlookMailConnector, _graph_get


@register
class OutlookCalendarConnector(OutlookMailConnector):
    kind = "outlook_cal"
    SCOPES = ["Calendars.Read"]

    def _delta_inicial(self) -> str:
        start = datetime.now(timezone.utc)
        end = start + timedelta(days=14)
        return (
            f"{GRAPH}/me/calendarView/delta"
            f"?startDateTime={start.isoformat()}&endDateTime={end.isoformat()}"
        )

    async def pull_incremental(self, cursor: str | None) -> tuple[list[NewRawItem], str | None]:
        # re-basaliza la ventana de 14 dias en cada sync: si guardara el deltaLink
        # la ventana quedaria congelada y los eventos futuros nunca entrarian.
        # Re-pull es barato, el dedup por external_id salta lo ya visto.
        token = self.get_access_token()
        url = self._delta_inicial()
        items: list[NewRawItem] = []
        async with httpx.AsyncClient(timeout=60) as client:
            while url:
                data = await _graph_get(client, url, token)
                for ev in data.get("value", []):
                    if ev.get("@removed") or ev.get("isCancelled"):
                        continue
                    items.append(
                        NewRawItem(
                            external_id=ev["id"],
                            kind="event",
                            payload=ev,
                            occurred_at=datetime.fromisoformat(
                                ev["start"]["dateTime"] + "+00:00"
                                if not ev["start"]["dateTime"].endswith("Z")
                                else ev["start"]["dateTime"]
                            ),
                            text=ev.get("subject", ""),
                        )
                    )
                url = data.get("@odata.nextLink")
        return items, None

    async def health(self) -> ConnectorHealth:
        return await super().health()
