"""Settings: estado de conectores y editor de pesos del scoring (el ranking
se recalcula al guardar)."""
import math
import os

import yaml
from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from atlas.agents.orchestrator import rescore_abiertas
from atlas.db.models import Source
from atlas.db.session import SessionLocal
from atlas.scoring.engine import DEFAULT_WEIGHTS_PATH, load_weights

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/sources")
async def fuentes():
    async with SessionLocal() as s:
        rows = (await s.scalars(select(Source))).all()
        return [
            {
                "kind": src.kind,
                "status": src.status,
                "last_sync_at": src.last_sync_at.isoformat() if src.last_sync_at else None,
                "autenticado": src.auth_meta is not None,
            }
            for src in rows
        ]


@router.post("/sources/{kind}/reauth")
async def reauth(kind: str):
    """Re-lanza el device flow del conector (el codigo sale en el log del server)."""
    import asyncio

    from atlas.connectors import outlook, outlook_calendar  # noqa: F401 registra
    from atlas.connectors.base import REGISTRY
    from atlas.connectors.sync import authenticate

    if kind not in REGISTRY:
        raise HTTPException(404, f"conector desconocido: {kind}")
    asyncio.create_task(authenticate(kind))
    return {"ok": True, "detalle": "device flow disparado; revisa el log del server para el codigo"}


@router.get("/scoring")
async def pesos():
    return load_weights()


@router.put("/scoring")
async def guardar_pesos(body: dict):
    actual = load_weights()
    if set(body.get("weights", {})) != set(actual["weights"]):
        raise HTTPException(422, "weights debe traer exactamente los factores existentes")
    try:
        pesos = {k: float(v) for k, v in body["weights"].items()}
    except (TypeError, ValueError) as e:
        raise HTTPException(422, "los pesos deben ser numeros") from e
    if not all(math.isfinite(v) for v in pesos.values()):
        raise HTTPException(422, "los pesos deben ser finitos (ni NaN ni infinito)")
    actual["weights"] = pesos
    # escritura atomica: temporal + replace (un fallo a mitad no corrompe el yaml)
    tmp = DEFAULT_WEIGHTS_PATH.with_suffix(".tmp")
    tmp.write_text(yaml.safe_dump(actual, sort_keys=False, allow_unicode=True))
    os.replace(tmp, DEFAULT_WEIGHTS_PATH)
    async with SessionLocal() as s:
        await rescore_abiertas(s)
        await s.commit()
    return actual
