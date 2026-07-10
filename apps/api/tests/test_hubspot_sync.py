"""Criterio del Bloque 5 (HubSpot) con respuestas grabadas (respx):
el sync pagina engagements + deals, filtra ruido, normaliza a crm_activity y es
idempotente. Y la regla del handoff: deals_sin_actividad (query SQL).
"""
import asyncio
import socket
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import respx
from httpx import Response
from sqlalchemy import delete, select

from atlas.connectors.hubspot import _ms, deals_sin_actividad, es_ruido
from atlas.connectors import sync as sync_mod
from atlas.core.config import DEFAULT_USER_ID
from atlas.db.models import RawItem, Source


def _pg_disponible() -> bool:
    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", 5432))
        return True
    except OSError:
        return False
    finally:
        s.close()


def test_filtro_ruido():
    assert es_ruido("notes", "")           # engagement sin texto -> ruido
    assert es_ruido("tasks", "   ")        # vacio -> ruido
    assert not es_ruido("notes", "llamar a Tomas")
    assert not es_ruido("deals", "")       # un deal nunca es ruido (aporta estado)


pytestmark_db = pytest.mark.skipif(not _pg_disponible(), reason="postgres no disponible")

BASE = "https://api.hubapi.com/crm/v3/objects"


@pytestmark_db
def test_sync_end_to_end_idempotente(monkeypatch):
    monkeypatch.setattr(sync_mod, "_decrypt_meta", lambda meta: {"token": "pat_fake"})
    monkeypatch.setattr(sync_mod, "_encrypt_meta", lambda meta: {"fernet": "x"})

    sufijo = uuid.uuid4().hex[:8]
    note_id, deal_id = f"n{sufijo}", f"d{sufijo}"
    note = {
        "id": note_id, "createdAt": "2026-07-08T09:00:00Z", "updatedAt": "2026-07-08T10:00:00Z",
        "properties": {"hs_note_body": "<p>Enviar propuesta a Agunsa</p>",
                       "hs_lastmodifieddate": "2026-07-08T10:00:00Z"},
    }
    deal = {
        "id": deal_id, "createdAt": "2026-06-01T09:00:00Z", "updatedAt": "2026-07-08T12:00:00Z",
        "properties": {"dealname": "Agunsa expansion", "dealstage": "presentationscheduled",
                       "amount": "50000", "hs_is_closed": "false",
                       "hs_last_sales_activity_timestamp": "2026-05-01T10:00:00Z",
                       "hs_lastmodifieddate": "2026-07-08T12:00:00Z"},
    }

    async def run():
        async with sync_mod.SessionLocal() as s:
            await s.execute(delete(Source).where(Source.kind == "hubspot"))
            await s.commit()

        with respx.mock(assert_all_called=True) as mock:
            for obj in ("notes", "tasks", "calls", "emails", "meetings", "deals"):
                if obj == "notes":
                    payload = {"results": [note]}
                elif obj == "deals":
                    payload = {"results": [deal]}
                else:
                    payload = {"results": []}
                mock.post(f"{BASE}/{obj}/search").mock(return_value=Response(200, json=payload))
            r1 = await sync_mod.run_sync("hubspot")
            r2 = await sync_mod.run_sync("hubspot")  # segunda corrida: mismo lote, dedup

        assert r1.pulled == 2 and r1.created == 2, r1   # nota (con texto) + deal
        assert r2.created == 0, r2                       # idempotencia

        async with sync_mod.SessionLocal() as s:
            src = await s.scalar(select(Source).where(Source.kind == "hubspot"))
            assert src.sync_cursor == str(_ms("2026-07-08T12:00:00Z"))  # el lastmodified mas alto (deal)
            rows = (await s.scalars(select(RawItem).where(RawItem.source_id == src.id))).all()
            ext = {r.external_id for r in rows}
            assert ext == {f"notes:{note_id}", f"deals:{deal_id}"}
            assert all(r.kind == "crm_activity" for r in rows)
            await s.execute(delete(RawItem).where(RawItem.source_id == src.id))
            await s.execute(delete(Source).where(Source.id == src.id))
            await s.commit()

    asyncio.run(run())


@pytestmark_db
def test_deals_sin_actividad():
    now = datetime.now(timezone.utc)
    sufijo = uuid.uuid4().hex[:8]

    def deal_item(src_id, did, closed, actividad):
        props = {"dealname": f"Deal {did}", "dealstage": "x", "amount": "1000",
                 "hs_is_closed": closed}
        if actividad is not None:
            props["hs_last_sales_activity_timestamp"] = actividad.isoformat()
        return RawItem(
            source_id=src_id, user_id=DEFAULT_USER_ID, external_id=f"deals:{did}",
            kind="crm_activity", payload={"_object": "deals", "id": did, "properties": props},
            occurred_at=now,
        )

    async def run():
        async with sync_mod.SessionLocal() as s:
            src = Source(kind=f"hubspot_test_{sufijo}", status="active")
            s.add(src)
            await s.flush()
            s.add_all([
                deal_item(src.id, "A", "false", now - timedelta(days=60)),   # abierto y viejo -> entra
                deal_item(src.id, "B", "false", now - timedelta(days=2)),    # abierto y reciente -> fuera
                deal_item(src.id, "C", "true", now - timedelta(days=200)),   # cerrado -> fuera
                deal_item(src.id, "D", "false", None),                       # abierto sin actividad -> entra
            ])
            await s.commit()

            filas = await deals_sin_actividad(s, dias=14)
            ids = {f["deal_id"] for f in filas}
            assert "A" in ids and "D" in ids
            assert "B" not in ids and "C" not in ids

            await s.execute(delete(RawItem).where(RawItem.source_id == src.id))
            await s.execute(delete(Source).where(Source.id == src.id))
            await s.commit()

    asyncio.run(run())
