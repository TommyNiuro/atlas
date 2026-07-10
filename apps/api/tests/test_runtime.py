"""Resiliencia del runtime de agentes (regresión de la auditoría)."""
import asyncio

from atlas.agents import runtime
from atlas.agents.schemas import ExtractorOut
from atlas.core import config


def test_fallo_backend_no_revienta_el_batch(monkeypatch):
    # un fallo del CLI (timeout, returncode, sin login) descarta SOLO esta tarea
    monkeypatch.setattr(config, "LLM_BACKEND", "cli")

    async def boom(*a, **k):
        raise RuntimeError("claude sin login")

    monkeypatch.setattr(runtime, "_call_cli", boom)

    async def _sin_budget():  # aisla del contador diario real en Redis (compartido con la app)
        return None

    monkeypatch.setattr(runtime, "check_budget", _sin_budget)
    out = asyncio.run(runtime.call_agent("extractor", {"x": 1}, ExtractorOut, "m"))
    assert out is None  # se descarta, no propaga
