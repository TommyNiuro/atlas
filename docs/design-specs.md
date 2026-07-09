# Atlas Design Specs

Especificación técnica del sistema de diseño para implementación en producción.

---

## Tokens de Color

### Dark Theme (default)

| Token | Valor | Uso |
|-------|-------|-----|
| `--bg` | `#0C1222` | Fondo principal |
| `--surface` | `#141D33` | Cards, modales |
| `--overlay` | `#1C2844` | Hover states |
| `--raised` | `#243254` | Elementos elevados |
| `--sidebar-bg` | `#0A1020` | Sidebar |
| `--topbar-bg` | `rgba(10,16,32,.94)` | Topbar con blur |
| `--border` | `rgba(148,163,210,.16)` | Bordes default |
| `--border-strong` | `rgba(148,163,210,.28)` | Bordes hover/focus |
| `--fg` | `#E8ECF4` | Texto principal |
| `--fg-bright` | `#FFFFFF` | Texto énfasis |
| `--muted` | `#8A99C2` | Texto secundario |
| `--gold` | `#FFD166` | Acento primario |
| `--blue` | `#5B7BFF` | Interactivos |
| `--success` | `#34D399` | Estados positivos |
| `--warning` | `#FBBF24` | Alertas |
| `--danger` | `#F87171` | Errores |

### Light Theme

| Token | Valor |
|-------|-------|
| `--bg` | `#F4F6FA` |
| `--surface` | `#FFFFFF` |
| `--fg` | `#1A2138` |
| `--muted` | `#5E6A8A` |
| `--blue` | `#3B5FE5` |
| `--gold` | `#B8911F` |

---

## Tipografía

| Rol | Stack | Tamaños típicos |
|-----|-------|-----------------|
| Display | `'Fraunces', Georgia, serif` | 30px greeting, 20px headers |
| Headers | `'Inter', system-ui, sans-serif` | 16px, 14px |
| Body | `'Inter', system-ui, sans-serif` | 13px, 12px |
| Mono | `'JetBrains Mono', monospace` | 11px, 10px |

### Escala específica

- Greeting: `30px`, weight `700`, letter-spacing `-0.02em`
- Section title: `20px`, weight `600`, letter-spacing `-0.01em`
- Task title: `14px`, weight `500`
- Body text: `13px`, line-height `1.6`
- Captions/meta: `12px`, color `--muted`
- Chips/badges: `10.5px`, mono, uppercase con `letter-spacing: 0.06em`

---

## Espaciado

| Token | Valor |
|-------|-------|
| `--space-xs` | `6px` |
| `--space-sm` | `10px` |
| `--space-md` | `16px` |
| `--space-lg` | `24px` |
| `--space-xl` | `32px` |
| `--space-2xl` | `48px` |

---

## Radios

| Token | Valor | Uso |
|-------|-------|-----|
| `--radius` | `10px` | Buttons, inputs |
| `--radius-lg` | `14px` | Cards |
| `--radius-xl` | `18px` | Modales, command palette |

---

## Layout

### Grid principal
```
.app {
  display: grid;
  grid-template-columns: var(--sidebar-w) 1fr;  /* 260px sidebar */
  grid-template-rows: var(--topbar-h) 1fr;      /* 60px topbar */
}
```

### Breakpoints

| Nombre | Ancho | Cambios |
|--------|-------|---------|
| Desktop | >1024px | Sidebar visible, grids 2-3 columnas |
| Tablet | ≤1024px | Grids 1-2 columnas, padding reducido |
| Mobile | ≤768px | Sidebar drawer, topbar compacto |
| Small | ≤390px | Tipografía reducida |

---

## Componentes

### Task Row
```css
.task-row {
  display: grid;
  grid-template-columns: 32px 1fr auto;
  gap: 14px;
  padding: 14px 18px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  transition: all .15s ease;
}

.task-row:hover {
  background: var(--overlay);
  border-color: var(--border-strong);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0,0,0,.2);
}
```

### Project Card
```css
.project-card {
  padding: var(--space-lg);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  transition: all .18s;
}

.project-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 28px rgba(0,0,0,.25);
}
```

### Buttons
```css
/* Primary */
.btn-primary {
  background: var(--blue);
  color: #fff;
  padding: 8px 16px;
  border-radius: var(--radius);
}

/* Ghost */
.btn-ghost {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--muted);
}

.btn-ghost:hover {
  border-color: var(--blue);
  color: var(--blue);
}
```

### Score Badge
```css
.task-score {
  font-family: var(--font-mono);
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 6px;
  background: var(--gold-soft);
  color: var(--gold);
}
```

### Chips
```css
.task-chip {
  display: inline-flex;
  padding: 3px 10px;
  border-radius: 99px;
  font-size: 10.5px;
  font-family: var(--font-mono);
  background: var(--chip-bg);
  border: 1px solid var(--border);
}
```

---

## Interacciones

### Transiciones base
- Duration: `150ms` para microinteracciones
- Duration: `200ms` para paneles/modales
- Easing: `ease` o `cubic-bezier(0.4, 0, 0.2, 1)`

### Focus states
```css
:focus-visible {
  outline: 2px solid var(--blue);
  outline-offset: 2px;
}
```

### Hover lift
```css
/* Lift sutil en hover */
transform: translateY(-1px);  /* cards pequeñas */
transform: translateY(-2px);  /* cards grandes */

/* Press feedback */
:active {
  transform: translateY(0);
  transition-duration: .05s;
}
```

---

## Keyboard Shortcuts

| Acción | Shortcut |
|--------|----------|
| Command palette | `⌘/Ctrl + K` |
| Nueva tarea | `N` |
| Buscar | `/` |
| Navegar Today | `1` |
| Navegar Inbox | `2` |
| Navegar Projects | `3` |
| Navegar Analytics | `4` |
| Navegar Settings | `5` |
| Aceptar sugerencia | `A` |
| Rechazar sugerencia | `X` |
| Editar sugerencia | `E` |
| Fusionar tarea | `M` |
| Toggle sidebar (mobile) | `B` |

---

## Animaciones

### Fade in (contenido nuevo)
```css
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}
```

### Command palette
```css
@keyframes cmdIn {
  from { opacity: 0; transform: scale(.98) translateY(-8px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}
```

### Task complete
```css
@keyframes taskComplete {
  to { opacity: .3; transform: translateX(8px); }
}
```

### Toast notification
```css
@keyframes toastIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}
```

---

## Z-Index Scale

| Layer | z-index |
|-------|---------|
| Base content | 1 |
| Sidebar | 40 |
| Mobile overlay | 45 |
| Topbar | 50 |
| Tooltips | 50 |
| Help panel | 60 |
| Command palette | 100 |
| Toasts | 200 |

---

## Mobile Sidebar Drawer

```css
@media (max-width: 768px) {
  .sidebar {
    position: fixed;
    width: 280px;
    transform: translateX(-100%);
    transition: transform .2s ease;
    z-index: 40;
  }

  .sidebar.open {
    transform: translateX(0);
  }

  .sidebar-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,.4);
    backdrop-filter: blur(2px);
    z-index: 35;
  }
}
```

---

## API Data Shapes

### Task
```typescript
interface Task {
  id: string;
  title: string;
  score: number;  // 0-100
  scoreBreakdown: {
    urgency: number;
    impact: number;
    effort: number;
    deadline: number;
    requester: number;
    dependencies: number;
    recurrence: number;
    context: number;
  };
  confidence: number;  // 0-1
  status: 'open' | 'suggested' | 'completed' | 'rejected';
  area: string;
  project?: string;
  client?: string;
  deadline?: string;  // ISO date
  source: 'outlook' | 'slack' | 'hubspot' | 'granola' | 'github' | 'drive';
  evidence: {
    quote: string;
    sourceUrl: string;
  };
  createdAt: string;
}
```

### Project
```typescript
interface Project {
  id: string;
  name: string;
  area: string;
  client?: string;
  openTasks: number;
  completedTasks: number;
  lastActivity: string;
  deal?: {
    value: number;
    stage: string;
  };
}
```

### Connector
```typescript
interface Connector {
  id: string;
  type: 'outlook' | 'slack' | 'hubspot' | 'granola' | 'github' | 'drive';
  status: 'connected' | 'error' | 'pending';
  lastSync: string;
  itemsProcessed: number;
  tokensUsed: number;
}
```

---

## Scoring Weights (default)

```yaml
# config/scoring.yaml
urgency: 0.20
impact: 0.20
effort: 0.15
deadline: 0.15
requester: 0.12
dependencies: 0.08
recurrence: 0.05
context: 0.05
```

---

## Notas de Implementación

1. **Theming**: Usar `data-theme="light"` en `<html>` para cambiar tema. Solo sobrescribir tokens de color.

2. **Fonts**: Cargar Fraunces (display), Inter (body), JetBrains Mono (mono) via Google Fonts o self-hosted.

3. **Icons**: SVG inline con `currentColor`. No usar icon fonts.

4. **States**: Cada componente interactivo necesita `:hover`, `:active`, `:focus-visible`, `:disabled`.

5. **Mobile**: Sidebar es drawer que se abre con hamburger. Cierra al navegar o tap en overlay.

6. **Accessibility**:
   - Todos los botones con `aria-label` si solo icono
   - Focus visible con outline blue
   - Hit targets mínimo 44px en mobile

7. **Performance**:
   - `backdrop-filter` solo en topbar y command palette
   - Transitions en GPU props (`transform`, `opacity`)
   - Lazy load vistas no activas
