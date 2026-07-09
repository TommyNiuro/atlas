# Atlas · Plan de construcción del cuerpo completo

**De la maqueta a la aplicación funcionando en tu Mac o Windows**

Autor: asistente de Tomás Ffrench-Davis
Fecha: 8 de julio de 2026
Acompaña a: Requerimiento_Tecnico_Atlas_v1.md (la arquitectura) y al prototipo de Claude Design (la piel)

---

## Cómo usar este documento

El requerimiento técnico dice qué se construye. El prototipo muestra cómo se ve. Este documento dice cómo se construye, en qué orden, y trae los prompts exactos para dárselos a Claude Code una vez que abras el proyecto en tu equipo.

La regla de oro: se construye de abajo hacia arriba y de una fuente a la vez. Primero el esqueleto que corre en tu máquina, después la base de datos, después un solo conector de punta a punta (Outlook), después el motor de agentes sobre esa única fuente, y recién cuando ese circuito completo funciona con datos reales, se suman las demás fuentes. Nada de construir siete conectores a ciegas antes de ver el primero producir una tarea de verdad.

Cada bloque de abajo es un conjunto de commits con un criterio de "terminado" verificable. Si el criterio no se cumple, no se avanza al siguiente bloque.

---

## Prerequisitos que dependen de ti, no del código

Estas tres cosas hay que resolverlas antes de escribir la primera línea, porque sin ellas los conectores no autentican. Son independientes de Mac o Windows.

Registro de app en Microsoft Entra ID. Entra al portal de Azure con la cuenta de niuro.io, registra una aplicación nueva como cliente público (public client), y anota el Client ID y el Tenant ID. Los permisos delegados que necesita son Mail.Read y Calendars.Read. Esto habilita el device code flow, que es el que no necesita secreto de cliente y sirve para una app local.

Private App token de HubSpot. En el portal 50413996, ajustes, integraciones, private apps, crea una con scopes de lectura de CRM (deals, contacts, engagements). Copia el token.

Lista de canales de Slack relevantes. Define cuáles canales, además de tus DMs y menciones, quieres que Atlas lea. Empieza corto: los tres o cuatro donde de verdad te asignan trabajo. Esta lista vive en un archivo de configuración y se puede ampliar después.

Además necesitas dos llaves de API: la de Anthropic (para los agentes) y la de Voyage (para los embeddings). Ambas se pegan en el archivo .env al inicio.

---

## Bloque 0 · Esqueleto que corre

Objetivo: que `task dev` levante todo el stack vacío en tu equipo. Sin funciones todavía, pero con el andamiaje completo montado.

Qué se crea en este bloque:

El monorepo con la estructura de carpetas del requerimiento (apps/web, apps/api, packages, config, infra, scripts).

El docker-compose con cuatro servicios: postgres 16 con la extensión pgvector, redis 7, el api de FastAPI y el worker de arq. Imágenes multi-arch para que corra igual en Intel, Apple Silicon y Windows.

El Taskfile.yml con los comandos base: dev, migrate, test, logs, backup. Reemplaza al Makefile para que funcione idéntico en Mac y Windows.

El script setup.py que detecta el sistema operativo, genera la llave Fernet y la guarda en el almacén nativo (Keychain o Credential Locker) vía keyring, instala dependencias y corre las migraciones iniciales.

FastAPI con un endpoint /health que responde ok, y Next.js con el prototipo de Claude Design ya integrado como el frontend base (aquí es donde la piel deja de ser un HTML suelto y se vuelve la app real).

El pipeline de CI en GitHub Actions: lint, typecheck y test en cada push.

Criterio de terminado: clonas el repo en una Mac y en una PC con Windows, corres los comandos de instalación, y en ambos `task dev` levanta el stack en menos de 90 segundos. El dashboard abre en localhost:3000 mostrando el prototipo. El endpoint /health responde. Los tests pasan en verde aunque todavía sean pocos.

---

## Bloque 1 · Base de datos y modelo

Objetivo: las diez entidades del requerimiento existen como tablas, con sus índices y su cifrado de tokens.

Qué se crea:

Los modelos de SQLAlchemy 2 async para las diez entidades: SOURCE, RAW_ITEM, AREA, PROJECT, CLIENT, TASK, TASK_SCORE, TASK_EVENT, TIME_BLOCK, USER_FEEDBACK, WEEKLY_REPORT.

La migración inicial de Alembic que las crea todas, con la columna user_id presente desde el día uno (con valor por defecto del usuario único) para no tener que remodelar cuando llegue el multi-usuario.

Los índices del requerimiento: GIN sobre los campos JSONB, ivfflat sobre el embedding para búsqueda vectorial, y B-tree sobre las combinaciones que se consultan seguido.

La capa de cifrado: los tokens OAuth se guardan cifrados con Fernet en la columna auth_meta de SOURCE, y la llave maestra se lee desde el almacén del sistema, nunca desde el .env.

Un script de seed que carga tus áreas de trabajo reales (Ventas, Reclutamiento, Operaciones, Clientes, Alianzas, Networking, Administración, Marketing, Contenido, Personal) y tus clientes activos, para que las pruebas usen datos que reconoces.

Criterio de terminado: la migración corre limpia, puedes insertar y leer una tarea de prueba con su evidencia y su score, y los tokens que guardes quedan cifrados en la base (lo verificas mirando la columna directamente: debe ser ilegible).

---

## Bloque 2 · Un conector de punta a punta (Outlook)

Objetivo: Outlook autentica, trae correos reales y los guarda como RawItem en la base. Todavía sin agentes, solo el circuito de datos crudos.

Este es el bloque más importante del proyecto. Si un conector funciona de verdad, los otros seis son variaciones del mismo patrón. Por eso se hace uno completo antes de tocar los demás.

Qué se crea:

La interfaz Connector (el Protocol con authenticate, pull_incremental y health) que todos los conectores van a implementar. Se define aquí porque Outlook es el primero que la usa.

El conector de Outlook contra Microsoft Graph, usando el device code flow: al autenticar, imprime un código en la terminal, abres el navegador, lo pegas, y queda autorizado sin secreto de cliente.

Las delta queries de Graph, que son la mejor API incremental de todo el stack: en cada sync solo traen lo que cambió desde el último token, no todo el buzón.

La normalización de correo a RawItem: cada correo se convierte al formato común, se le calcula el embedding con Voyage, se guarda el payload original completo y se registra su external_id para no reprocesarlo.

El filtro barato previo: newsletters y notificaciones automáticas se descartan por remitente y cabeceras antes de gastar nada, porque no son tareas.

Criterio de terminado: corres el comando de auth de Outlook, autorizas, corres un sync manual, y ves en la base tus correos reales de las últimas horas convertidos en RawItems, con su embedding calculado y sin duplicados. Si corres el sync dos veces seguidas, la segunda no crea nada nuevo (idempotencia).

### Prompt para Claude Code · Bloque 2

Usa el conector de Microsoft Graph como plantilla del resto. Implementa la interfaz Connector definida en connectors/base.py. Para la autenticación usa el device code flow de MSAL para Python, apropiado para un cliente público local, sin secreto de cliente. Para la sincronización incremental usa las delta queries de Graph (el deltaLink que devuelve la API), guardado en SOURCE.sync_cursor. Normaliza cada mensaje a RawItem guardando el payload JSON completo, calculando el embedding con la API de Voyage y registrando el external_id del mensaje. Antes de procesar, descarta correos de listas y notificaciones automáticas mirando remitente y cabeceras List-Unsubscribe y Auto-Submitted. Escribe tests de integración que usen respuestas grabadas de Graph con respx, sin llamar a la API real. No implementes todavía ningún otro conector.

---

## Bloque 3 · Motor de agentes sobre esa única fuente

Objetivo: los RawItems de Outlook se convierten en tareas reales con evidencia y score. El pipeline de inteligencia funcionando de extremo a extremo sobre una sola fuente.

Qué se crea:

El Agent Runtime: la capa que llama a la API de Anthropic con presupuesto de tokens, reintentos y validación de salida contra esquemas de Pydantic.

El Orchestrator, que es código Python, no un LLM: enruta cada RawItem por el pipeline y decide qué agente corre cuándo. La orquestación es determinista; solo la interpretación usa modelo.

Los primeros cuatro agentes, cada uno con su prompt en un archivo versionado: Extractor (saca tareas candidatas con cita textual de evidencia), Clasificador (les pone área, proyecto, cliente, tipo), Priorizador semántico (estima urgencia, impacto y esfuerzo) y Seguimiento (detecta cuáles esperan respuesta).

La deduplicación previa al LLM: antes de llamar al Extractor, se compara el embedding del RawItem contra las tareas abiertas; si la similitud coseno supera 0.92, es duplicado y no se procesa.

El umbral de confianza: bajo 0.6 se descarta, entre 0.6 y 0.8 la tarea queda en estado suggested (va a la bandeja), sobre 0.8 pasa a open directo.

El Priority Engine, que es la fórmula determinista del requerimiento con los pesos en un YAML editable. Toma las señales cualitativas del Priorizador y las combina con los hechos duros (deadline, quién pide, antigüedad) para dar un score de 0 a 100 con su desglose factor por factor.

Criterio de terminado: un correo real que dice "¿me mandas la propuesta el viernes?" entra por el sync, pasa por el pipeline, y aparece en la base como una tarea con título limpio, fecha el viernes, área Ventas, el cliente correcto, un score con su desglose, y la cita textual del correo como evidencia con su enlace de vuelta al mensaje. Un correo que no es tarea (una confirmación, un gracias) no genera nada.

### Prompt para Claude Code · Bloque 3

Construye el pipeline de agentes sobre los RawItems de Outlook que ya existen en la base. El Orchestrator es código Python que enruta; no uses un framework de agentes, mantén el control explícito. Cada agente tiene su prompt en agents/prompts como archivo de texto versionado, y su salida se valida contra un esquema Pydantic; si no valida, reintenta una vez y si falla, descarta con log. Antes del Extractor, calcula la similitud coseno del embedding del RawItem contra las tareas abiertas y salta los que superen 0.92. El Extractor debe devolver, por cada tarea candidata, la cita textual exacta del correo que la origina y un nivel de confianza de 0 a 1; sin cita, la candidata se descarta. El Priority Engine es una función pura en scoring/engine.py que lee los pesos desde config/scoring.yaml y devuelve el score con el desglose de cada factor; no llama a ningún LLM. Usa Haiku para Extractor, Clasificador y Seguimiento, y Sonnet para el Priorizador. Escribe un set de evals con diez correos reales anonimizados, unos que son tarea y otros que no, y mide la precisión antes de dar el bloque por terminado.

---

## Bloque 4 · La app se ve y se usa (MVP visible)

Objetivo: conectar el prototipo de Claude Design con los datos reales. Dejar de mirar la base con un cliente de SQL y empezar a usar Atlas como app.

Qué se crea:

La API REST que expone las tareas, los proyectos y las vistas, más un WebSocket que empuja cada tarea nueva al dashboard sin recargar.

La vista Hoy conectada a datos reales: el Top 5 sale del ranking del Priority Engine, la agenda del día sale de los eventos de Outlook Calendar (que se suma como segundo conector aquí, porque es gemelo del de Mail), la carga del día se calcula de verdad.

La bandeja de Sugerencias funcional: las tareas en estado suggested aparecen aquí, y el triage por teclado funciona de verdad (A acepta y la mueve a open, X la descarta, E abre para editar, M fusiona con otra). Cada acción se guarda en USER_FEEDBACK.

El command palette real (Cmd/Ctrl+K): crear tarea en lenguaje natural con parseo de fecha, navegar entre vistas, buscar. Esto que faltaba en la maqueta, aquí se construye funcionando.

Los tres estados de cada vista: carga con skeleton, vacío con mensaje útil, error con reintento.

La vista Settings conectada: el estado real de cada conector, el historial de syncs con sus métricas, y el editor de pesos del scoring que recalcula el ranking al guardar.

Criterio de terminado: abres Atlas, ves tus tareas reales del día ordenadas por prioridad, procesas la bandeja de sugerencias con el teclado, creas una tarea escribiendo "café con Alan el jueves 9am" en el palette y aparece con la fecha correcta, y todo esto sin tocar la base de datos directamente ni una vez.

Este es el momento donde tienes producto. Todo lo que sigue lo hace más completo, pero a partir de aquí Atlas ya te sirve todos los días con una fuente. Vale la pena usarlo una semana real antes de seguir, para validar que la extracción funciona con tu correo de verdad y no con casos de prueba.

---

## Bloque 5 · Las demás fuentes

Objetivo: sumar Slack, Granola y HubSpot al circuito que ya funciona. Cada una es una implementación de la misma interfaz Connector, así que son rápidas comparadas con el bloque 2.

Qué se crea, una fuente a la vez, cada una con su criterio de terminado propio:

Slack, con user token para ver DMs y menciones y los canales de tu lista. Una mención que dice "@tomas necesitamos revisar el presupuesto" se vuelve tarea.

Granola, vía su MCP oficial. El backend actúa como cliente MCP: tras cada reunión, los acuerdos donde el responsable eres tú se vuelven tareas, y los de otros se vuelven seguimientos.

HubSpot, con el private app token. Además de traer actividad de deals, trae una regla de negocio que corre en SQL sin gastar tokens: un deal en negociación sin actividad en cinco días genera un follow-up automático.

Criterio de terminado del bloque: las cuatro fuentes (Outlook, Slack, Granola, HubSpot) alimentan la misma bandeja, y en Settings ves las cuatro en verde con su último sync. Un acuerdo de una reunión de Granola y un correo de Outlook conviven en el mismo Top 5, ordenados por el mismo score.

### Prompt para Claude Code · Bloque 5

Implementa Slack, Granola y HubSpot como conectores nuevos, cada uno implementando la interfaz Connector ya definida, sin tocar el pipeline de agentes ni el scoring, que ya funcionan y son agnósticos a la fuente. Para Slack usa un user token con los scopes de historial y búsqueda, y lee solo DMs, menciones y los canales listados en config/channels.yaml. Para Granola, el backend es un cliente MCP que se conecta al servidor oficial por streamable HTTP y llama a list_meetings desde el último sync. Para HubSpot, además del pull de deals con actividad reciente por hs_lastmodifieddate, agrega una función en SQL que marque para follow-up los deals en etapa de negociación sin engagement en cinco días, sin llamar a ningún LLM. Cada conector trae sus tests de integración con respuestas grabadas. Súmalos al registro de conectores uno por uno y verifica cada uno de punta a punta antes de pasar al siguiente.

---

## Bloque 6 · Planificación y aprendizaje (V1)

Objetivo: Atlas deja de solo ordenar y empieza a planificar el día, y empieza a aprender de tus correcciones.

Qué se crea:

Los conectores que faltan, GitHub y Google Drive, que son los de menor volumen de tareas para tu perfil y por eso van al final.

El agente Planificador diario: cada mañana toma el ranking, los huecos de tu calendario y tus horas de más energía, y propone bloques de tiempo. Tú los aceptas, mueves o descartas con arrastrar y soltar. Atlas nunca escribe en tu calendario: propone, tú agendas.

El agente de Resúmenes, que condensa hilos largos y transcripciones en tres a cinco líneas con los acuerdos y responsables.

El loop de aprendizaje semanal: todas tus correcciones (reclasificar, cambiar prioridad, rechazar una sugerencia) se guardan, y cada domingo se convierten en ejemplos que se inyectan en los prompts de los agentes de extracción y clasificación. Sin reentrenar el modelo: aprende por contexto, y es reversible.

La vista Proyectos y Clientes conectada: por cada cliente ves tareas abiertas, último contacto, deals asociados y próxima reunión.

Atlas como servidor MCP local: publica sus propias herramientas (mis tareas de hoy, crear tarea, completar tarea, plan del día) para que lo manejes desde Claude Desktop o Claude Code sin abrir el dashboard.

Criterio de terminado: a las siete de la mañana tienes un plan del día propuesto con bloques de tiempo sobre tu calendario real, y después de dos semanas corrigiendo, la clasificación por área acierta notablemente más que la primera semana (se mide con los evals).

---

## Bloque 7 · Reportería y analítica (V2)

Objetivo: cerrar el producto con los reportes y las métricas que pediste desde el principio.

Qué se crea:

El agente de Reportería y el generador de reportes: cada viernes, un PDF con la marca Niuro y un XLSX con todas las tareas de la semana, tiempo invertido, KPIs, logros y riesgos, listo para compartir con quien sea.

El agente de Productividad y la vista Analytics completa: horas de trabajo profundo contra reuniones, cumplimiento semanal y mensual, rachas, tus días y horas más productivos, qué clientes consumen más tiempo. El Focus Score y el Burnout Score, cada uno con su fórmula visible, nunca un número mágico.

El input por voz en el command palette, dictar una tarea en español.

Una vista móvil de solo lectura: el Top 5 y la agenda, para consultar desde el teléfono.

Los conectores opcionales que quieras: Notion, Linear, Jira. Los tres tienen MCP oficial y la interfaz Connector los hace directos.

Criterio de terminado: el viernes por la tarde tienes un reporte de la semana generado solo, con el diseño de Niuro, que podrías enviarle a un socio sin editar nada.

---

## El orden completo, de un vistazo

Bloque 0, esqueleto que corre. Bloque 1, base de datos. Bloque 2, Outlook de punta a punta. Bloque 3, agentes sobre Outlook. Bloque 4, la app visible con Outlook y su calendario (aquí ya tienes producto usable). Bloque 5, las demás fuentes. Bloque 6, planificación y aprendizaje. Bloque 7, reportería y analítica.

Del bloque 0 al 4 es el MVP: entre cinco y ocho semanas de trabajo con Claude Code. Del 5 al 7 es completar el producto: otras seis a ocho semanas. El requerimiento técnico tiene el detalle de cada pieza; este documento tiene el orden y los prompts.

---

## La única regla que no se rompe

No se construyen las siete fuentes antes de ver la primera producir una tarea real. No se construyen las seis vistas antes de que el pipeline funcione. Se hace una cosa completa, se verifica con datos de verdad, y recién entonces se suma la siguiente. Es lo que separa un producto que funciona de una demo que se ve bien y no hace nada.

Cada bloque tiene un criterio de terminado que se puede comprobar mirando la pantalla o la base de datos. Si no se cumple, no se avanza. Esa disciplina es lo que hace que un proyecto de este tamaño llegue a puerto en vez de quedarse en el 80 por ciento para siempre.

---

## Lo primero, mañana

Resolver los tres prerequisitos que dependen de ti (app en Entra ID, token de HubSpot, lista de canales de Slack), conseguir las llaves de Anthropic y Voyage, y abrir el proyecto en Claude Code para arrancar el Bloque 0. Con eso, el esqueleto corriendo en tu equipo es cuestión de una o dos sesiones.
