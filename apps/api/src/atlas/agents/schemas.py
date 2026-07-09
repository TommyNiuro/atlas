"""Contratos Pydantic de los agentes. Si la salida no valida, se reintenta
una vez y luego se descarta con log (regla del requerimiento)."""
from pydantic import BaseModel, Field


class TaskCandidate(BaseModel):
    titulo: str
    descripcion: str | None = None
    cita_textual: str  # sin cita, la candidata se descarta
    confianza: float = Field(ge=0, le=1)
    due_date: str | None = None  # YYYY-MM-DD si el mensaje lo implica
    estimated_minutes: int | None = None


class ExtractorOut(BaseModel):
    candidatas: list[TaskCandidate] = []


class Clasificacion(BaseModel):
    area: str | None = None
    proyecto: str | None = None
    cliente: str | None = None
    tipo: str | None = None  # accion|seguimiento|delegable|estrategico|personal
    delegable: bool = False


class Senales(BaseModel):
    """Señales cualitativas del Priorizador; el score final lo calcula el
    Priority Engine determinista, no el LLM."""

    urgencia_percibida: float = Field(ge=0, le=1)
    impacto: float = Field(ge=0, le=1)
    esfuerzo: float = Field(ge=0, le=1)
    urgente: bool = False
    importante: bool = False


class RespuestasDetectadas(BaseModel):
    task_ids_respondidas: list[str] = []
