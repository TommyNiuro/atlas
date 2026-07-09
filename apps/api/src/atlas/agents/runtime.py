"""Agent Runtime: presupuesto diario, un reintento y validacion Pydantic.
Dos backends: el CLI de Claude Code (suscripcion Max/Pro del usuario, sin API
key; patron probado en el CRM de Niuro) o la API de Anthropic. La orquestacion
es codigo; solo la interpretacion usa modelo."""
import asyncio
import json
import logging
import os
import shutil
from datetime import date
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from atlas.core import config

log = logging.getLogger("atlas.agents")
PROMPTS = Path(__file__).parent / "prompts"

T = TypeVar("T", bound=BaseModel)

_client = None
# ponytail: contador en memoria como fallback si redis no esta; el proceso de
# sync es uno solo y corto, con redis compartimos el presupuesto entre corridas
_local_spent = {"input": 0, "output": 0}


def _get_client():
    global _client
    if _client is None:
        from anthropic import AsyncAnthropic

        _client = AsyncAnthropic()
    return _client


def _claude_bin() -> str:
    # env CLAUDE_BIN -> PATH -> ruta tipica de nvm (leccion del CRM: el symlink
    # de nvm cambia al actualizar Node, mejor resolver en runtime)
    return (
        config.CLAUDE_BIN
        or shutil.which("claude")
        or os.path.expanduser("~/.claude/local/claude")
    )


async def _call_cli(system: str, user: str, model: str) -> tuple[str, dict]:
    """Corre `claude -p` con la suscripcion del usuario. Env CLAUDE_*/CLAUDECODE
    purgado (heredarlo desde otro proceso de Claude infla el contexto, leccion
    del CRM) y sin tools ni settings: solo texto -> JSON."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k != "CLAUDECODE" and not k.startswith("CLAUDE_")
    }
    binario = _claude_bin()
    env["PATH"] = f"{os.path.dirname(binario)}:{env.get('PATH', '')}"
    proc = await asyncio.create_subprocess_exec(
        binario, "-p", "--output-format", "json", "--input-format", "text",
        "--model", model, "--dangerously-skip-permissions", "--tools", "",
        "--strict-mcp-config", "--setting-sources", "", "--disable-slash-commands",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, env=env,
    )
    prompt = f"{system}\n\n{user}"
    out, err = await asyncio.wait_for(proc.communicate(prompt.encode()), timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(f"claude CLI fallo ({proc.returncode}): {err.decode()[:300]}")
    data = json.loads(out.decode())
    usage = data.get("usage") or {}
    return data.get("result", ""), usage


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
    correccion = ""
    for intento in (1, 2):
        if config.LLM_BACKEND == "cli":
            text, usage = await _call_cli(system, user + correccion, model)
            await _budget_add(usage.get("input_tokens", 0), usage.get("output_tokens", 0))
        else:
            client = _get_client()
            resp = await client.messages.create(
                model=model, max_tokens=2048, system=system,
                messages=[{"role": "user", "content": user + correccion}],
            )
            await _budget_add(resp.usage.input_tokens, resp.usage.output_tokens)
            text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            return schema.model_validate(_parse_json(text))
        except Exception as e:  # noqa: BLE001 - reintento unico y descarte con log
            if intento == 1:
                correccion = (
                    f"\n\nTu salida anterior fue:\n{text}\n"
                    f"No validó ({e}). Responde SOLO el JSON corregido."
                )
            else:
                log.warning("agente %s descartado tras 2 intentos: %s", prompt_name, e)
    return None
