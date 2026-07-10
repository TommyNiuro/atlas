import os
import uuid
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[5]
load_dotenv(REPO_ROOT / ".env")

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://atlas:atlas@localhost:5432/atlas"
)

MS_CLIENT_ID = os.environ.get("MS_CLIENT_ID", "")
MS_TENANT_ID = os.environ.get("MS_TENANT_ID", "common")
SLACK_TOKEN = os.environ.get("SLACK_TOKEN", "")
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY", "")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Modelos pineados (riesgo 8 del requerimiento: la version se fija en config).
# La spec pedia claude-sonnet-4-6 para el Priorizador; claude-sonnet-5 es su sucesor.
MODEL_FAST = os.environ.get("ATLAS_MODEL_FAST", "claude-haiku-4-5")
MODEL_SMART = os.environ.get("ATLAS_MODEL_SMART", "claude-sonnet-5")

# Backend de LLM: "cli" usa el CLI de Claude Code con la suscripcion (Max/Pro)
# del usuario, sin API key; "api" usa ANTHROPIC_API_KEY. Default: cli si no hay key.
LLM_BACKEND = os.environ.get(
    "ATLAS_LLM_BACKEND", "api" if os.environ.get("ANTHROPIC_API_KEY") else "cli"
)
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "")

# Presupuesto diario de tokens (regla dura 4 del runtime)
TOKEN_BUDGET_INPUT_DAILY = int(os.environ.get("TOKEN_BUDGET_INPUT_DAILY", "500000"))
TOKEN_BUDGET_OUTPUT_DAILY = int(os.environ.get("TOKEN_BUDGET_OUTPUT_DAILY", "80000"))

# user_id presente en todas las tablas desde la migracion 001 (seccion 17 del
# requerimiento): multi-tenancy despues es agregar auth, no re-modelar datos.
DEFAULT_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
