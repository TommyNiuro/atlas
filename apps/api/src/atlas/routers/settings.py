"""Settings: estado de conectores y editor de pesos del scoring (el ranking
se recalcula al guardar)."""
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


@router.get("/scoring")
async def pesos():
    return load_weights()


@router.put("/scoring")
async def guardar_pesos(body: dict):
    actual = load_weights()
    if set(body.get("weights", {})) != set(actual["weights"]):
        raise HTTPException(422, "weights debe traer exactamente los factores existentes")
    actual["weights"] = {k: float(v) for k, v in body["weights"].items()}
    DEFAULT_WEIGHTS_PATH.write_text(yaml.safe_dump(actual, sort_keys=False, allow_unicode=True))
    async with SessionLocal() as s:
        await rescore_abiertas(s)
        await s.commit()
    return actual
