"""Criterio del Bloque 5 (Granola) con respuestas grabadas (respx):
el sync lista notas, trae su detalle, filtra las sin resumen, las convierte
en RawItems y es idempotente. El cursor avanza al created_at mas alto.
"""
import asyncio
import socket
import uuid

import pytest
import respx
from httpx import Response
from sqlalchemy import delete, select

from atlas.connectors.granola import es_ruido
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
    assert es_ruido({"title": "1:1", "summary_markdown": None, "summary_text": ""})  # sin resumen
    assert es_ruido({"title": "1:1", "summary_text": "   "})  # resumen vacio
    assert not es_ruido({"title": "Kickoff", "summary_markdown": "## Acuerdos\n- Tomas manda la propuesta"})


pytestmark_db = pytest.mark.skipif(not _pg_disponible(), reason="postgres no disponible")


@pytestmark_db
def test_sync_end_to_end_idempotente(monkeypatch):
    monkeypatch.setattr(sync_mod, "_decrypt_meta", lambda meta: {"token": "grn_fake"})
    monkeypatch.setattr(sync_mod, "_encrypt_meta", lambda meta: {"fernet": "x"})

    sufijo = uuid.uuid4().hex[:12]
    id_ok = f"not_{sufijo}A"    # con resumen -> entra
    id_ruido = f"not_{sufijo}B"  # sin resumen -> se filtra (pero avanza el cursor)

    async def run():
        async with sync_mod.SessionLocal() as s:
            await s.execute(delete(Source).where(Source.kind == "granola"))
            await s.commit()

        with respx.mock(assert_all_called=True) as mock:
            mock.get("https://public-api.granola.ai/v1/notes").mock(
                return_value=Response(200, json={
                    "notes": [
                        {"id": id_ok, "object": "note", "title": "Kickoff Agunsa",
                         "owner": {"name": "Tomas", "email": "tomas@niuro.io"},
                         "created_at": "2026-07-08T10:00:00Z", "updated_at": "2026-07-08T10:30:00Z"},
                        {"id": id_ruido, "object": "note", "title": "Nota vacia",
                         "owner": {"name": "Tomas", "email": "tomas@niuro.io"},
                         "created_at": "2026-07-08T11:00:00Z", "updated_at": "2026-07-08T11:00:00Z"},
                    ],
                    "hasMore": False,
                    "cursor": None,
                }))
            mock.get(f"https://public-api.granola.ai/v1/notes/{id_ok}").mock(
                return_value=Response(200, json={
                    "id": id_ok, "object": "note", "title": "Kickoff Agunsa",
                    "owner": {"name": "Tomas", "email": "tomas@niuro.io"},
                    "created_at": "2026-07-08T10:00:00Z", "updated_at": "2026-07-08T10:30:00Z",
                    "web_url": "https://notes.granola.ai/d/abc",
                    "calendar_event": {"scheduled_start_time": "2026-07-08T09:30:00Z"},
                    "attendees": [], "folder_membership": [],
                    "summary_text": "Tomas manda la propuesta el viernes.",
                    "summary_markdown": "## Acuerdos\n- Tomas manda la propuesta el viernes",
                    "transcript": None,
                }))
            mock.get(f"https://public-api.granola.ai/v1/notes/{id_ruido}").mock(
                return_value=Response(200, json={
                    "id": id_ruido, "object": "note", "title": "Nota vacia",
                    "owner": {"name": "Tomas", "email": "tomas@niuro.io"},
                    "created_at": "2026-07-08T11:00:00Z", "updated_at": "2026-07-08T11:00:00Z",
                    "web_url": "https://notes.granola.ai/d/def",
                    "calendar_event": None, "attendees": [], "folder_membership": [],
                    "summary_text": "", "summary_markdown": None, "transcript": None,
                }))
            r1 = await sync_mod.run_sync("granola")
            r2 = await sync_mod.run_sync("granola")  # segunda corrida: mismo lote, dedup

        assert r1.pulled == 1 and r1.created == 1, r1  # solo la nota con resumen entra
        assert r2.created == 0, r2  # idempotencia

        async with sync_mod.SessionLocal() as s:
            src = await s.scalar(select(Source).where(Source.kind == "granola"))
            assert src.sync_cursor == "2026-07-08T11:00:00Z"  # el created_at mas alto, aun del filtrado
            rows = (await s.scalars(select(RawItem).where(RawItem.source_id == src.id))).all()
            assert len(rows) == 1
            assert rows[0].external_id == id_ok
            assert rows[0].kind == "meeting_note"
            assert rows[0].payload["title"] == "Kickoff Agunsa"
            assert "transcript" not in rows[0].payload  # no lo guardamos
            await s.execute(delete(RawItem).where(RawItem.source_id == src.id))
            await s.execute(delete(Source).where(Source.id == src.id))
            await s.commit()

    asyncio.run(run())
