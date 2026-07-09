"""Criterio del Bloque 3 con agentes simulados (sin API): un correo que pide
la propuesta el viernes se vuelve tarea con evidencia y score; un gracias no
genera nada; el umbral 0.6-0.8 manda a sugerencias."""
import asyncio
import socket
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, select

from atlas.agents import orchestrator, runtime
from atlas.agents.schemas import Clasificacion, ExtractorOut, Senales, TaskCandidate
from atlas.db.models import RawItem, Source, Task, TaskEvent, TaskScore
from atlas.db.session import SessionLocal


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


RESPUESTAS = {
    "propuesta": ExtractorOut(candidatas=[TaskCandidate(
        titulo="Mandar la propuesta a Acme",
        cita_textual="¿me mandas la propuesta el viernes?",
        confianza=0.92, due_date="2026-07-11", estimated_minutes=45)]),
    "gracias": ExtractorOut(candidatas=[]),
    "ambiguo": ExtractorOut(candidatas=[TaskCandidate(
        titulo="Revisar tema pendiente", cita_textual="quedamos de ver ese tema",
        confianza=0.7)]),
}


async def _fake_call_agent(prompt_name, payload, schema, model):
    if schema is ExtractorOut:
        clave = payload["mensaje"]["clave"]
        return RESPUESTAS[clave]
    if schema is Clasificacion:
        return Clasificacion(area="Ventas", tipo="accion")
    if schema is Senales:
        return Senales(urgencia_percibida=0.8, impacto=0.9, esfuerzo=0.3,
                       urgente=True, importante=True)
    return None


def test_pipeline_extremo_a_extremo(monkeypatch):
    monkeypatch.setattr(runtime, "call_agent", _fake_call_agent)

    async def run():
        async with SessionLocal() as s:
            await s.execute(delete(TaskEvent))
            await s.execute(delete(TaskScore))
            await s.execute(delete(Task))
            await s.execute(delete(RawItem))
            await s.execute(delete(Source))
            src = Source(kind="outlook_mail")
            s.add(src)
            await s.flush()
            for clave in ("propuesta", "gracias", "ambiguo"):
                s.add(RawItem(source_id=src.id, external_id=f"{clave}-{uuid.uuid4().hex[:6]}",
                              kind="email", payload={"clave": clave, "webLink": f"https://outlook/{clave}"},
                              occurred_at=datetime.now(timezone.utc)))
            await s.commit()

        stats = await orchestrator.procesar_pendientes()
        assert stats["procesados"] == 3

        async with SessionLocal() as s:
            tareas = (await s.scalars(select(Task))).all()
            assert len(tareas) == 2  # el gracias no genera nada

            abierta = next(t for t in tareas if t.status == "open")
            assert abierta.title == "Mandar la propuesta a Acme"
            assert abierta.evidence_quote == "¿me mandas la propuesta el viernes?"
            assert abierta.due_date.isoformat() == "2026-07-11"
            assert abierta.deep_link == "https://outlook/propuesta"
            assert abierta.area_id is not None  # Ventas resuelta del seed

            sugerida = next(t for t in tareas if t.status == "suggested")
            assert sugerida.extraction_confidence == 0.7

            # score con desglose y ranking
            score = await s.get(TaskScore, abierta.id)
            assert score.priority_score > 0
            assert "deadline_factor" in score.score_breakdown
            assert score.rank_today in (1, 2)

            # todos los raw items quedaron marcados
            sin_procesar = (await s.scalars(
                select(RawItem).where(RawItem.processed_at.is_(None)))).all()
            assert sin_procesar == []

            # limpieza
            await s.execute(delete(TaskEvent))
            await s.execute(delete(TaskScore))
            await s.execute(delete(Task))
            await s.execute(delete(RawItem))
            await s.execute(delete(Source))
            await s.commit()

    asyncio.run(run())
