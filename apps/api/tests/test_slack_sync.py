"""Criterio del Bloque 5 (Slack) con respuestas grabadas (respx):
el sync convierte mensajes en RawItems, filtra ruido y es idempotente.
"""
import asyncio
import socket
import uuid

import pytest
import respx
from httpx import Response
from sqlalchemy import delete, select

from atlas.connectors.slack import es_ruido
from atlas.connectors import sync as sync_mod
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
    assert es_ruido({"subtype": "channel_join", "text": "x", "user": "U1"}, "UME")
    assert es_ruido({"bot_id": "B1", "text": "deploy ok", "user": "U1"}, "UME")
    assert es_ruido({"text": "mi propia respuesta", "user": "UME"}, "UME")  # mio
    assert es_ruido({"text": "   ", "user": "U1"}, "UME")  # vacio
    assert not es_ruido({"text": "me pasas la propuesta?", "user": "UBOSS"}, "UME")


pytestmark_db = pytest.mark.skipif(not _pg_disponible(), reason="postgres no disponible")


@pytestmark_db
def test_sync_end_to_end_idempotente(monkeypatch):
    monkeypatch.setattr(sync_mod, "_decrypt_meta", lambda meta: {"token": "xoxp-fake"})
    monkeypatch.setattr(sync_mod, "_encrypt_meta", lambda meta: {"fernet": "x"})

    sufijo = uuid.uuid4().hex[:8]
    cid = f"D{sufijo}"
    msgs = [
        {"ts": "1720000002.000100", "user": "UBOSS", "text": "me pasas la propuesta el viernes?"},
        {"ts": "1720000003.000200", "user": "UME", "text": "dale, ahi va"},          # mio -> ruido
        {"ts": "1720000001.000000", "bot_id": "B1", "text": "deploy ok"},            # bot -> ruido
    ]

    async def run():
        async with sync_mod.SessionLocal() as s:
            await s.execute(delete(Source).where(Source.kind == "slack"))
            await s.commit()

        with respx.mock(assert_all_called=True) as mock:
            mock.get("https://slack.com/api/auth.test").mock(
                return_value=Response(200, json={"ok": True, "user_id": "UME", "user": "tomas", "team": "niuro"})
            )
            mock.get("https://slack.com/api/conversations.list").mock(
                return_value=Response(200, json={"ok": True, "channels": [{"id": cid, "user": "UBOSS"}]})
            )
            mock.get("https://slack.com/api/conversations.history").mock(
                return_value=Response(200, json={"ok": True, "messages": msgs})
            )
            r1 = await sync_mod.run_sync("slack")
            r2 = await sync_mod.run_sync("slack")  # segunda corrida: mismo lote, dedup

        assert r1.pulled == 1 and r1.created == 1, r1  # solo el mensaje del jefe entra
        assert r2.created == 0, r2  # idempotencia

        async with sync_mod.SessionLocal() as s:
            src = await s.scalar(select(Source).where(Source.kind == "slack"))
            assert src.sync_cursor == "1720000003.000200"  # el ts mas alto, aun del mensaje filtrado
            rows = (await s.scalars(select(RawItem).where(RawItem.source_id == src.id))).all()
            assert len(rows) == 1
            assert rows[0].external_id == f"{cid}:1720000002.000100"
            assert rows[0].payload["_channel_id"] == cid
            await s.execute(delete(RawItem).where(RawItem.source_id == src.id))
            await s.execute(delete(Source).where(Source.id == src.id))
            await s.commit()

    asyncio.run(run())
