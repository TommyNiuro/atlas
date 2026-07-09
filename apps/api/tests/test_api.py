"""API del Bloque 4: crear tarea en lenguaje natural, vista Hoy, triage con
USER_FEEDBACK. Requiere postgres local."""
import socket

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from atlas.db.models import RawItem, Source, Task, TaskEvent, TaskScore, UserFeedback
from atlas.main import app


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


pytestmark = pytest.mark.skipif(not _pg_disponible(), reason="postgres no disponible")


@pytest.fixture()
def cliente():
    import asyncio

    from atlas.db.session import SessionLocal

    async def limpiar():
        async with SessionLocal() as s:
            for tabla in (UserFeedback, TaskEvent, TaskScore, Task, RawItem, Source):
                await s.execute(delete(tabla))
            await s.commit()

    asyncio.run(limpiar())
    with TestClient(app) as c:
        yield c
    asyncio.run(limpiar())


def test_crear_con_fecha_natural_y_vista_hoy(cliente):
    r = cliente.post("/api/tasks", json={"text": "café con Alan el jueves 9am"})
    assert r.status_code == 200
    body = r.json()
    assert "café con Alan" in body["title"]
    assert body["due_date"] is not None  # el jueves se parseó

    hoy = cliente.get("/api/today").json()
    assert len(hoy["top5"]) == 1
    assert hoy["top5"][0]["score"] is not None
    assert hoy["top5"][0]["rank"] == 1


def test_triage_guarda_feedback(cliente):
    import asyncio

    from atlas.db.session import SessionLocal

    tid = cliente.post("/api/tasks", json={"text": "revisar contrato"}).json()["id"]

    async def marcar_sugerida():
        async with SessionLocal() as s:
            t = await s.get(Task, tid)
            t.status = "suggested"
            await s.commit()

    asyncio.run(marcar_sugerida())
    assert len(cliente.get("/api/suggestions").json()) == 1

    r = cliente.post(f"/api/tasks/{tid}/triage", json={"action": "accept"})
    assert r.json()["status"] == "open"

    async def feedback():
        async with SessionLocal() as s:
            return (await s.scalars(select(UserFeedback))).all()

    fb = asyncio.run(feedback())
    assert len(fb) == 1 and fb[0].feedback_kind == "reclassified"


def test_scoring_roundtrip(cliente):
    pesos = cliente.get("/api/scoring").json()
    r = cliente.put("/api/scoring", json={"weights": pesos["weights"]})
    assert r.status_code == 200
    assert cliente.put("/api/scoring", json={"weights": {"malo": 1}}).status_code == 422
