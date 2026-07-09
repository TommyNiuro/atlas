"""Seed idempotente de areas, clientes y proyectos desde config/*.yaml.

Uso: uv run python -m atlas.db.seed
"""
import asyncio
from pathlib import Path

import yaml
from sqlalchemy import select

from atlas.db.models import Area, Client, Project
from atlas.db.session import SessionLocal

REPO_ROOT = Path(__file__).resolve().parents[5]  # .../apps/api/src/atlas/db -> raiz
CFG = REPO_ROOT / "config"


def _load(nombre: str, clave: str) -> list:
    data = yaml.safe_load((CFG / nombre).read_text()) or {}
    return data.get(clave) or []


async def seed() -> None:
    areas = _load("areas.yaml", "areas")
    clientes = _load("clients.yaml", "clients")
    proyectos = _load("projects.yaml", "projects")

    async with SessionLocal() as s:
        ex_a = set((await s.scalars(select(Area.name))).all())
        s.add_all([Area(name=n) for n in areas if n not in ex_a])
        ex_c = set((await s.scalars(select(Client.name))).all())
        s.add_all([Client(name=n) for n in clientes if n not in ex_c])
        await s.flush()

        area_id = {a.name: a.id for a in (await s.scalars(select(Area))).all()}
        cli_id = {c.name: c.id for c in (await s.scalars(select(Client))).all()}
        ex_p = set((await s.scalars(select(Project.name))).all())
        for p in proyectos:
            extra = p if isinstance(p, dict) else {"name": p}
            if extra["name"] in ex_p:
                continue
            s.add(Project(name=extra["name"], area_id=area_id.get(extra.get("area")),
                          client_id=cli_id.get(extra.get("cliente"))))
        await s.commit()
        print(f"Seed: {len(areas)} areas, {len(clientes)} clientes, {len(proyectos)} proyectos (idempotente)")


if __name__ == "__main__":
    asyncio.run(seed())
