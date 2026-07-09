"""Orchestrator: codigo Python que enruta cada RawItem por el pipeline
Extractor -> Clasificador -> Priorizador -> Priority Engine. Sin framework
de agentes: control explicito (patron del AI SDR de Niuro).

Uso: uv run python -m atlas.agents.orchestrator
"""
import asyncio
import logging
from datetime import date, datetime, timezone

from sqlalchemy import select, text

from atlas.core import config
from atlas.agents import runtime
from atlas.agents.schemas import (
    Clasificacion,
    ExtractorOut,
    RespuestasDetectadas,
    Senales,
)
from atlas.db.models import Area, Client, Project, RawItem, Task, TaskEvent, TaskScore
from atlas.db.session import SessionLocal
from atlas.scoring.engine import Facts, compute_score, load_weights

log = logging.getLogger("atlas.orchestrator")

ESTADOS_ABIERTOS = ("suggested", "open", "in_progress", "waiting")


async def _es_duplicado(session, item: RawItem, umbral: float) -> bool:
    """Dedup previa al LLM: coseno del embedding contra tareas abiertas."""
    if item.embedding is None:
        return False
    row = await session.execute(
        text(
            "SELECT 1 - (ri.embedding <=> CAST(:emb AS vector)) AS sim FROM task t "
            "JOIN raw_item ri ON t.raw_item_id = ri.id "
            "WHERE t.status IN ('suggested','open','in_progress','waiting') "
            "AND ri.embedding IS NOT NULL AND ri.id != CAST(:self_id AS uuid) "
            "ORDER BY sim DESC LIMIT 1"
        ),
        {"emb": str(list(item.embedding)), "self_id": str(item.id)},
    )
    top = row.scalar()
    return top is not None and top > umbral


async def _contexto_usuario(session) -> dict:
    areas = (await session.scalars(select(Area.name))).all()
    proyectos = (await session.scalars(select(Project.name))).all()
    clientes = (await session.scalars(select(Client.name))).all()
    return {"areas": list(areas), "proyectos": list(proyectos), "clientes": list(clientes)}


async def _resolver_ids(session, clasif: Clasificacion) -> dict:
    async def buscar(model, nombre):
        if not nombre:
            return None
        return await session.scalar(select(model.id).where(model.name.ilike(nombre)))

    return {
        "area_id": await buscar(Area, clasif.area),
        "project_id": await buscar(Project, clasif.proyecto),
        "client_id": await buscar(Client, clasif.cliente),
    }


async def procesar_pendientes() -> dict:
    """Convierte RawItems sin procesar en tareas con evidencia y score."""
    umbrales = load_weights()["thresholds"]
    stats = {"procesados": 0, "duplicados": 0, "tareas": 0, "sugeridas": 0, "descartadas": 0}

    async with SessionLocal() as session:
        contexto = await _contexto_usuario(session)
        pendientes = (
            await session.scalars(
                select(RawItem).where(RawItem.processed_at.is_(None)).order_by(RawItem.occurred_at)
            )
        ).all()

        for item in pendientes:
            stats["procesados"] += 1
            item.processed_at = datetime.now(timezone.utc)

            if await _es_duplicado(session, item, umbrales["dedup_cosine"]):
                stats["duplicados"] += 1
                continue

            extraccion = await runtime.call_agent(
                "extractor",
                {"mensaje": item.payload, "fecha_hoy": date.today().isoformat(),
                 "contexto_usuario": contexto},
                ExtractorOut,
                config.MODEL_FAST,
            )
            if not extraccion:
                continue

            for cand in extraccion.candidatas:
                if not cand.cita_textual or cand.confianza < umbrales["confidence_discard"]:
                    stats["descartadas"] += 1
                    continue

                clasif = await runtime.call_agent(
                    "clasificador",
                    {"tarea": cand.model_dump(), "areas": contexto["areas"],
                     "proyectos": contexto["proyectos"], "clientes": contexto["clientes"]},
                    Clasificacion,
                    config.MODEL_FAST,
                ) or Clasificacion(tipo="accion")

                senales = await runtime.call_agent(
                    "priorizador",
                    {"tarea": cand.model_dump(), "clasificacion": clasif.model_dump()},
                    Senales,
                    config.MODEL_SMART,
                ) or Senales(urgencia_percibida=0.3, impacto=0.3, esfuerzo=0.3)

                ids = await _resolver_ids(session, clasif)
                estado = "open" if cand.confianza >= umbrales["confidence_auto_open"] else "suggested"
                due = date.fromisoformat(cand.due_date) if cand.due_date else None

                task = Task(
                    title=cand.titulo,
                    description=cand.descripcion,
                    status=estado,
                    task_type=clasif.tipo,
                    due_date=due,
                    estimated_minutes=cand.estimated_minutes,
                    evidence_quote=cand.cita_textual,
                    deep_link=item.payload.get("webLink"),
                    extraction_confidence=cand.confianza,
                    raw_item_id=item.id,
                    user_id=item.user_id,
                    **ids,
                )
                session.add(task)
                await session.flush()

                horas = None
                if due:
                    horas = (datetime.combine(due, datetime.min.time(), timezone.utc)
                             - datetime.now(timezone.utc)).total_seconds() / 3600
                # ponytail: requester_factor fijo en 0.6 hasta que el Bloque 5
                # traiga CRM/roles para distinguir cliente-con-deal de colega
                facts = Facts(
                    horas_hasta_deadline=horas,
                    impacto=senales.impacto,
                    requester_factor=0.6,
                    urgente=senales.urgente,
                    importante=senales.importante,
                    estimated_minutes=cand.estimated_minutes,
                )
                score, breakdown = compute_score(facts)
                session.add(TaskScore(task_id=task.id, user_id=task.user_id,
                                      priority_score=score, score_breakdown=breakdown))
                session.add(TaskEvent(task_id=task.id, user_id=task.user_id, event="created",
                                      detail={"fuente": item.kind, "confianza": cand.confianza}))
                stats["tareas" if estado == "open" else "sugeridas"] += 1

        # seguimiento: solo si hay tareas waiting y llegaron mensajes nuevos
        waiting = (await session.scalars(select(Task).where(Task.status == "waiting"))).all()
        if waiting and pendientes:
            detectadas = await runtime.call_agent(
                "seguimiento",
                {"tareas_waiting": [{"id": str(t.id), "titulo": t.title,
                                     "evidencia": t.evidence_quote} for t in waiting],
                 "mensajes_nuevos": [i.payload for i in pendientes[:20]]},
                RespuestasDetectadas,
                config.MODEL_FAST,
            )
            for tid in (detectadas.task_ids_respondidas if detectadas else []):
                t = next((w for w in waiting if str(w.id) == tid), None)
                if t:
                    session.add(TaskEvent(task_id=t.id, user_id=t.user_id,
                                          event="status_change",
                                          detail={"detalle": "respuesta detectada"}))

        await session.commit()
        await rescore_abiertas(session)
        await session.commit()

    return stats


async def rescore_abiertas(session) -> None:
    """Rescoring global determinista: corre al final de cada sync porque el
    score decae con el tiempo. Milisegundos, cero tokens."""
    weights = load_weights()
    tareas = (
        await session.scalars(
            select(Task).where(Task.status.in_(ESTADOS_ABIERTOS))
        )
    ).all()
    scored = []
    for t in tareas:
        prev = await session.get(TaskScore, t.id)
        impacto = (prev.score_breakdown.get("impact_factor", 0) / weights["weights"]["impact_factor"]
                   if prev and prev.score_breakdown.get("impact_factor") else 0.3)
        horas = None
        if t.due_date:
            horas = (datetime.combine(t.due_date, datetime.min.time(), timezone.utc)
                     - datetime.now(timezone.utc)).total_seconds() / 3600
        dias = (datetime.now(timezone.utc) - t.created_at).total_seconds() / 86400 if t.created_at else 0
        facts = Facts(horas_hasta_deadline=horas, impacto=impacto, requester_factor=0.6,
                      estimated_minutes=t.estimated_minutes, dias_abierta=dias)
        score, breakdown = compute_score(facts, weights)
        scored.append((t, score, breakdown, prev))

    scored.sort(key=lambda x: x[1], reverse=True)
    for rank, (t, score, breakdown, prev) in enumerate(scored, start=1):
        if prev:
            prev.priority_score, prev.score_breakdown, prev.rank_today = score, breakdown, rank
            prev.computed_at = datetime.now(timezone.utc)
        else:
            session.add(TaskScore(task_id=t.id, user_id=t.user_id, priority_score=score,
                                  score_breakdown=breakdown, rank_today=rank))


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    stats = asyncio.run(procesar_pendientes())
    print(f"Pipeline: {stats}")


if __name__ == "__main__":
    main()
