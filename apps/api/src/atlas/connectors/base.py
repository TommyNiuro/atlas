"""Interfaz comun de todos los conectores (seccion 6 del requerimiento).

Agregar una integracion nueva = implementar Connector + register().
Los conectores no deciden si algo es tarea: solo autentican, paginan y
normalizan a NewRawItem.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class NewRawItem:
    external_id: str
    kind: str  # email|message|meeting_note|crm_activity|issue|file_comment
    payload: dict
    occurred_at: datetime
    text: str = ""  # texto plano para embedding y filtros


@dataclass
class ConnectorHealth:
    ok: bool
    detail: str = ""


class Connector(Protocol):
    kind: str

    async def authenticate(self) -> dict:
        """Flujo interactivo; devuelve el auth_meta a cifrar en SOURCE."""
        ...

    async def pull_incremental(self, cursor: str | None) -> tuple[list[NewRawItem], str | None]:
        """Trae solo lo nuevo desde el cursor; devuelve (items, cursor_nuevo)."""
        ...

    async def health(self) -> ConnectorHealth: ...


# kind -> clase conectora (se instancia con el auth_meta descifrado)
REGISTRY: dict[str, type] = {}


def register(cls: type) -> type:
    REGISTRY[cls.kind] = cls
    return cls


@dataclass
class SyncResult:
    kind: str
    pulled: int = 0
    filtered: int = 0
    created: int = 0
    errors: list[str] = field(default_factory=list)
