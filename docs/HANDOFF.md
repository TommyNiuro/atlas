# Atlas · Prompt de continuación (handoff para otro chat)

Copia todo lo de abajo (desde "Contexto") en un chat nuevo de Claude Code abierto en `~/atlas` para seguir con lo que falta.

---

## Contexto

Estás trabajando en **Atlas**, un "Personal Operating System" local-first y open source: extrae, clasifica y prioriza tareas automáticamente desde los canales reales de Tomás (Outlook, Slack, Granola, HubSpot, GitHub, Drive) con agentes Claude y un Priority Engine determinista. Cero captura manual.

- **Repo:** `/Users/enderys/atlas` · **GitHub:** https://github.com/TommyNiuro/atlas (público, cuenta TommyNiuro) · licencia MIT.
- **Specs (leer antes de tocar):** `docs/Requerimiento_Tecnico_v1.md` (arquitectura completa, 9 agentes, 7 conectores), `docs/Plan_de_Construccion.md` (8 bloques 0-7), `docs/Recomendaciones_Prototipo.md`, y `docs/AUDITORIA-2026-07-09.md` (auditoría + qué se resolvió/deferió).
- **Estado:** MVP completo (bloques 0 a 4) + auditoría corregida al 100% dentro del alcance "app perfecta" + app nativa. 20 tests en verde. Última release v0.6.0.

## Cómo está desplegado (en la Mac de Tomás)

- **App nativa Tauri/WebKit** en `/Applications/Atlas.app` (binario `atlas-desktop`, no es Chrome). El launcher Rust (`src-tauri/src/main.rs`) asegura los servicios y navega a `localhost:3005`. Reconstruir: `scripts/build-desktop.sh`.
- **Servicios launchd** (KeepAlive, auto-arranque): `io.niuro.atlas.api` (FastAPI :8000, wrapper `scripts/atlas-api.sh` que levanta colima+compose), `io.niuro.atlas.web` (Next :3005), `io.niuro.atlas.sync` (horario), `io.niuro.atlas.backup` (pg_dump diario). Plists en `~/Library/LaunchAgents/`.
- **Postgres 16 + pgvector y Redis 7** en Docker vía **colima**. Logs en `~/atlas/logs/`.
- **Agentes = tu suscripción Claude Max vía CLI** (`claude -p`), sin API key. Backend en `apps/api/src/atlas/agents/runtime.py` (`ATLAS_LLM_BACKEND=cli|api`, `CLAUDE_BIN` en `.env`).
- Tras cambiar código: `scripts/update-app.sh` (rebuild web + reinicia servicios). Tras cambiar el launcher Rust: `scripts/build-desktop.sh`.

## Stack y arquitectura

Monorepo. `apps/web` (Next.js 15, un `page.tsx` con las vistas Hoy/Sugerencias/Settings + command palette). `apps/api` (FastAPI, Python 3.12/uv):
- `connectors/` (base.py = interfaz Connector + registry; outlook.py, outlook_calendar.py, sync.py). `agents/` (runtime.py, orchestrator.py = pipeline en código puro, schemas.py, prompts/*.md). `scoring/engine.py` (fórmula determinista, pesos en `config/scoring.yaml`). `routers/` (tasks.py, settings.py). `db/` (models.py = 11 entidades, seed.py). `ws.py` (LISTEN/NOTIFY → WebSocket).
- Comandos: `task dev|migrate|seed|sync|pipeline|auth-outlook|auth-calendar`. Tests: `cd apps/api && uv run pytest`. Lint: `uv run ruff check`.

## Convenciones (importante)

- **Ponytail**: la solución más simple que funciona, diff mínimo, sin sobre-ingeniería. Reusar antes de escribir.
- **Español, sin guión largo (—)**, sin inventar datos.
- **Sin subagentes/workflows caros** salvo que Tomás lo pida (la auditoría con 27 agentes costó mucho): edits directos, batch, tests+lint por tanda, commit+push por tanda.
- Cada cambio: `uv run ruff check --fix . && uv run pytest`, luego commit con `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` y push. Modelos pineados en `config.py` (`claude-haiku-4-5` volumen, `claude-sonnet-5` priorizador).

## Prerequisitos humanos (bloquean datos reales, son de Tomás)

1. **Microsoft**: el device flow con el client ID público de Graph quedó pendiente de **admin consent del tenant niuro.io**. Cuando lo aprueben (o registren app propia en Entra ID con permisos `Mail.Read`+`Calendars.Read` y pongan `MS_CLIENT_ID` en `.env`), correr `task auth-outlook` y `task auth-calendar`.
2. **Credenciales de los conectores nuevos**: Slack user token, HubSpot private app token, Granola (MCP), GitHub PAT. Sin ellas los conectores se construyen pero no autentican.
3. Opcional: `VOYAGE_API_KEY` en `.env` (solo mejora la dedup semántica; sin ella todo funciona).
4. Poblar `config/clients.yaml` y `config/projects.yaml` con los clientes/proyectos reales (habilita clasificación por cliente y `context_bonus`), luego `task seed`.

## Lo que falta (bloques 5-7 del plan) — ordena por lo que Tomás priorice

**Bloque 5 · Las demás fuentes** (cada una implementa la interfaz `Connector` de `connectors/base.py`, se registra con `@register`, y trae tests con respuestas grabadas tipo respx):
- **Slack** (user token, scopes de history/search; leer DMs, menciones y canales de `config/channels.yaml`).
- **Granola** vía su MCP oficial (SDK `mcp` de Python, streamable HTTP, `list_meetings` desde `last_sync_at`; acuerdos donde el responsable es Tomás → tareas, de otros → seguimientos).
- **HubSpot** (private app token, deals con actividad reciente; + regla en SQL: deal en negociación sin actividad en 5 días → follow-up, sin gastar tokens).
- Verificar cada uno de punta a punta antes del siguiente. GitHub y Drive quedan para el final (menor volumen).

**Bloque 6 · Planificación y aprendizaje:**
- **Agente 8 Planificador diario** (7:00): ranking + huecos de calendario → `TimeBlock` origin='ai_proposed'; endpoint aceptar/mover/descartar; drag&drop en el front. Atlas propone, no escribe en el calendario. La entidad `TimeBlock` ya está migrada, sin usar.
- **Agente 5 Resúmenes** (hilos/transcripciones → 3-5 líneas).
- **Loop de aprendizaje semanal** (`agents/learning.py`): sacar 4-8 ejemplos de correcciones (`user_feedback`/`task_event`) e inyectarlos como few-shots en los prompts 1-3 (agregar un placeholder `{few_shots}` que `call_agent` sustituya). Hoy `UserFeedback` solo se escribe.
- Vista Proyectos/Clientes conectada (endpoint de detalle con último contacto y deals).
- Atlas como MCP server local (FastMCP montado en la app).

**Bloque 7 · Reportería y analítica:**
- Agentes 6 (Reportería, PDF WeasyPrint + XLSX openpyxl semanal con marca Niuro) y 7 (Productividad, insights 30d). Endpoints `GET /api/analytics` (Focus/Burnout Score con fórmula visible) y `GET /api/reports/{semana}.pdf|.xlsx`. Vistas Analytics y Reporte semanal en el front (hoy solo hay Hoy/Sugerencias/Settings). Voz en el command palette (Web Speech API). Vista móvil de solo lectura.

**Regla de presupuesto pendiente** (`runtime.py`): cuando existan los agentes 5-9, al cruzar el 80% del presupuesto deshabilitarlos y dejar solo 1-4 hasta el 100% (hoy solo hay corte al 100% y el aviso al 80%).

## Deudas menores deferidas (bajo impacto, ver AUDITORIA sección "Deferido")

Rate limiter dedicado por conector (aiolimiter), contador de 2 fallos consecutivos con badge, borrado de RawItem en `@removed`, búsqueda de tareas y voz en el command palette, drawer responsive móvil, cifrado del `sync_cursor`, detalle de proyectos con deals (necesita CRM del bloque 5).

## Primer paso sugerido

Preguntar a Tomás cuál de los conectores del bloque 5 quiere primero (Slack suele ser el de mayor señal), o si prefiere el planificador diario del bloque 6. Luego implementarlo end-to-end sobre la interfaz existente, con su test, y verificarlo antes de seguir.
