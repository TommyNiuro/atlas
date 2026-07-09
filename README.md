# Atlas · Personal Operating System

Atlas centraliza automáticamente las responsabilidades de un ejecutivo que opera en 6+ canales (Outlook, Slack, Granola, HubSpot, GitHub, Google Drive). El principio número uno: **cero captura manual**. Tú trabajas; los agentes de IA detectan, extraen, clasifican y priorizan las tareas.

Local-first y open source: tus datos viven en tu computador, nada se sube a servidores de terceros.

> Atlas automatically centralizes an executive's responsibilities across 6+ channels. Local-first, open source, powered by Claude agents. Docs are in Spanish.

## Qué es y qué no es

| Es | No es |
|----|-------|
| Un motor de extracción de tareas desde canales reales | Otra app de to-dos con captura manual |
| Un sistema de scoring de prioridad configurable y explicable | Un tablero kanban con etiquetas Alta/Media/Baja |
| Local-first: los datos viven en tu máquina | Un SaaS que guarda tu correo en servidores de terceros |
| Agentes especializados que colaboran | Un solo prompt gigante que hace todo |

## Estado

**En construcción, Bloque 0 (esqueleto).** El roadmap completo vive en [docs/Plan_de_Construccion.md](docs/Plan_de_Construccion.md) y la especificación en [docs/Requerimiento_Tecnico_v1.md](docs/Requerimiento_Tecnico_v1.md).

- [x] Bloque 0: monorepo, Docker Compose (Postgres+pgvector, Redis), FastAPI `/health`, Next.js con el prototipo de diseño, CI
- [x] Bloque 1: modelo de datos (11 entidades con `user_id` desde el día uno, Alembic, índices GIN/ivfflat/B-tree, cifrado Fernet, seed de áreas)
- [x] Bloque 2: conector Outlook de punta a punta (interfaz `Connector`, device code flow, delta queries, filtro de newsletters, embeddings Voyage, sync idempotente)
- [ ] Bloque 3: motor de agentes (Extractor, Clasificador, Priorizador, Seguimiento) + Priority Engine
- [ ] Bloque 4: app visible con datos reales (MVP)
- [ ] Bloques 5-7: Slack, Granola, HubSpot, planificación, aprendizaje, reportería

## Requisitos

- macOS 13+ (Intel o Apple Silicon) o Windows 10/11 de 64 bits
- Docker (OrbStack o Colima en Mac, Docker Desktop + WSL2 en Windows)
- Node 22+ con pnpm, Python 3.12 vía [uv](https://docs.astral.sh/uv/), [go-task](https://taskfile.dev)

## Instalación

### macOS

```bash
brew install uv pnpm go-task colima docker
git clone https://github.com/TommyNiuro/atlas.git && cd atlas
python3 scripts/setup.py     # detecta el SO, llave Fernet al Keychain, deps
task dev                     # stack completo: web en :3000, api en :8000
```

### Windows (PowerShell)

```powershell
winget install astral-sh.uv pnpm.pnpm Docker.DockerDesktop Task.Task Git.Git
git clone https://github.com/TommyNiuro/atlas.git; cd atlas
python scripts\setup.py      # llave Fernet al Credential Locker (DPAPI)
task dev
```

Abre `http://localhost:3000` (dashboard) y `http://localhost:8000/health` (api).

## Estructura

```
apps/web        Next.js 15 (por ahora sirve el prototipo de diseño)
apps/api        FastAPI (Python 3.12, uv)
config/         scoring.yaml (pesos del Priority Engine), areas.yaml, channels.yaml
infra/          docker-compose (postgres 16 + pgvector, redis 7)
scripts/        setup.py multiplataforma
docs/           requerimiento técnico, plan de construcción, handoff de diseño
```

## Seguridad local

- API y web solo escuchan en `127.0.0.1`.
- Los tokens OAuth se cifran con Fernet; la llave maestra vive en el almacén nativo del sistema (Keychain / Credential Locker) vía `keyring`, nunca en `.env`.
- El contenido de fuentes externas jamás se interpola en prompts como instrucciones: siempre delimitado como datos.

## Licencia

[MIT](LICENSE)
