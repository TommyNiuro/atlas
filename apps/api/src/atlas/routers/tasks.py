"""API de tareas: vista Hoy, bandeja, triage por teclado, creacion en
lenguaje natural. Toda accion del usuario queda en USER_FEEDBACK o TASK_EVENT."""
import re
import uuid
from datetime import date, datetime, timezone

from dateparser.search import search_dates
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, text

from atlas.agents.orchestrator import ESTADOS_ABIERTOS, rescore_abiertas
from atlas.db.models import Area, Client, Project, RawItem, Task, TaskEvent, TaskScore, UserFeedback
from atlas.db.session import SessionLocal

router = APIRouter(prefix="/api", tags=["tasks"])


def _task_out(t: Task, s: TaskScore | None, extra: dict | None = None) -> dict:
    return {
        "id": str(t.id),
        "title": t.title,
        "description": t.description,
        "status": t.status,
        "task_type": t.task_type,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "estimated_minutes": t.estimated_minutes,
        "evidence_quote": t.evidence_quote,
        "deep_link": t.deep_link,
        "confidence": t.extraction_confidence,
        "score": s.priority_score if s else None,
        "rank": s.rank_today if s else None,
        "breakdown": s.score_breakdown if s else None,
        **(extra or {}),
    }


async def _notify(session) -> None:
    await session.execute(text("NOTIFY atlas_tasks, 'changed'"))


@router.get("/today")
async def vista_hoy():
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                select(Task, TaskScore)
                .outerjoin(TaskScore, TaskScore.task_id == Task.id)
                .where(Task.status.in_(("open", "in_progress", "waiting")))
                .order_by(TaskScore.rank_today.nulls_last())
            )
        ).all()
        tareas = [_task_out(t, sc) for t, sc in rows]

        sugeridas = await s.scalar(
            select(func.count()).select_from(Task).where(Task.status == "suggested")
        )

        # agenda del dia desde los eventos de Outlook Calendar
        eventos = (
            await s.scalars(
                select(RawItem).where(
                    RawItem.kind == "event",
                    func.date(RawItem.occurred_at) == date.today(),
                ).order_by(RawItem.occurred_at)
            )
        ).all()
        agenda = [
            {
                "subject": e.payload.get("subject"),
                "start": e.payload.get("start", {}).get("dateTime"),
                "end": e.payload.get("end", {}).get("dateTime"),
                "online": bool(e.payload.get("onlineMeeting")),
            }
            for e in eventos
        ]

        # carga del dia: reuniones + minutos estimados de tareas con due hoy
        min_reuniones = 0
        for e in eventos:
            try:
                ini = datetime.fromisoformat(e.payload["start"]["dateTime"][:19])
                fin = datetime.fromisoformat(e.payload["end"]["dateTime"][:19])
                min_reuniones += (fin - ini).total_seconds() / 60
            except (KeyError, ValueError):
                pass
        min_tareas = sum(
            t.estimated_minutes or 30
            for t, _ in rows
            if t.due_date and t.due_date == date.today()
        )
        carga = round(min(1.0, (min_reuniones + min_tareas) / (8 * 60)), 2)

        return {
            "top5": tareas[:5],
            "resto": tareas[5:],
            "sugeridas_pendientes": sugeridas,
            "agenda": agenda,
            "carga_del_dia": carga,
        }


@router.get("/suggestions")
async def bandeja():
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                select(Task, TaskScore)
                .outerjoin(TaskScore, TaskScore.task_id == Task.id)
                .where(Task.status == "suggested")
                .order_by(Task.created_at)
            )
        ).all()
        return [_task_out(t, sc) for t, sc in rows]


class TriageIn(BaseModel):
    action: str  # accept | reject | edit | merge
    title: str | None = None
    due_date: str | None = None
    merge_into: str | None = None


@router.post("/tasks/{task_id}/triage")
async def triage(task_id: uuid.UUID, body: TriageIn):
    async with SessionLocal() as s:
        t = await s.get(Task, task_id)
        if not t:
            raise HTTPException(404)
        before = {"status": t.status, "title": t.title}
        kind = {"accept": "reclassified", "reject": "rejected",
                "edit": "reclassified", "merge": "merged"}.get(body.action)
        if not kind:
            raise HTTPException(422, "action invalida")

        if body.action == "accept":
            t.status = "open"
        elif body.action == "reject":
            t.status = "dropped"
        elif body.action == "edit":
            t.title = body.title or t.title
            t.due_date = date.fromisoformat(body.due_date) if body.due_date else t.due_date
            t.status = "open"
        elif body.action == "merge":
            t.status = "dropped"

        s.add(UserFeedback(task_id=t.id, user_id=t.user_id, feedback_kind=kind,
                           before=before, after={"status": t.status, "title": t.title}))
        s.add(TaskEvent(task_id=t.id, user_id=t.user_id, event="status_change",
                        detail={"triage": body.action}))
        await rescore_abiertas(s)
        await _notify(s)
        await s.commit()
        return {"ok": True, "status": t.status}


class CreateIn(BaseModel):
    text: str  # lenguaje natural: "café con Alan el jueves 9am"


def _normalizar_horas(texto: str) -> str:
    # "9am"/"10pm" confunden a dateparser en español; se vuelven "9:00"/"22:00"
    def repl(m: re.Match) -> str:
        h = int(m.group(1)) + (12 if m.group(2).lower() == "pm" and int(m.group(1)) < 12 else 0)
        return f"{h}:00"

    return re.sub(r"\b(\d{1,2})\s*(am|pm)\b", repl, texto, flags=re.I)


@router.post("/tasks")
async def crear(body: CreateIn):
    settings = {"PREFER_DATES_FROM": "future", "TIMEZONE": "local"}
    normal = _normalizar_horas(body.text)
    encontrada = [
        (f, d) for f, d in (search_dates(normal, languages=["es"], settings=settings) or [])
        if len(f) >= 4  # descarta falsos positivos tipo "a"
    ]
    due, titulo = None, normal.strip()
    if encontrada:
        frase, fecha = encontrada[-1]
        due = fecha.date()
        titulo = titulo.replace(frase, "").strip(" ,.-") or body.text
        titulo = re.sub(r"\s+(el|la|los|las|para|este|esta)$", "", titulo)

    async with SessionLocal() as s:
        t = Task(title=titulo, status="open", task_type="accion", due_date=due)
        s.add(t)
        await s.flush()
        s.add(TaskEvent(task_id=t.id, user_id=t.user_id, event="created",
                        detail={"origen": "palette", "texto": body.text}))
        await rescore_abiertas(s)
        await _notify(s)
        await s.commit()
        return {"id": str(t.id), "title": titulo,
                "due_date": due.isoformat() if due else None}


@router.post("/tasks/{task_id}/complete")
async def completar(task_id: uuid.UUID):
    async with SessionLocal() as s:
        t = await s.get(Task, task_id)
        if not t:
            raise HTTPException(404)
        t.status = "done"
        t.completed_at = datetime.now(timezone.utc)
        s.add(TaskEvent(task_id=t.id, user_id=t.user_id, event="status_change",
                        detail={"a": "done"}))
        await rescore_abiertas(s)
        await _notify(s)
        await s.commit()
        return {"ok": True}


@router.post("/tasks/{task_id}/snooze")
async def snooze(task_id: uuid.UUID, dias: int = 1):
    async with SessionLocal() as s:
        t = await s.get(Task, task_id)
        if not t:
            raise HTTPException(404)
        t.due_date = date.fromordinal(date.today().toordinal() + dias)
        s.add(TaskEvent(task_id=t.id, user_id=t.user_id, event="snoozed",
                        detail={"dias": dias}))
        await rescore_abiertas(s)
        await _notify(s)
        await s.commit()
        return {"ok": True, "due_date": t.due_date.isoformat()}


@router.get("/projects")
async def proyectos():
    async with SessionLocal() as s:
        areas = (await s.scalars(select(Area))).all()
        projs = (await s.scalars(select(Project))).all()
        clientes = (await s.scalars(select(Client))).all()
        abiertas = (
            await s.execute(
                select(Task.area_id, func.count()).where(
                    Task.status.in_(ESTADOS_ABIERTOS)).group_by(Task.area_id)
            )
        ).all()
        conteo = {str(a): c for a, c in abiertas if a}
        return {
            "areas": [{"id": str(a.id), "name": a.name,
                       "tareas_abiertas": conteo.get(str(a.id), 0)} for a in areas],
            "proyectos": [{"id": str(p.id), "name": p.name} for p in projs],
            "clientes": [{"id": str(c.id), "name": c.name} for c in clientes],
        }
