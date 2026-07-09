"""Sync manual de un conector: pull incremental -> RawItems en la base.

Uso:
    uv run python -m atlas.connectors.sync outlook_mail --auth   # primera vez
    uv run python -m atlas.connectors.sync outlook_mail          # sync
"""
import asyncio
import json
import sys
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from atlas.core import crypto, embeddings
from atlas.connectors import outlook  # noqa: F401 - registra el conector
from atlas.connectors.base import REGISTRY, SyncResult
from atlas.db.models import RawItem, Source
from atlas.db.session import SessionLocal


def _decrypt_meta(meta: dict | None) -> dict:
    if not meta:
        return {}
    return json.loads(crypto.decrypt(meta["fernet"]))


def _encrypt_meta(meta: dict) -> dict:
    return {"fernet": crypto.encrypt(json.dumps(meta))}


async def get_or_create_source(session, kind: str) -> Source:
    src = await session.scalar(select(Source).where(Source.kind == kind))
    if not src:
        src = Source(kind=kind, status="paused")  # paused hasta autenticar
        session.add(src)
        await session.flush()
    return src


async def authenticate(kind: str) -> None:
    connector = REGISTRY[kind]()
    auth_meta = await connector.authenticate()
    async with SessionLocal() as session:
        src = await get_or_create_source(session, kind)
        src.auth_meta = _encrypt_meta(auth_meta)
        src.status = "active"
        await session.commit()
    print(f"{kind}: autenticado y activo")


async def run_sync(kind: str) -> SyncResult:
    result = SyncResult(kind=kind)
    async with SessionLocal() as session:
        src = await get_or_create_source(session, kind)
        connector = REGISTRY[kind](_decrypt_meta(src.auth_meta))
        try:
            items, cursor = await connector.pull_incremental(src.sync_cursor)
        except Exception as e:
            src.status = "error"
            await session.commit()
            result.errors.append(str(e))
            return result
        result.pulled = len(items)

        # idempotencia: external_id ya visto = no-op
        vistos = set(
            (
                await session.scalars(
                    select(RawItem.external_id).where(
                        RawItem.source_id == src.id,
                        RawItem.external_id.in_([i.external_id for i in items]),
                    )
                )
            ).all()
        )
        nuevos = [i for i in items if i.external_id not in vistos]

        vectores = await embeddings.embed([i.text for i in nuevos]) if nuevos else None
        for idx, item in enumerate(nuevos):
            stmt = (
                pg_insert(RawItem)
                .values(
                    source_id=src.id,
                    user_id=src.user_id,
                    external_id=item.external_id,
                    kind=item.kind,
                    payload=item.payload,
                    embedding=vectores[idx] if vectores else None,
                    occurred_at=item.occurred_at,
                )
                .on_conflict_do_nothing(index_elements=["source_id", "external_id"])
            )
            await session.execute(stmt)
        result.created = len(nuevos)

        # el token cache de MSAL puede rotar durante el pull
        if connector.auth_meta:
            src.auth_meta = _encrypt_meta(connector.auth_meta)
        src.sync_cursor = cursor
        src.last_sync_at = datetime.now(timezone.utc)
        src.status = "active"
        await session.commit()
    return result


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in REGISTRY:
        print(f"Uso: python -m atlas.connectors.sync <{'|'.join(REGISTRY)}> [--auth]")
        sys.exit(1)
    kind = sys.argv[1]
    if "--auth" in sys.argv:
        asyncio.run(authenticate(kind))
    else:
        r = asyncio.run(run_sync(kind))
        print(f"{r.kind}: {r.pulled} traidos, {r.created} nuevos, errores: {r.errors or 'no'}")
        if r.errors:
            sys.exit(1)


if __name__ == "__main__":
    main()
