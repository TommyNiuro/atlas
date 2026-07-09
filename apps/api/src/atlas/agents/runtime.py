"""Agent Runtime: llamadas a la API de Anthropic con presupuesto diario,
un reintento y validacion Pydantic. La orquestacion es codigo; solo la
interpretacion usa modelo."""
import json
import logging
from datetime import date
from pathlib import Path
from typing import TypeVar

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from atlas.core import config

log = logging.getLogger("atlas.agents")
PROMPTS = Path(__file__).parent / "prompts"

T = TypeVar("T", bound=BaseModel)

_client: AsyncAnthropic | None = None
# ponytail: contador en memoria como fallback si redis no esta; el proceso de
# sync es uno solo y corto, con redis compartimos el presupuesto entre corridas
_local_spent = {"input": 0, "output": 0}


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic()
    return _client


async def _budget_spent() -> tuple[int, int]:
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(config.REDIS_URL)
        key = f"atlas:tokens:{date.today().isoformat()}"
        vals = await r.hmget(key, "input", "output")
        await r.aclose()
        return int(vals[0] or 0), int(vals[1] or 0)
    except Exception:
        return _local_spent["input"], _local_spent["output"]


async def _budget_add(inp: int, out: int) -> None:
    _local_spent["input"] += inp
    _local_spent["output"] += out
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(config.REDIS_URL)
        key = f"atlas:tokens:{date.today().isoformat()}"
        await r.hincrby(key, "input", inp)
        await r.hincrby(key, "output", out)
        await r.expire(key, 60 * 60 * 48)
        await r.aclose()
    except Exception:
        pass


class BudgetExceeded(RuntimeError):
    pass


async def check_budget() -> None:
    inp, out = await _budget_spent()
    if inp >= config.TOKEN_BUDGET_INPUT_DAILY or out >= config.TOKEN_BUDGET_OUTPUT_DAILY:
        raise BudgetExceeded(f"Presupuesto diario agotado: {inp} in / {out} out")


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text.removeprefix("json").strip()
    return json.loads(text)


async def call_agent(prompt_name: str, payload: dict, schema: type[T], model: str) -> T | None:
    """Corre un agente: prompt versionado + datos como JSON, salida validada.

    El contenido de fuentes externas viaja envuelto como datos, nunca como
    instrucciones (mitigacion de prompt injection del requerimiento).
    """
    await check_budget()
    system = (PROMPTS / f"{prompt_name}.md").read_text()
    user = (
        "<datos>\n"
        + json.dumps(payload, ensure_ascii=False, default=str)
        + "\n</datos>\n\nResponde SOLO con JSON válido según el esquema indicado."
    )
    client = _get_client()
    messages = [{"role": "user", "content": user}]
    for intento in (1, 2):
        resp = await client.messages.create(
            model=model, max_tokens=2048, system=system, messages=messages
        )
        await _budget_add(resp.usage.input_tokens, resp.usage.output_tokens)
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            return schema.model_validate(_parse_json(text))
        except Exception as e:  # noqa: BLE001 - reintento unico y descarte con log
            if intento == 1:
                messages = messages + [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": f"Tu salida no validó ({e}). Corrígela: responde SOLO el JSON."},
                ]
            else:
                log.warning("agente %s descartado tras 2 intentos: %s", prompt_name, e)
    return None
