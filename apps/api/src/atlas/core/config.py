import os
import uuid

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://atlas:atlas@localhost:5432/atlas"
)

# user_id presente en todas las tablas desde la migracion 001 (seccion 17 del
# requerimiento): multi-tenancy despues es agregar auth, no re-modelar datos.
DEFAULT_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
