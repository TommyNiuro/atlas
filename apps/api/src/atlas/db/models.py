"""Las 11 entidades del requerimiento (seccion 5), user_id en todas."""
import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import DATERANGE, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeEngine

from atlas.core.config import DEFAULT_USER_ID

# ponytail: el requerimiento dice 1536 dims, pero voyage-3.5-lite entrega
# 256/512/1024/2048; usamos su default 1024. Cambiar aqui si cambia el modelo.
EMBEDDING_DIMS = 1024


class Base(DeclarativeBase):
    type_annotation_map: dict[type, TypeEngine] = {dict: JSONB}


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _user_id() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), nullable=False, default=DEFAULT_USER_ID)


class Source(Base):
    __tablename__ = "source"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_id()
    kind: Mapped[str] = mapped_column(Text)  # outlook_mail|outlook_cal|slack|granola|hubspot|github|gdrive
    auth_meta: Mapped[dict | None] = mapped_column(JSONB)  # tokens cifrados con Fernet
    sync_cursor: Mapped[str | None] = mapped_column(Text)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, default="active")  # active|error|paused


class RawItem(Base):
    __tablename__ = "raw_item"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id"),
        Index("ix_raw_item_payload_gin", "payload", postgresql_using="gin"),
        Index(
            "ix_raw_item_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_id()
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source.id"))
    external_id: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)  # email|message|meeting_note|crm_activity|issue|file_comment
    payload: Mapped[dict] = mapped_column(JSONB)  # objeto original completo, nada se pierde
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMS))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Area(Base):
    __tablename__ = "area"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_id()
    name: Mapped[str] = mapped_column(Text)


class Client(Base):
    __tablename__ = "client"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_id()
    name: Mapped[str] = mapped_column(Text)


class Project(Base):
    __tablename__ = "project"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_id()
    name: Mapped[str] = mapped_column(Text)
    area_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("area.id"))
    client_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("client.id"))
    strategic: Mapped[bool] = mapped_column(Boolean, default=False)  # pareto_factor


class Task(Base):
    __tablename__ = "task"
    __table_args__ = (
        CheckConstraint(
            "status IN ('suggested','open','in_progress','waiting','done','dropped')",
            name="ck_task_status",
        ),
        Index("ix_task_status_due", "status", "due_date"),
        Index("ix_task_area_status", "area_id", "status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_id()
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    area_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("area.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project.id"))
    client_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("client.id"))
    raw_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("raw_item.id"))
    status: Mapped[str] = mapped_column(Text, default="open")
    task_type: Mapped[str | None] = mapped_column(Text)  # accion|seguimiento|delegable|estrategico|personal
    due_date: Mapped[date | None] = mapped_column(Date)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)
    evidence_quote: Mapped[str | None] = mapped_column(Text)
    deep_link: Mapped[str | None] = mapped_column(Text)
    extraction_confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskScore(Base):
    __tablename__ = "task_score"

    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = _user_id()
    priority_score: Mapped[float] = mapped_column(Float)  # 0-100
    score_breakdown: Mapped[dict] = mapped_column(JSONB)  # cada factor con su valor
    rank_today: Mapped[int | None] = mapped_column(Integer)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TaskEvent(Base):
    __tablename__ = "task_event"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_id()
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task.id"))
    event: Mapped[str] = mapped_column(Text)  # created|status_change|rescored|snoozed|edited
    detail: Mapped[dict | None] = mapped_column(JSONB)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TimeBlock(Base):
    __tablename__ = "time_block"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_id()
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    origin: Mapped[str] = mapped_column(Text)  # ai_proposed|user_set|calendar_event
    status: Mapped[str] = mapped_column(Text, default="proposed")  # proposed|accepted|done|missed


class UserFeedback(Base):
    __tablename__ = "user_feedback"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_id()
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task.id"))
    feedback_kind: Mapped[str] = mapped_column(Text)  # reclassified|repriorized|rejected|merged
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WeeklyReport(Base):
    __tablename__ = "weekly_report"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_id()
    week = mapped_column(DATERANGE)
    kpis: Mapped[dict | None] = mapped_column(JSONB)
    pdf_path: Mapped[str | None] = mapped_column(Text)
    xlsx_path: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
