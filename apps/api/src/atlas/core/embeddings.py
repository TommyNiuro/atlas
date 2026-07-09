"""Embeddings con Voyage AI. Sin VOYAGE_API_KEY devuelve None (el pipeline
sigue funcionando, solo sin dedup semantico)."""
import httpx

from atlas.core import config
from atlas.db.models import EMBEDDING_DIMS

VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL = "voyage-3.5-lite"


async def embed(texts: list[str]) -> list[list[float]] | None:
    if not config.VOYAGE_API_KEY or not texts:
        return None
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            VOYAGE_URL,
            headers={"Authorization": f"Bearer {config.VOYAGE_API_KEY}"},
            json={"input": texts, "model": VOYAGE_MODEL, "output_dimension": EMBEDDING_DIMS},
        )
        r.raise_for_status()
        return [d["embedding"] for d in r.json()["data"]]
