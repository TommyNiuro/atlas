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
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY", "")

# user_id presente en todas las tablas desde la migracion 001 (seccion 17 del
# requerimiento): multi-tenancy despues es agregar auth, no re-modelar datos.
DEFAULT_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
