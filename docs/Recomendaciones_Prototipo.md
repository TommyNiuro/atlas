# Atlas · Revisión del prototipo y siguientes pasos

**Revisado por**: asistente de Tomás Ffrench-Davis
**Fecha**: 8 de julio de 2026
**Archivo revisado**: `Atlas_Task.zip` (index.html, DESIGN-MANIFEST.json, DESIGN-HANDOFF.md, critique.json)
**Origen**: prototipo generado en Claude Design

---

## Veredicto en una línea

La maqueta visual está a nivel de referencia (Linear como vara) y sirve tal cual para dos cosas: enseñarla y usarla como input de diseño de la Fase 0. Lo que falta no son arreglos de diseño, son las tres piezas de interacción que hacen que un desarrollador entienda el producto completo antes de construirlo.

---

## Qué está bien

Las cinco vistas del requerimiento están presentes y son fieles al spec: Hoy, Sugerencias, Proyectos y Clientes, Analytics y Settings.

La vista Hoy resuelve la jerarquía que buscábamos. El saludo en Fraunces, el Top 5 con score en gold y desglose visible, la agenda a la derecha con los time blocks propuestos en punteado, la barra de carga del día y el panel de "esperando respuesta". En diez segundos se entiende de qué va Atlas.

La marca se respeta. Navy, gold como acento contenido, warm white en lugar de blanco puro. El dark mode es el correcto y el light mode no cae en el beige o cream que suele arruinar estos diseños. El toggle de tema funciona y persiste.

Analytics se ve premium. Los KPI grandes, el Focus Score y el Burnout Score con su explicación al lado, la distribución por área. Es la vista que más fácil vende el producto a un tercero.

El responsive está pensado, no improvisado. Tres breakpoints (1024, 768, 390), sidebar que pasa a drawer con overlay, tipografía que escala. El handoff trae la matriz de viewports para validar.

---

## Qué es y qué no es (para no llevarte una sorpresa)

Esto es la piel, no el cuerpo. Es una maqueta visual estática: cero stylesheets externos, cero componentes, dos scripts mínimos (solo el toggle de tema). Los datos son de ejemplo. No hay backend, ni conectores, ni agentes.

Eso está perfecto para esta etapa. En el requerimiento, la maqueta es justo el punto de partida de la Fase 0. El único riesgo es confundirla con "ya está construido": no lo está, y no debería estarlo todavía.

---

## Las tres piezas que faltan, por orden de impacto

### 1. Command palette (Cmd/Ctrl+K)

Es el corazón de la experiencia keyboard-first que definimos: abrir con Cmd/Ctrl+K, crear tareas en lenguaje natural ("llamar a Francisco el viernes 10am"), navegar entre vistas, buscar. No está en la maqueta, y sin él un desarrollador no ve el patrón de interacción central del producto. Es la ausencia más importante.

Qué agregar: el overlay con el input arriba, una lista de resultados agrupados (acciones, tareas, navegación) y el hint de que acepta lenguaje natural. Aunque sea estático, el patrón queda claro.

### 2. Estados vacío y error de cada vista

Ahora solo se ve el estado "lleno y feliz". Falta lo que el producto muestra el resto del tiempo, que es justo donde se siente terminado o a medias. El handoff insiste en esto y tiene razón.

Qué agregar por vista: el estado vacío con acción útil (ejemplo en la bandeja: "Sin sugerencias nuevas. Última sync hace 12 min.") y el estado de error con reintento (ejemplo en Settings: conector caído en rojo con botón de re-autenticar, que ya se insinúa en HubSpot). El estado de carga con skeleton, no spinner.

### 3. Hints de atajos A/X/E/M en Sugerencias

La vista de la bandeja está, pero el gesto rápido que la hace útil no se ve. El triage de una tecla (A acepta, X rechaza, E edita, M fusiona) es lo que permite procesar veinte sugerencias en dos minutos.

Qué agregar: los chips de atajo visibles en cada fila o un recordatorio fijo en la cabecera de la vista, de modo que se lea el gesto sin tener que probarlo.

---

## Correcciones menores

El `DESIGN-MANIFEST.json` trae el título con un UUID (`fc3fe77b-8c9c-...`) en lugar de "Atlas". Cambiarlo antes de pasar el paquete a un desarrollador o a Claude Code, para que no arrastre ese nombre a la implementación.

El nombre del producto sigue como "Atlas". Si aún estás decidiendo el nombre final (quedaron sobre la mesa Cauce, Rumbo y Tramo), conviene cerrarlo antes de que un dev lo hardcodee en rutas, títulos y el repo.

---

## Recomendación concreta

El prototipo está listo para enseñarlo hoy. Para que sea un buen input de desarrollo, una segunda pasada en Claude Design que sume solo esas tres piezas (palette, estados, hints) deja el handoff redondo y evita que el desarrollador tenga que inventarlas.

Dos caminos posibles:

Uno, una segunda pasada en Claude Design con un prompt preciso que describa las tres adiciones fieles a la marca.

Dos, tomar este HTML y agregarle el command palette y los estados como demo funcional, para verlo moviéndose antes de decidir.

Cualquiera de los dos sirve. El primero mantiene todo dentro de Claude Design y su sistema de tokens; el segundo te da algo interactivo más rápido.

---

## Checklist antes del handoff a desarrollo

Para cuando decidas pasar esto a construcción, esto es lo que conviene tener cerrado:

Nombre del producto definido y reemplazado en el manifest, títulos y rutas.

Command palette presente en la maqueta, aunque sea estático.

Los tres estados (carga, vacío, error) diseñados para cada una de las cinco vistas.

Hints de atajos visibles en Sugerencias y, si se puede, en Hoy.

Las tres definiciones de la Fase 0 del requerimiento resueltas, que son independientes del prototipo: app registrada en Entra ID para Outlook, token de HubSpot con scopes de lectura CRM, y la lista inicial de canales de Slack relevantes.
