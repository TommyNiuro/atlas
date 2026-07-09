"""Criterio de terminado del Bloque 1: insertar y leer una tarea con su
evidencia y su score, y verificar que los tokens quedan cifrados en la base.
Requiere postgres corriendo con la migracion aplicada (task dev + task migrate).
"""
import asyncio
import socket
import uuid
from datetime import date, datetime, timezone

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from atlas.core import crypto
from atlas.db.models import RawItem, Source, Task, TaskScore


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


def test_tarea_con_evidencia_score_y_token_cifrado():
    async def run():
        # sesion propia para poder hacer rollback y no ensuciar la base
        from atlas.db.session import SessionLocal

        f = Fernet(Fernet.generate_key())
        async with SessionLocal() as session:
            src = Source(kind="outlook_mail", auth_meta={"access_token": crypto.encrypt("tok-123", f)})
            session.add(src)
            await session.flush()

            item = RawItem(
                source_id=src.id,
                external_id=f"msg-{uuid.uuid4()}",
                kind="email",
                payload={"subject": "propuesta", "from": "cliente@acme.com"},
                embedding=[0.1] * 1024,
                occurred_at=datetime.now(timezone.utc),
            )
            session.add(item)
            await session.flush()

            task = Task(
                title="Mandar la propuesta a Acme",
                raw_item_id=item.id,
                status="open",
                due_date=date(2026, 7, 11),
                evidence_quote="¿me mandas la propuesta el viernes?",
                deep_link="https://outlook.office.com/mail/msg-1",
                extraction_confidence=0.91,
            )
            session.add(task)
            await session.flush()
            session.add(TaskScore(task_id=task.id, priority_score=87.0,
                                  score_breakdown={"deadline_factor": 23, "requester_factor": 15}))
            await session.flush()

            # leer de vuelta
            leida = (await session.execute(
                select(Task, TaskScore).join(TaskScore).where(Task.id == task.id)
            )).one()
            assert leida.Task.evidence_quote.startswith("¿me mandas")
            assert leida.TaskScore.priority_score == 87.0
            assert leida.TaskScore.score_breakdown["deadline_factor"] == 23

            # el token en la base es ilegible y se descifra bien
            guardado = (await session.get(Source, src.id)).auth_meta["access_token"]
            assert "tok-123" not in guardado
            assert crypto.decrypt(guardado, f) == "tok-123"

            await session.rollback()

    asyncio.run(run())
