"""Criterio del Bloque 2 con respuestas grabadas de Graph (respx):
el sync convierte correos en RawItems, filtra ruido y es idempotente.
"""
import asyncio
import socket
import uuid

import pytest
import respx
from httpx import Response
from sqlalchemy import delete, select

from atlas.connectors.outlook import DELTA_INICIAL, OutlookMailConnector, es_ruido
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


def _msg(mid: str, subject: str, sender: str, headers: list | None = None) -> dict:
    return {
        "id": mid,
        "subject": subject,
        "from": {"emailAddress": {"address": sender}},
        "receivedDateTime": "2026-07-09T12:00:00Z",
        "bodyPreview": "hola",
        "webLink": f"https://outlook.office.com/mail/{mid}",
        "internetMessageHeaders": headers or [],
    }


def test_filtro_barato():
    assert es_ruido(_msg("1", "oferta", "noreply@spam.com"))
    assert es_ruido(_msg("2", "news", "a@b.com", [{"name": "List-Unsubscribe", "value": "x"}]))
    assert es_ruido(_msg("3", "auto", "a@b.com", [{"name": "Auto-Submitted", "value": "auto-generated"}]))
    assert not es_ruido(_msg("4", "propuesta", "cliente@acme.com"))


pytestmark_db = pytest.mark.skipif(not _pg_disponible(), reason="postgres no disponible")


@pytestmark_db
def test_sync_end_to_end_idempotente(monkeypatch):
    monkeypatch.setattr(OutlookMailConnector, "get_access_token", lambda self: "tok-fake")
    monkeypatch.setattr(sync_mod, "_decrypt_meta", lambda meta: {})
    monkeypatch.setattr(sync_mod, "_encrypt_meta", lambda meta: {"fernet": "x"})

    sufijo = uuid.uuid4().hex[:8]
    delta = f"https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$deltatoken=abc{sufijo}"
    respuesta = {
        "value": [
            _msg(f"m1-{sufijo}", "¿me mandas la propuesta el viernes?", "cliente@acme.com"),
            _msg(f"m2-{sufijo}", "revision contrato", "socio@niuro.io"),
            _msg(f"m3-{sufijo}", "NEWSLETTER", "noreply@news.com"),
        ],
        "@odata.deltaLink": delta,
    }

    async def run():
        async with sync_mod.SessionLocal() as s:
            await s.execute(delete(Source).where(Source.kind == "outlook_mail"))
            await s.commit()

        with respx.mock(assert_all_called=True) as mock:
            mock.get(url__startswith=DELTA_INICIAL.split("?")[0]).mock(
                return_value=Response(200, json=respuesta)
            )
            r1 = await sync_mod.run_sync("outlook_mail")
            r2 = await sync_mod.run_sync("outlook_mail")  # segunda corrida: delta link

        assert r1.pulled == 2 and r1.created == 2, r1  # el newsletter no entra
        assert r2.created == 0, r2  # idempotencia

        async with sync_mod.SessionLocal() as s:
            src = await s.scalar(select(Source).where(Source.kind == "outlook_mail"))
            assert src.sync_cursor == delta
            rows = (await s.scalars(select(RawItem).where(RawItem.source_id == src.id))).all()
            assert len(rows) == 2
            assert rows[0].payload["webLink"].startswith("https://outlook.office.com")
            # limpieza
            await s.execute(delete(RawItem).where(RawItem.source_id == src.id))
            await s.execute(delete(Source).where(Source.id == src.id))
            await s.commit()

    asyncio.run(run())
