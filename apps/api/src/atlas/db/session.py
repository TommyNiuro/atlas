from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.core.config import DATABASE_URL

# ponytail: NullPool porque cada CLI/test usa su propio event loop y las
# conexiones pooled del loop anterior revientan; app mono-usuario local,
# el costo de conectar por sesion es despreciable. Pool real si algun dia
# hay carga de verdad.
engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
