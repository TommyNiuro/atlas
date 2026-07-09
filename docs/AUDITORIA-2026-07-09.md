# Auditoría Atlas · qué falta para que funcione perfecto

**Fecha:** 2026-07-09  
**Método:** workflow multi-agente (9 auditores en paralelo + verificación adversarial de los críticos + síntesis).  
**Cobertura:** 76 hallazgos crudos, 16 bugs críticos confirmados, 1 descartado.

> Los bugs marcados bloqueante/alta pasaron por una segunda pasada de verificación (un agente escéptico releyó el código citado). El detalle completo, hallazgo por hallazgo con archivo:línea, está al final.

---

## Resumen

La app está a un bug bloqueante de arrancar: el CORS apunta al puerto 3000 pero la web corre en 3005, así que hoy el navegador no puede hablar con la API (nada carga). Detrás de eso el motor de scoring está medio muerto (6 de sus factores se calculan en 0 o se corrompen tras el primer sync) y el pipeline de agentes es frágil (una sola respuesta mala del CLI aborta todo el batch). Las 3 urgencias: (1) arreglar CORS, (2) verificar que los IDs de modelo existen (si no, el motor entero 404ea), (3) blindar el batch de agentes y el scoring para que un sync no degrade las tareas.

## Top 5 acciones inmediatas

1. **CORS bloquea todo el navegador.** La API solo permite origin :3000 y la web sirve en :3005, todas las llamadas mueren. `apps/api/src/atlas/main.py:23`. Arreglo: `allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+"` (local, no se vuelve a romper). Esfuerzo: S.
2. **IDs de modelo sin verificar.** `claude-sonnet-5` / `claude-haiku-4-5` pueden 404ear y tumbar el motor completo. `apps/api/src/atlas/core/config.py:22`. Arreglo: confirmar los ids vigentes y fijarlos, con fallo temprano legible. Esfuerzo: S (verificá esto primero, es 1 minuto y define si algo funciona).
3. **El conector de calendario usa scope Mail.Read, no Calendars.Read.** calendarView da 403, el calendario nunca entra. `apps/api/src/atlas/connectors/outlook_calendar.py:14`. Arreglo: SCOPES como atributo de clase (`['Calendars.Read']` en la subclase) y que auth lo use. Esfuerzo: S.
4. **Un fallo del CLI aborta TODO el batch.** Timeout, returncode!=0, JSON malformado o `claude` sin login mata la generación de todas las tareas. `apps/api/src/atlas/agents/runtime.py:137`. Arreglo: envolver la llamada en try/except dentro del loop, reintentar una vez y si persiste `return None`; dejar BudgetExceeded propagando. Esfuerzo: M.
5. **El scoring se derrumba al rescoring.** `eisenhower_factor` no se persiste y la tarea pierde hasta ~10.7 pts tras el primer sync. `apps/api/src/atlas/agents/orchestrator.py:205`. Arreglo: persistir urgente/importante (columnas en Task o reconstruir del breakdown como impact_factor) y pasarlos al Facts de rescore. Esfuerzo: M.

Bonus visible: el sync horario crea tareas **sin emitir NOTIFY**, así que el dashboard nunca se actualiza en vivo (`orchestrator.py:159`, S). Un `NOTIFY atlas_tasks` en un helper compartido lo resuelve y de paso cubre todo path que mute tareas.

## Bugs a arreglar

| Hallazgo | Archivo | Severidad | Esfuerzo |
|---|---|---|---|
| CORS :3000 vs :3005 bloquea el navegador | main.py:23 | bloqueante | S |
| Scope Mail.Read en calendario (403) | connectors/outlook_calendar.py:14 | alta | S |
| Fallo del CLI aborta el batch entero | agents/runtime.py:137 | alta | M |
| eisenhower_factor se corrompe en rescore (-10.7 pts) | agents/orchestrator.py:205 | alta | M |
| Sync horario no emite NOTIFY (dashboard no refresca) | agents/orchestrator.py:159 | alta | S |
| Ventana de 14 días del calendario congelada, eventos futuros no entran | connectors/outlook_calendar.py:16 | alta | M |
| pareto_factor nunca se alimenta (10 pts en 0) | agents/orchestrator.py:146 | media | S |
| context_bonus nunca se calcula (4 pts muertos) | agents/orchestrator.py:205 | media | M |
| carga_del_dia no llega al scoring (penalty -10 nunca aplica) | agents/orchestrator.py:205 | media | M |
| frog_factor siempre 0 (veces_pospuesta no se cuenta) | agents/orchestrator.py:205 | media | S |
| rescore reconstruye impacto de forma lossy / resetea impacto=0 a 0.3 | agents/orchestrator.py:198 | media/baja | S-M |
| requester_factor hardcodeado en 0.6 | agents/orchestrator.py:149 | media | S (parche) |
| Agente Seguimiento nunca cambia el estado waiting | agents/orchestrator.py:172 | media | S |
| Triage merge no fusiona, ignora merge_into | routers/tasks.py:144 | media | M |
| Snooze no saca la tarea de Hoy | routers/tasks.py:214 | media | S |
| due_date inválido da 500 en vez de 422 | routers/tasks.py:142 | media | S |
| Triage sin precondición de estado (revierte tareas cerradas) | routers/tasks.py:124 | media | S |
| Timeout del CLI no mata el subproceso (procesos huérfanos) | agents/runtime.py:67 | media | S |
| Atajo 'g' hijackea toda tecla y salta a Hoy | web/app/page.tsx:242 | media | S |
| Errores de /api/suggestions se tragan (skeleton eterno) | web/app/page.tsx:206 | media | S |

Nota: casi todos los bugs de scoring viven en el mismo `rescore_abiertas` (`orchestrator.py:205`), que ya tiene las tareas en memoria. Conviene atacarlos en una sola pasada: es un fix concentrado, no siete.

## Robustez y producción

Aguanta pero es frágil. Ordenado por impacto:

- **Sin reintentos ni backoff ni 429 Retry-After** en los conectores: cualquier rate-limit o 5xx aborta el sync y marca la Source como error (`connectors/outlook.py:87`, M). Prioritario, es lo que va a romper en uso real.
- **Sin rate limiter por conector** (aiolimiter que pide el spec) (`connectors/base.py:27`, M).
- **health() nunca se invoca**: no hay detección de "2 syncs fallidos" ni badge (`connectors/sync.py:52`, M).
- **Items @removed/isCancelled no se borran** del RawItem, solo se saltan (`connectors/outlook.py:90`, M).
- **WebSocket sin reconexión**: una caída deja el dashboard mudo hasta recargar (`web/lib/api.ts`, S, ~8 líneas). El listener de PG además usa `get_event_loop()` deprecado y `conn` puede quedar sin asignar (`ws.py:47`, S).
- **Sin backup de Postgres**: los datos viven solo en el volumen docker (riesgo 9 del spec). Crear `scripts/backup.py` con pg_dump + rotación + launchd diario (`infra/docker-compose.yml:27`, S).
- **Sin notificaciones nativas** (conector caído, plan listo, presupuesto 80%): `run-sync.sh` traga fallos con `|| true` (`run-sync.sh:6-7`, M).
- **QUIET_HOURS es config muerta**: definido en .env, nunca leído, el sync corre 24/7 (`core/config.py:34`, S).
- **Sin catch-up de sync**: no corre al arrancar y launchd coalesce las corridas perdidas en una; poner `RunAtLoad=true` + sync desde el último timestamp (`io.niuro.atlas.sync.plist:11`, M).
- **Sin prompt caching** del contexto de usuario en el backend api: costo evitable en llamadas de alto volumen (`agents/runtime.py:142`, M).
- **Índice ivfflat mal dimensionado** (lists=100) y no usado por la query vectorial: a escala MVP, cambiarlo por HNSW o quitarlo (`db/models.py:59`, S).
- **/health no verifica DB/Redis** (`main.py:31`, S). **PUT /scoring** sin validación numérica y escritura no atómica (`settings.py:40`, S).
- **Seguridad barata pendiente**: gitleaks pre-commit ausente (S), `setup.py` no chequea FileVault (S), API sin auth ni chequeo de Origin en WS (baja, aceptable mientras el bind sea 127.0.0.1). sync_cursor en texto plano mientras auth_meta va cifrado (baja).
- **Puerto inconsistente** 3000/3005 en Taskfile/README vs deploy real (`Taskfile.yml:17`, S) y falta `scripts/update-app.sh` para reconstruir la web y reiniciar servicios tras cambios (S).

## Completar el MVP visible

Cosas que el MVP ya debería tener y hoy no están:

- **Sin endpoint de sync manual** (botón Cmd+Shift+S del spec): agregar `POST /api/sync` en background para las fuentes activas (`connectors/sync.py:52`, alta, M).
- **Tablas Client y Project nunca se pueblan**: la clasificación por cliente/proyecto está inerte. Sembrar con `config/clients.yaml`/`projects.yaml` idempotente o CRUD mínimo (`db/seed.py`, alta, M). Esto habilita context_bonus y el detalle de proyectos.
- **Faltan casi todos los atajos** (1-5, C, S, D, /, Cmd+Shift+S) y la vista Hoy no tiene selección (`web/app/page.tsx:227`, M). El chord G→H/P/A/R no existe (hoy 'g' hijackea, ver bugs).
- **Vista Proyectos/Clientes ausente** y `/projects` solo devuelve nombres+conteo; falta detalle con último contacto y deals (`routers/tasks.py:229`, M).
- **Sin búsqueda FTS** (atajo '/', <50ms): `GET /api/search` con websearch_to_tsquery en español (`routers/tasks.py`, M).
- **Sin endpoint de presupuesto**: el dato ya vive en Redis, exponer `GET /api/budget` (`routers/settings.py`, S).
- **Command palette incompleto**: sin voz, sin búsqueda de tareas, sin navegación por teclado en resultados (`web/app/page.tsx:166`, M).
- **UX del prototipo perdida**: sin toggle de tema/light mode (`globals.css:2`, M), fuentes del spec no cargan y el saludo cae a Georgia (`globals.css:31`, S), sidebar no pasa a drawer en móvil (`globals.css:34`, baja).
- **Falta re-auth de conector** `POST /api/sources/{kind}/reauth` (`routers/settings.py:15`, baja, S).

## Bloques 5-7 (roadmap)

Features grandes, agrupadas por bloque (no urgentes si se respeta el roadmap):

- **Conectores nuevos (L)**: Slack (user token + whitelist de canales), Granola (MCP streamable_http), HubSpot (REST v3), GitHub, Google Drive. Con HubSpot viene la regla "deal en negociación sin actividad en 5 días" por SQL. Empezar por Slack/Granola/HubSpot del MVP.
- **Agentes 5-9 (L)**: Resúmenes, Reportería, Productividad, Planificador diario/semanal. Cada uno: prompt versionado + schema Pydantic + entrada tipada (6/7 con SQL agregado, no texto crudo) + scheduling launchd. Al existir, conectar el **umbral de presupuesto al 80%** que hoy no está (`runtime.py:108`): deshabilitar agentes 5-9 y notificar, dejando 1-4 hasta el 100%.
- **Time blocking / agente 8 (L)**: leer ranking de TaskScore + eventos de calendario + energía aprendida y generar `TimeBlock` origin='ai_proposed' con endpoint aceptar/mover/descartar. Atlas propone, no escribe el calendario en MVP.
- **Loop de aprendizaje semanal (L)**: `agents/learning.py` que saque 4-8 ejemplos reales de TaskEvents de corrección y los inyecte en un placeholder `{few_shots}` de los prompts 1-3. Aquí se empieza a leer `UserFeedback` (hoy solo se escribe).
- **Reportería y Analytics (L)**: `GET /api/analytics` (Focus/Burnout 30d) y `GET /api/reports/{semana}.pdf|.xlsx`.
- **Scoring completo (L)**: `requester_factor` real desde remitente + mapa de scoring.yaml, y revenue del CRM para el pareto_factor. Entidades `TimeBlock`/`WeeklyReport` ya están migradas como pre-provisión, ok dejarlas con comentario hasta que su bloque las consuma.

## Tests y CI

No hay hallazgos de tests directos, pero los bugs que llegaron a producción marcan los huecos:

- **Scoring sin cobertura**: seis factores (pareto, context, carga, frog, eisenhower en rescore, requester) están en 0 o se corrompen y ningún test lo detectó. Falta un test de la fórmula que verifique que cada factor suma lo que debe con Facts conocidos, y un test de rescore que confirme que el score no baja tras un sync sin cambios.
- **Path de fallo del CLI sin test**: agregar un caso con returncode!=0 / JSON malformado que confirme que solo se pierde esa tarea, no el batch.
- **Config/puerto sin smoke test**: un chequeo de arranque que valide que los IDs de modelo resuelven y que el origin del front está en la whitelist de CORS habría atajado los dos peores bugs.
- **Semántica de estado sin test**: snooze saca de Hoy, triage merge fusiona, triage rechaza tareas cerradas, due_date inválido da 422.
- **CI**: no hay `.pre-commit-config.yaml`; agregar gitleaks y correr los tests en el hook o en CI para que estos huecos no se repitan.

## Veredicto

No está lejos de arrancar (1 fix de CORS y verificar los IDs de modelo y la app carga), pero sí lejos de "perfecto": el scoring está a medio cablear y el pipeline es frágil ante el primer fallo real. Orden recomendado: (1) CORS + IDs de modelo (10 min, define si algo funciona), (2) blindaje del batch de agentes y los 6 factores de scoring en la misma pasada de `orchestrator.py`, (3) NOTIFY + reconexión WS + retries/backoff para que el uso diario no se caiga, (4) sembrar Client/Project + endpoints faltantes (sync manual, budget, search) para cerrar el MVP visible, (5) backups y notificaciones antes de confiarle datos, (6) recién ahí los bloques 5-7.

---

## Detalle completo (todos los hallazgos)

- **[alta/bug/S]** (conectores) El conector de calendario autentica con scope Mail.Read, no Calendars.Read (calendarView da 403)
  - `apps/api/src/atlas/connectors/outlook_calendar.py:14`
  - Arreglo: Hacer que authenticate/get_access_token usen self.SCOPES en vez de la constante de modulo; poner SCOPES = ['Mail.Read'] como atributo de clase en OutlookMailConnector y ['Calendars.Read'] en la subclase.
- **[alta/bug/M]** (conectores) La ventana de 14 dias de calendarView queda congelada en el primer sync; eventos futuros nunca entran
  - `apps/api/src/atlas/connectors/outlook_calendar.py:16`
  - Arreglo: Re-baselinar periodicamente: descartar el cursor y rehacer el delta inicial con ventana movil (cada sync o cada N horas), o recalcular un rango deslizante en cada corrida en vez de confiar en el deltaLink para la ventana temporal.
- **[media/robustez/M]** (conectores) Sin reintentos ni backoff ni manejo de 429 Retry-After: cualquier rate-limit o 5xx aborta el sync completo
  - `apps/api/src/atlas/connectors/outlook.py:87`
  - Arreglo: Envolver las requests con reintentos (tenacity o loop propio) que respeten Retry-After en 429 y hagan backoff exponencial en 5xx; no marcar la Source como error por fallos transitorios.
- **[media/bug/S]** (agentes) El agente de Seguimiento nunca cambia el estado de la tarea waiting
  - `apps/api/src/atlas/agents/orchestrator.py:172`
  - Arreglo: En el bloque del for tid (orchestrator.py:172-177) setear t.status='open' (o 'done'/'in_progress' según la semántica deseada) además del TaskEvent, y registrar from/to en el detail.
- **[alta/robustez/M]** (agentes) Fallo del backend CLI (timeout, returncode!=0, JSON malformado, claude no logueado) aborta TODO el batch
  - `apps/api/src/atlas/agents/runtime.py:137`
  - Arreglo: Envolver la llamada al backend (runtime.py:137-147) en try/except dentro del for intento, tratándola igual que un fallo de validación: reintentar una vez y si persiste log.warning + return None. Dejar BudgetExceeded propagando.
- **[alta/bug/M]** (scoring) eisenhower_factor se derrumba en cada rescore: la tarea pierde hasta ~10.7 pts tras el primer sync
  - `apps/api/src/atlas/agents/orchestrator.py:205`
  - Arreglo: Persistir urgente/importante (columnas en Task, o reconstruir eisenhower_factor desde prev.score_breakdown igual que se hace con impact_factor) y pasarlos en el Facts de rescore_abiertas.
- **[media/bug/S]** (scoring) pareto_factor (estrategico) nunca se alimenta: 10 pts de la formula siempre valen 0
  - `apps/api/src/atlas/agents/orchestrator.py:146`
  - Arreglo: En creacion pasar estrategico=(clasif.tipo=='estrategico'); en rescore leer t.task_type=='estrategico'. (El spec ademas contempla revenue del CRM, eso queda para Bloque 5.)
- **[bloqueante/bug/S]** (api-backend) CORS bloquea al navegador: API solo permite :3000 pero la web corre en :3005
  - `apps/api/src/atlas/main.py:23`
  - Arreglo: Agregar 'http://localhost:3005' y 'http://127.0.0.1:3005' a allow_origins (o leerlos de env). Alternativa: allow_origin_regex para localhost. Alinear con el puerto real del deploy.
- **[media/bug/M]** (api-backend) Triage 'merge' no fusiona: ignora merge_into y solo descarta la tarea
  - `apps/api/src/atlas/routers/tasks.py:144`
  - Arreglo: En action=='merge': validar que existe la Task merge_into del mismo user, mover/copiar lo relevante (o al menos guardar merge_into en detail/after), marcar la origen como merged apuntando al destino y reflejarlo en el feedback. Hoy merge_into esta muerto.
- **[alta/bug/S]** (realtime) El sync horario crea tareas sin emitir NOTIFY: el dashboard no se actualiza en vivo
  - `apps/api/src/atlas/agents/orchestrator.py:159`
  - Arreglo: En orchestrator.procesar_pendientes(), antes del commit final (o en un commit posterior) ejecutar await session.execute(text("NOTIFY atlas_tasks, 'sync'")) cuando stats['tareas']+stats['sugeridas']>0. Mejor aun: mover _notify a un helper compartido (db/session o un notify.py) e invocarlo desde el orchestrator y el router para que ningun path que muta tareas se olvide.
- **[bloqueante/bug/S]** (realtime) CORS solo permite el puerto 3000, pero el front se sirve en 3005: todas las llamadas del navegador quedan bloqueadas
  - `apps/api/src/atlas/main.py:22`
  - Arreglo: Agregar http://localhost:3005 y http://127.0.0.1:3005 a allow_origins, o usar allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+" para no volver a romper si cambia el puerto.
- **[bloqueante/bug/S]** (frontend) CORS bloquea TODAS las llamadas del browser: el front corre en :3005 pero la API solo permite origin :3000
  - `apps/api/src/atlas/main.py:23`
  - Arreglo: Agregar 'http://localhost:3005' y 'http://127.0.0.1:3005' a allow_origins en main.py (o usar allow_origin_regex=r'http://(localhost|127.0.0.1):\d+' dado que todo es local). Alternativa: setear NEXT_PUBLIC_API_URL igual al origin y proxiar, pero el fix de CORS es el minimo.
- **[media/robustez/S]** (frontend) Errores de /api/suggestions se tragan: skeleton eterno sin retry ni mensaje
  - `apps/web/app/page.tsx:206`
  - Arreglo: Capturar el error de suggestions en su propio estado (o reutilizar err) en page.tsx:206 y pasarlo a VistaSugerencias, en vez de .catch(() => {}).
- **[media/robustez/S]** (datos) No existe backup automatico de Postgres (riesgo 9 del spec)
  - `scripts/ (directorio, falta backup.py)`
  - Arreglo: Crear scripts/backup.py (o backup.sh) que corra pg_dump del contenedor a ~/AtlasBackups/atlas-YYYYMMDD.sql.gz con rotacion (ej. ultimos 14 dias), y agendarlo con un launchd diario tipo io.niuro.atlas.backup analogo al io.niuro.atlas.sync ya existente.
- **[alta/bug/S]** (seguridad) CORS whitelistea el puerto 3000 pero el web corre en 3005: el navegador bloquea todas las llamadas del frontend a la API
  - `apps/api/src/atlas/main.py:23`
  - Arreglo: Incluir http://localhost:3005 y http://127.0.0.1:3005 en allow_origins, o mejor leer la lista desde config/env (p.ej. ATLAS_WEB_ORIGIN) en vez de hardcodear el puerto, para que deploy y CORS no se desincronicen.
- **[alta/bug/S]** (ops) CORS solo permite origin :3000 pero la web corre en :3005: el dashboard no puede cargar datos de la api
  - `apps/api/src/atlas/main.py:22`
  - Arreglo: Agregar http://localhost:3005 (y 127.0.0.1:3005) a allow_origins, idealmente leyendo los origins de una env var para no hardcodear el puerto. Alinear el puerto en un solo lugar de config.
- **[media/robustez/M]** (conectores) Sin rate limiter por conector (aiolimiter) que exige el spec
  - `apps/api/src/atlas/connectors/base.py:27`
  - Arreglo: Agregar aiolimiter y exponer un limitador configurable por conector en base.py (atributo rate_limit) que envuelva las llamadas HTTP.
- **[media/robustez/M]** (conectores) health() esta definido pero nunca se invoca; no hay deteccion de '2 syncs fallidos' ni badge/notificacion
  - `apps/api/src/atlas/connectors/sync.py:52`
  - Arreglo: Llamar health() en el flujo de sync, guardar un contador de fallos consecutivos en Source, exponerlo por API y disparar la notificacion tras 2 fallos.
- **[media/robustez/M]** (conectores) Items @removed / isCancelled solo se saltan; el raw_item viejo nunca se borra
  - `apps/api/src/atlas/connectors/outlook.py:90`
  - Arreglo: Al detectar @removed/isCancelled, borrar o marcar como eliminado el RawItem por (source_id, external_id) en vez de solo saltarlo.
- **[media/falta-feature/M]** (conectores) Falta el catch-up sync tras un gap (equipo apagado a la hora del sync)
  - `scripts/run-sync.sh:1`
  - Arreglo: Agregar un LaunchAgent con RunAtLoad / watch de wake, o al arranque comparar Source.last_sync_at contra ahora y disparar sync si el gap supera el intervalo.
- **[media/robustez/S]** (conectores) run-sync.sh silencia todos los fallos con '|| true' y no hay alerta
  - `scripts/run-sync.sh:6`
  - Arreglo: Registrar/propagar los fallos (contar exit codes, escribir a un log que el dashboard lea, o disparar notificacion) en vez de tragarlos con || true.
- **[alta/falta-feature/L]** (conectores) Faltan los conectores Slack, Granola (MCP), HubSpot, GitHub y Google Drive
  - `apps/api/src/atlas/connectors/`
  - Arreglo: Implementar cada conector contra la interfaz Connector existente (empezar por Slack/Granola/HubSpot del MVP). Granola via SDK mcp de Python (streamable_http); Slack con user token y whitelist de canales; HubSpot REST v3.
- **[media/falta-feature/M]** (conectores) Falta la regla de negocio HubSpot 'deal en negociacion sin actividad en 5 dias' (deteccion por SQL)
  - `apps/api/src/atlas/connectors/`
  - Arreglo: Al construir el conector HubSpot, sincronizar deals+engagements y agregar la consulta SQL que detecta deals en negociacion con max(actividad) > 5 dias y emite el TaskCandidate.
- **[baja/seguridad/S]** (conectores) El sync_cursor (deltaLink) se guarda en texto plano mientras auth_meta si va cifrado
  - `apps/api/src/atlas/db/models.py:49`
  - Arreglo: Cifrar el cursor con el mismo mecanismo Fernet que auth_meta, o documentar que para los conectores actuales no es sensible.
- **[baja/robustez/S]** (conectores) No hay quiet hours ni ventana de silencio configurable
  - `apps/api/src/atlas/core/config.py`
  - Arreglo: Agregar una franja quiet-hours configurable (en config) que el runner/notificador respete antes de sincronizar o notificar.
- **[media/robustez/S]** (agentes) Timeout del CLI no mata el subproceso: fuga de procesos claude huérfanos
  - `apps/api/src/atlas/agents/runtime.py:67`
  - Arreglo: Capturar asyncio.TimeoutError alrededor del wait_for y hacer proc.kill() + await proc.wait() antes de re-lanzar.
- **[alta/falta-feature/M]** (agentes) Regla de presupuesto al 80% no implementada: corte solo al 100% y para TODOS los agentes
  - `apps/api/src/atlas/agents/runtime.py:108`
  - Arreglo: Agregar umbral 0.8: al superarlo, deshabilitar agentes 5-9 (cuando existan) y emitir notificación 'presupuesto al 80%', dejando correr 1-4 hasta el 100%.
- **[media/robustez/M]** (agentes) Sin prompt caching del contexto de usuario (mitigación de costo del spec ausente)
  - `apps/api/src/atlas/agents/runtime.py:142`
  - Arreglo: En backend api, poner cache_control:{type:'ephemeral'} en el bloque system/contexto estable para las llamadas de alto volumen. Documentar que el backend cli no cachea.
- **[media/falta-feature/L]** (agentes) Agentes 5-9 del spec sin implementar (Resúmenes, Reportería, Productividad, Planificador diario/semanal)
  - `apps/api/src/atlas/agents/prompts`
  - Arreglo: Construir por bloque: 5/8/9 (Bloque 5), 6/7 (Bloque 6). Cada uno: prompt versionado + schema Pydantic + entrada tipada (6/7 con datos SQL agregados, no texto crudo) + scheduling launchd.
- **[media/falta-feature/L]** (agentes) Loop de aprendizaje semanal por few-shots no implementado (falta learning.py)
  - `apps/api/src/atlas/agents`
  - Arreglo: Crear agents/learning.py: query de TaskEvents de corrección de la semana -> 4-8 ejemplos reales -> render en un placeholder {few_shots} de los prompts 1-3. call_agent debe aceptar/sustituir ese bloque.
- **[baja/robustez/S]** (agentes) Señales urgencia_percibida y esfuerzo del Priorizador se calculan y se descartan
  - `apps/api/src/atlas/agents/orchestrator.py:146`
  - Arreglo: Decidir: incorporar urgencia_percibida/esfuerzo a Facts y a la fórmula, o eliminarlos de Senales y del prompt priorizador para reducir tokens de salida.
- **[baja/robustez/M]** (agentes) Rescoring reconstruye 'impacto' de forma lossy dividiendo el breakdown por el peso
  - `apps/api/src/atlas/agents/orchestrator.py:198`
  - Arreglo: Persistir impacto (y demás señales del Priorizador) como columnas en Task/TaskScore y leerlas directo en el rescoring, en vez de invertir el breakdown.
- **[media/robustez/S]** (agentes) IDs de modelo sin verificar ('claude-sonnet-5', 'claude-haiku-4-5') pueden 404ear todo el motor
  - `apps/api/src/atlas/core/config.py:22`
  - Arreglo: Confirmar los ids exactos vigentes de la API/CLI de Anthropic y fijarlos; agregar fallo temprano legible si el modelo no existe en vez de propagar error crudo.
- **[baja/robustez/S]** (agentes) deep_link asume payload['webLink'] (formato Outlook); vacío para el resto de conectores
  - `apps/api/src/atlas/agents/orchestrator.py:131`
  - Arreglo: Que cada conector normalice su URL a un campo canónico (item.web_link o payload['_deep_link']) en la capa connectors, y que el orquestador lea ese campo.
- **[media/bug/M]** (scoring) context_bonus nunca se calcula: 4 pts muertos (tareas_mismo_contexto_hoy siempre 0)
  - `apps/api/src/atlas/agents/orchestrator.py:205`
  - Arreglo: En rescore_abiertas, que ya tiene todas las tareas abiertas en memoria, contar por project_id/client_id y pasar tareas_mismo_contexto_hoy al Facts de cada tarea.
- **[media/bug/M]** (scoring) carga_del_dia no llega al scoring: effort_penalty_if_overloaded (-10) nunca se aplica
  - `apps/api/src/atlas/agents/orchestrator.py:205`
  - Arreglo: Calcular la carga del dia dentro de rescore_abiertas (o pasarla como argumento) y alimentar Facts.carga_del_dia; reutilizar la logica ya escrita en tasks.py:79-92.
- **[media/bug/S]** (scoring) frog_factor siempre 0: snooze genera evento pero veces_pospuesta nunca se cuenta
  - `apps/api/src/atlas/agents/orchestrator.py:205`
  - Arreglo: En rescore contar TaskEvent con event='snoozed' por task_id y pasarlo como veces_pospuesta.
- **[media/falta-feature/L]** (scoring) requester_factor hardcodeado en 0.6: bloque 'requester' de scoring.yaml sin usar
  - `apps/api/src/atlas/agents/orchestrator.py:149`
  - Arreglo: Al integrar CRM/roles (Bloque 5), resolver el factor desde el remitente y el mapa requester de scoring.yaml. Mientras tanto, al menos distinguir auto-impuesta (tarea creada a mano en /tasks) = 0.4 vs extraida = 0.6.
- **[baja/robustez/S]** (scoring) rescore resetea impacto=0 a 0.3 por chequeo de truthiness
  - `apps/api/src/atlas/agents/orchestrator.py:198`
  - Arreglo: Distinguir ausente de cero: usar 'impact_factor' in prev.score_breakdown en vez de truthiness, o guardar el impacto crudo en TaskScore para no re-derivarlo.
- **[media/falta-feature/L]** (scoring) Time blocking (agente 8) no implementado: modelo TimeBlock existe pero nadie lo escribe ni lee
  - `apps/api/src/atlas/db/models.py:163`
  - Arreglo: Implementar agente 8 en Bloque 6/7: leer ranking de TaskScore + eventos de calendario (RawItem kind='event') + energia aprendida (agente 7) y generar filas TimeBlock origin='ai_proposed'; endpoint para aceptar/mover/descartar. Atlas propone, no escribe en el calendario en MVP.
- **[alta/falta-feature/M]** (api-backend) No existe endpoint de sync manual (boton Cmd+Shift+S del spec)
  - `apps/api/src/atlas/connectors/sync.py:52`
  - Arreglo: Agregar POST /api/sync que llame a run_sync para las fuentes activas (idealmente en background task) y devuelva estado; exponer ultimo run via /sources (ya trae last_sync_at) o un endpoint de SyncRuns.
- **[media/bug/S]** (api-backend) Snooze no saca la tarea de Hoy: /today filtra por status e ignora due_date
  - `apps/api/src/atlas/routers/tasks.py:214`
  - Arreglo: Definir semantica de snooze: /today excluye tareas open con due_date > hoy, o snooze setea un status/campo (waiting o snoozed_until) que hoy filtre. Hoy ambos lados no se hablan.
- **[media/robustez/S]** (api-backend) due_date invalido en triage/edit provoca 500 en vez de 422
  - `apps/api/src/atlas/routers/tasks.py:142`
  - Arreglo: Validar/parsear la fecha con manejo de error y responder HTTPException(422,'due_date invalida'); o tipar due_date como datetime.date en el modelo Pydantic para que FastAPI valide.
- **[media/robustez/S]** (api-backend) Triage sin precondicion de estado: permite revertir tareas ya cerradas
  - `apps/api/src/atlas/routers/tasks.py:124`
  - Arreglo: Exigir que t.status este en el conjunto valido (p.ej. 'suggested') para triage y devolver 409/422 si no; centralizar transiciones de estado validas.
- **[media/falta-feature/S]** (api-backend) Falta endpoint de presupuesto de tokens del dia (el dato ya vive en Redis)
  - `apps/api/src/atlas/routers/settings.py:1`
  - Arreglo: Agregar GET /api/budget que devuelva {input_spent, output_spent, input_limit, output_limit, pct}. Reusar _budget_spent() del runtime y config.
- **[media/falta-feature/M]** (api-backend) Falta busqueda FTS instantanea (atajo '/' del spec, <50ms)
  - `apps/api/src/atlas/routers/tasks.py:1`
  - Arreglo: Agregar GET /api/search que corra websearch_to_tsquery sobre tasks (y raw_items) con config espanol; requiere indice tsvector si no existe.
- **[media/falta-feature/M]** (api-backend) Detalle de proyectos/clientes incompleto: /projects solo devuelve nombres y conteo
  - `apps/api/src/atlas/routers/tasks.py:229`
  - Arreglo: Agregar endpoint de detalle por proyecto/cliente con ultimo contacto (max de raw_items relacionados) y deals.
- **[media/falta-feature/L]** (api-backend) Faltan endpoints de Analytics (Focus/Burnout) y Reporteria PDF/XLSX
  - `apps/api/src/atlas/routers/tasks.py:1`
  - Arreglo: Bloques 6-7: GET /api/analytics (metricas 30d + formula) y GET /api/reports/{semana}.pdf|.xlsx. Sin urgencia si se respeta el roadmap MVP.
- **[baja/falta-feature/S]** (api-backend) Falta endpoint de re-auth de conector (boton re-auth del spec)
  - `apps/api/src/atlas/routers/settings.py:15`
  - Arreglo: Agregar POST /api/sources/{kind}/reauth que invoque authenticate(kind).
- **[baja/robustez/M]** (api-backend) Multi-usuario ignorado: ninguna query filtra por user_id
  - `apps/api/src/atlas/routers/tasks.py:42`
  - Arreglo: Si el diseno es mono-usuario, documentarlo y filtrar explicitamente por DEFAULT_USER_ID; si no, introducir dependencia de user actual y filtrar en cada query.
- **[baja/robustez/S]** (api-backend) PUT /scoring: sin validacion numerica y escritura de archivo no atomica
  - `apps/api/src/atlas/routers/settings.py:40`
  - Arreglo: Validar que cada peso sea finito y >=0 (rechazar nan/inf/negativos) antes de escribir; escribir a temporal y os.replace para atomicidad.
- **[baja/robustez/S]** (api-backend) /health no verifica dependencias (DB/Redis)
  - `apps/api/src/atlas/main.py:31`
  - Arreglo: Hacer /health ejecutar SELECT 1 y un ping a Redis y devolver 503 si fallan; o separar /health/ready del liveness.
- **[media/robustez/S]** (realtime) El WebSocket del front no reconecta tras una caida: el dashboard queda mudo hasta recargar
  - `apps/web/lib/api.ts`
  - Arreglo: Agregar ws.onclose = () => setTimeout(reconnect, backoff) con backoff simple (p.ej. 1s creciente hasta 30s) y limpiar en el cleanup. Es un patron de ~8 lineas envolviendo el new WebSocket en una funcion connect() reentrante.
- **[baja/robustez/S]** (realtime) Listener de Postgres: asyncio.get_event_loop() deprecado y variable conn potencialmente sin asignar al cancelar
  - `apps/api/src/atlas/ws.py:47`
  - Arreglo: Usar loop = asyncio.get_running_loop() capturado antes de add_listener y loop.create_task en el callback (o asyncio.create_task directo). Inicializar conn=None antes del try y guardar 'if conn:' en el handler. Opcional: reemplazar el poll por conn.add_termination_listener para detectar caida al instante.
- **[media/bug/S]** (frontend) Atajo 'g' hijackea cualquier tecla y salta a Hoy; el chord G→H/P/A/R del spec no existe
  - `apps/web/app/page.tsx:242`
  - Arreglo: Implementar el chord real (capturar G y esperar la segunda tecla H/P/A/R con timeout), o al menos quitar el atajo suelto mientras no existan las vistas destino.
- **[media/falta-feature/M]** (frontend) Faltan casi todos los atajos de teclado del spec (1-5, C, S, D, /, Cmd+Shift+S) y la vista Hoy no tiene seleccion
  - `apps/web/app/page.tsx:227`
  - Arreglo: Agregar estado de seleccion en Hoy y wire de 1-5/C; implementar S y D contra endpoints (o marcarlos como pendientes de backend); '/' abriendo busqueda; Cmd+Shift+S disparando sync.
- **[media/falta-feature/L]** (frontend) Vistas del spec ausentes: Proyectos/Clientes, Analytics (Focus/Burnout Score) y Reporte semanal
  - `apps/web/app/page.tsx:14`
  - Arreglo: Construir en los bloques 5-7. A corto plazo, dejar los nav-items con estado vacio/proximamente para que la navegacion del spec no quede muerta.
- **[media/ux/M]** (frontend) Sin toggle de tema ni light mode (regresion vs prototipo, que 'funciona y persiste')
  - `apps/web/app/globals.css:2`
  - Arreglo: Agregar bloque de variables para tema claro (via :root[data-theme='light'] o prefers-color-scheme) y un boton que persista la eleccion en localStorage.
- **[media/falta-feature/M]** (frontend) Command palette incompleto: sin voz, sin busqueda de tareas existentes, sin navegacion por teclado en resultados
  - `apps/web/app/page.tsx:166`
  - Arreglo: Agregar boton mic con Web Speech API; agrupar resultados y consultar un endpoint de busqueda/FTS; permitir arrow+Enter para elegir resultado.
- **[baja/ux/M]** (frontend) Responsive parcial: el sidebar nunca pasa a drawer y hay un solo breakpoint
  - `apps/web/app/globals.css:34`
  - Arreglo: Agregar breakpoint ~768px que oculte el sidebar tras un boton hamburguesa con overlay, siguiendo la matriz de viewports del handoff.
- **[baja/ux/S]** (frontend) Las fuentes del spec no se cargan (Fraunces/Host Grotesk/Inter/JetBrains Mono); el saludo cae a Georgia
  - `apps/web/app/globals.css:31`
  - Arreglo: Cargar las fuentes con next/font/google (Inter, JetBrains Mono, Fraunces) en layout.tsx y aplicar Fraunces al .saludo y numeros grandes de analytics.
- **[alta/falta-feature/M]** (datos) Las tablas Client y Project nunca se pueblan: la clasificacion por cliente/proyecto es inerte
  - `apps/api/src/atlas/db/seed.py:17-24`
  - Arreglo: Sembrar clientes y proyectos: agregar config/clients.yaml (y projects.yaml) + extender seed.py de forma idempotente igual que las areas, o exponer un endpoint/CRUD minimo para crearlos desde la web. Sin datos sembrados, la clasificacion por cliente/proyecto no puede funcionar.
- **[media/robustez/S]** (datos) Indice ivfflat lists=100 mal dimensionado y no usado por la unica query vectorial
  - `apps/api/src/atlas/db/models.py:59-65`
  - Arreglo: A escala MVP: quitar el indice ivfflat (el seq scan es correcto y suficiente con pocas filas) o cambiarlo por HNSW (postgresql_using='hnsw', no depende de #filas ni de lists y da buen recall sin tuning). Si se mantiene ivfflat, ajustar lists ~ sqrt(N) y reconstruir tras cargar data, y subir ivfflat.probes.
- **[baja/robustez/S]** (datos) Entidades TimeBlock y WeeklyReport definidas y migradas pero sin uso en el codigo
  - `apps/api/src/atlas/db/models.py:163,187`
  - Arreglo: Aceptable como pre-provision para bloques 5-7. Dejar comentario ponytail marcando que son placeholders hasta esos bloques, o diferir su creacion a la migracion del bloque que las use, para no arrastrar esquema sin consumidor.
- **[baja/robustez/S]** (datos) UserFeedback solo se escribe, nunca se lee
  - `apps/api/src/atlas/routers/tasks.py:147`
  - Arreglo: Sin accion hasta el bloque 7 (aprendizaje semanal). Registrar la dependencia para que ese bloque consuma user_feedback. Verificar que la escritura actual guarde before/after utiles para cuando se lea.
- **[baja/robustez/S]** (datos) Dimension de embedding 1024 vs spec 1536: consistente y pineada (confirmacion, sin bug)
  - `apps/api/src/atlas/db/models.py:27`
  - Arreglo: Ninguna accion. Si algun dia se sube a 1536/2048, cambiar EMBEDDING_DIMS y generar una migracion de alter del tipo vector + recomputar embeddings existentes.
- **[media/seguridad/S]** (seguridad) Falta hook pre-commit con gitleaks: los secretos pueden colarse al repo por accidente
  - `.pre-commit-config.yaml (inexistente)`
  - Arreglo: Agregar .pre-commit-config.yaml con el hook de gitleaks (y documentar `pre-commit install` en scripts/setup.py para que quede activo tras la instalacion).
- **[media/seguridad/S]** (seguridad) setup.py no verifica FileVault: sin FDE, el disco expone el corpus crudo de emails y los tokens del volumen Postgres
  - `scripts/setup.py:22`
  - Arreglo: En setup.py, en la rama Darwin, correr `fdesetup status` y abortar o advertir en rojo si FileVault esta apagado antes de dejar el stack listo.
- **[baja/seguridad/M]** (seguridad) La API no tiene autenticacion ni chequeo de origen en endpoints mutantes ni en el WebSocket
  - `apps/api/src/atlas/main.py:36`
  - Arreglo: Dejarlo documentado como decision de diseño (single-tenant local) y, si se quiere endurecer barato, validar Origin en el handshake del WS y agregar un token local en header compartido web<->api leido de config. No urgente mientras el bind siga en 127.0.0.1.
- **[media/falta-feature/S]** (ops) QUIET_HOURS es config muerta: definido en .env pero nunca leido, el sync corre 24/7
  - `apps/api/src/atlas/core/config.py:34`
  - Arreglo: Leer QUIET_HOURS en config.py y saltar el pipeline (o solo la fase de notificacion/generacion) en run-sync.sh / orchestrator cuando la hora actual cae dentro del rango.
- **[media/robustez/M]** (ops) Sync sin catch-up: no corre al cargar y launchd coalesce las corridas perdidas en una sola
  - `~/Library/LaunchAgents/io.niuro.atlas.sync.plist:11`
  - Arreglo: Poner RunAtLoad=true y guardar el timestamp de la ultima corrida exitosa; al arrancar, sincronizar desde ese timestamp (delta real) en vez de asumir la ultima hora.
- **[media/falta-feature/M]** (ops) Sin notificaciones al usuario (conector caido, plan listo, presupuesto 80%) que pide el spec
  - `scripts/run-sync.sh:7`
  - Arreglo: Notificacion nativa macOS (osascript -e 'display notification' o terminal-notifier) desde run-sync.sh cuando un conector falla, y desde el orchestrator/runtime al cruzar el 80% del presupuesto y cuando el plan diario queda listo.
- **[media/robustez/S]** (ops) Sin backup programado de Postgres: los datos viven solo en el volumen docker
  - `infra/docker-compose.yml:27`
  - Arreglo: launchd diario que corra pg_dump del contenedor a un directorio versionado (rotacion simple de N dias). ~15 lineas de script + un plist.
- **[baja/ux/S]** (ops) Inconsistencia de puerto :3000 vs :3005 en Taskfile y README frente al deploy real
  - `Taskfile.yml:17`
  - Arreglo: Unificar en 3005: 'pnpm dev -p 3005' en Taskfile y actualizar README, o al reves, pero que dev, deploy, CORS y docs usen el mismo puerto.
- **[baja/falta-feature/S]** (ops) No hay update-app: al cambiar el codigo no se reconstruye la web ni se reinician los servicios
  - `scripts/make-mac-app.sh:1`
  - Arreglo: Script scripts/update-app.sh: git pull/uv sync + pnpm build en apps/web, luego 'launchctl kickstart -k gui/$(id -u)/io.niuro.atlas.api' y '.web' para tomar el codigo nuevo.
