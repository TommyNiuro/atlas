"""Seed: carga las areas de trabajo desde config/areas.yaml. Idempotente.

Uso: uv run python -m atlas.db.seed
"""
import asyncio
from pathlib import Path

import yaml
from sqlalchemy import select

from atlas.db.models import Area
from atlas.db.session import SessionLocal

REPO_ROOT = Path(__file__).resolve().parents[5]  # .../apps/api/src/atlas/db -> raiz


async def seed() -> None:
    areas = yaml.safe_load((REPO_ROOT / "config" / "areas.yaml").read_text())["areas"]
    async with SessionLocal() as session:
        existing = set((await session.scalars(select(Area.name))).all())
        nuevas = [Area(name=n) for n in areas if n not in existing]
        session.add_all(nuevas)
        await session.commit()
        print(f"Areas: {len(nuevas)} creadas, {len(existing)} ya existian")


if __name__ == "__main__":
    asyncio.run(seed())
