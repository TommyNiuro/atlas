"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, connectWS } from "../lib/api";

type Task = {
  id: string; title: string; status: string; due_date: string | null;
  evidence_quote: string | null; deep_link: string | null; score: number | null;
  rank: number | null; breakdown: Record<string, number> | null; confidence: number | null;
};
type Today = {
  top5: Task[]; resto: Task[]; sugeridas_pendientes: number;
  agenda: { subject: string; start: string; end: string }[]; carga_del_dia: number;
};
type Vista = "hoy" | "sugerencias" | "settings";

const SALUDO = new Intl.DateTimeFormat("es", { weekday: "long", day: "numeric", month: "long" });

function Score({ t }: { t: Task }) {
  if (t.score == null) return null;
  return (
    <span className="score">
      {Math.round(t.score)}
      {t.breakdown && (
        <span className="tip">
          {Object.entries(t.breakdown).filter(([, v]) => v !== 0).map(([k, v]) => (
            <div key={k}>{k.replace(/_/g, " ")}: {v > 0 ? "+" : ""}{v}</div>
          ))}
        </span>
      )}
    </span>
  );
}

function FilaTarea({ t, sel, onDone }: { t: Task; sel?: boolean; onDone: () => void }) {
  return (
    <div className={`task-row${sel ? " sel" : ""}`}>
      <button className="task-check" title="Completar (C)" onClick={onDone} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="task-title">
          {t.deep_link ? <a href={t.deep_link} target="_blank" rel="noreferrer">{t.title}</a> : t.title}
        </div>
        {t.evidence_quote && <div className="evidencia">&ldquo;{t.evidence_quote}&rdquo;</div>}
      </div>
      {t.due_date && <span className="task-meta">{t.due_date}</span>}
      <Score t={t} />
    </div>
  );
}

function VistaHoy({ data, error, retry, onDone }: {
  data: Today | null; error: string | null; retry: () => void; onDone: (id: string) => void;
}) {
  if (error) return <div className="estado-error">No pude cargar el día: {error}<br /><button onClick={retry}>Reintentar</button></div>;
  if (!data) return <div>{[1, 2, 3, 4, 5].map((i) => <div key={i} className="skeleton" />)}</div>;
  const todas = [...data.top5, ...data.resto];
  return (
    <div className="layout-hoy">
      <div className="card">
        <h3>Top 5 del día</h3>
        {todas.length === 0 && <div className="estado-vacio">Sin tareas abiertas. Corre <kbd>task sync</kbd> o crea una con <kbd>⌘K</kbd>.</div>}
        {data.top5.map((t) => <FilaTarea key={t.id} t={t} onDone={() => onDone(t.id)} />)}
        {data.resto.length > 0 && (
          <details style={{ marginTop: 10 }}>
            <summary style={{ color: "var(--muted)", cursor: "pointer" }}>{data.resto.length} más en el ranking</summary>
            {data.resto.map((t) => <FilaTarea key={t.id} t={t} onDone={() => onDone(t.id)} />)}
          </details>
        )}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div className="card">
          <h3>Carga del día</h3>
          <div className="task-meta">{Math.round(data.carga_del_dia * 100)}% comprometido</div>
          <div className="carga-bar"><div className="carga-fill" style={{ width: `${data.carga_del_dia * 100}%` }} /></div>
        </div>
        <div className="card">
          <h3>Agenda de hoy</h3>
          {data.agenda.length === 0 && <div className="estado-vacio">Sin eventos hoy. Conecta el calendario con <kbd>task auth-calendar</kbd>.</div>}
          {data.agenda.map((e, i) => (
            <div key={i} className="agenda-item">
              <span className="agenda-hora">{e.start?.slice(11, 16)}–{e.end?.slice(11, 16)}</span>
              <span>{e.subject}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function VistaSugerencias({ items, error, retry, onTriage, sel }: {
  items: Task[] | null; error: string | null; retry: () => void;
  onTriage: (id: string, action: string) => void; sel: number;
}) {
  if (error) return <div className="estado-error">No pude cargar la bandeja: {error}<br /><button onClick={retry}>Reintentar</button></div>;
  if (!items) return <div>{[1, 2, 3].map((i) => <div key={i} className="skeleton" />)}</div>;
  return (
    <div className="card">
      <div className="hints">
        <span><kbd>A</kbd> aceptar</span><span><kbd>X</kbd> rechazar</span>
        <span><kbd>E</kbd> editar y aceptar</span><span><kbd>↑↓</kbd> navegar</span>
      </div>
      {items.length === 0 && <div className="estado-vacio">Bandeja limpia. Nada esperando tu ojo. ✨</div>}
      {items.map((t, i) => (
        <div key={t.id} className={`task-row${i === sel ? " sel" : ""}`}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="task-title">{t.title}</div>
            {t.evidence_quote && <div className="evidencia">&ldquo;{t.evidence_quote}&rdquo;</div>}
          </div>
          <span className="task-meta">conf {Math.round((t.confidence ?? 0) * 100)}%</span>
          <button className="btn" style={{ margin: 0, padding: "4px 10px" }} onClick={() => onTriage(t.id, "accept")}>A</button>
          <button className="btn" style={{ margin: 0, padding: "4px 10px", background: "var(--raised)" }} onClick={() => onTriage(t.id, "reject")}>X</button>
        </div>
      ))}
    </div>
  );
}

function VistaSettings() {
  const [sources, setSources] = useState<{ kind: string; status: string; last_sync_at: string | null; autenticado: boolean }[] | null>(null);
  const [scoring, setScoring] = useState<{ weights: Record<string, number> } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const load = useCallback(() => {
    setError(null);
    api.sources().then(setSources).catch((e) => setError(String(e)));
    api.scoring().then(setScoring).catch((e) => setError(String(e)));
  }, []);
  useEffect(load, [load]);

  if (error) return <div className="estado-error">Error en settings: {error}<br /><button onClick={load}>Reintentar</button></div>;
  return (
    <div className="layout-hoy">
      <div className="card">
        <h3>Conectores</h3>
        {!sources && <div className="skeleton" />}
        {sources?.length === 0 && <div className="estado-vacio">Ninguna fuente configurada aún. Corre <kbd>task auth-outlook</kbd>.</div>}
        {sources?.map((s) => (
          <div key={s.kind} className="conector">
            <span><span className={`dot ${s.status}`} />{s.kind}</span>
            <span className="task-meta">{s.autenticado ? (s.last_sync_at ? `sync ${s.last_sync_at.slice(0, 16)}` : "sin sync aún") : "sin autenticar"}</span>
          </div>
        ))}
      </div>
      <div className="card">
        <h3>Pesos del scoring</h3>
        {!scoring && <div className="skeleton" />}
        {scoring && Object.entries(scoring.weights).map(([k, v]) => (
          <div key={k} className="peso-row">
            <span className="task-meta">{k.replace(/_/g, " ")}</span>
            <input type="number" value={v} onChange={(e) =>
              setScoring({ ...scoring, weights: { ...scoring.weights, [k]: Number(e.target.value) } })} />
          </div>
        ))}
        {scoring && (
          <button className="btn" onClick={() =>
            api.saveScoring(scoring.weights).then(() => { setSaved(true); setTimeout(() => setSaved(false), 2000); })}>
            {saved ? "Guardado, ranking recalculado" : "Guardar y recalcular"}
          </button>
        )}
      </div>
    </div>
  );
}

function Palette({ onClose, onCreated, goto }: {
  onClose: () => void; onCreated: () => void; goto: (v: Vista) => void;
}) {
  const [q, setQ] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => inputRef.current?.focus(), []);
  const navs: [string, Vista][] = [["Ir a Hoy", "hoy"], ["Ir a Sugerencias", "sugerencias"], ["Ir a Settings", "settings"]];
  const filtered = navs.filter(([n]) => n.toLowerCase().includes(q.toLowerCase()));

  const crear = async () => {
    if (!q.trim()) return;
    await api.create(q);
    onCreated();
    onClose();
  };
  return (
    <div className="palette-overlay" onClick={onClose}>
      <div className="palette" onClick={(e) => e.stopPropagation()}>
        <input ref={inputRef} value={q} placeholder="Crea una tarea en lenguaje natural o navega…"
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") crear(); if (e.key === "Escape") onClose(); }} />
        {q.trim() && <div className="res sel" onClick={crear}>➕ Crear tarea: &ldquo;{q}&rdquo; <span className="task-meta">(Enter, entiende &ldquo;el jueves 9am&rdquo;)</span></div>}
        {filtered.map(([n, v]) => <div key={v} className="res" onClick={() => { goto(v); onClose(); }}>{n}</div>)}
        <div className="hint">Esc para cerrar · las fechas en español se parsean solas</div>
      </div>
    </div>
  );
}

export default function App() {
  const [vista, setVista] = useState<Vista>("hoy");
  const [today, setToday] = useState<Today | null>(null);
  const [sugs, setSugs] = useState<Task[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sugsErr, setSugsErr] = useState<string | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [sel, setSel] = useState(0);

  const refresh = useCallback(() => {
    setErr(null);
    api.today().then(setToday).catch((e) => setErr(String(e)));
    api.suggestions().then((d) => { setSugs(d); setSugsErr(null); }).catch((e) => setSugsErr(String(e)));
  }, []);

  const doneTask = useCallback((id: string) => api.complete(id).then(refresh), [refresh]);
  const toggleTheme = () => {
    const t = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = t;
    localStorage.setItem("atlas-theme", t);
  };

  useEffect(() => {
    refresh();
    return connectWS(refresh);
  }, [refresh]);

  const triage = useCallback(async (id: string, action: string) => {
    if (action === "edit") {
      const t = sugs?.find((x) => x.id === id);
      const nuevo = prompt("Título:", t?.title ?? "");
      if (nuevo == null) return;
      await api.triage(id, "edit", { title: nuevo });
    } else {
      await api.triage(id, action);
    }
    refresh();
  }, [sugs, refresh]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "s") {
        e.preventDefault();
        api.sync().then(() => setTimeout(refresh, 1500)); // sync manual
        return;
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
        return;
      }
      if (paletteOpen || (e.target as HTMLElement).tagName === "INPUT") return;
      if (e.key === "/") {
        e.preventDefault();
        setPaletteOpen(true);
        return;
      }
      if (vista === "sugerencias" && sugs?.length) {
        const cur = sugs[Math.min(sel, sugs.length - 1)];
        if (e.key === "ArrowDown") setSel((s) => Math.min(s + 1, sugs.length - 1));
        if (e.key === "ArrowUp") setSel((s) => Math.max(s - 1, 0));
        if (cur && ["a", "x", "e"].includes(e.key.toLowerCase()))
          triage(cur.id, { a: "accept", x: "reject", e: "edit" }[e.key.toLowerCase()]!);
      }
      if (vista === "hoy" && today) {
        const n = parseInt(e.key, 10);
        // 1-5 abre el origen de la tarea N; C completa la primera del top
        if (n >= 1 && n <= 5 && today.top5[n - 1]?.deep_link)
          window.open(today.top5[n - 1].deep_link!, "_blank");
        if (e.key.toLowerCase() === "c" && today.top5[0]) doneTask(today.top5[0].id);
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [paletteOpen, vista, sugs, sel, triage, today, refresh, doneTask]);

  const hoyTxt = SALUDO.format(new Date());
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="logo">Atlas<span>.</span></div>
        <button className={`nav-item${vista === "hoy" ? " active" : ""}`} onClick={() => setVista("hoy")}>Hoy</button>
        <button className={`nav-item${vista === "sugerencias" ? " active" : ""}`} onClick={() => setVista("sugerencias")}>
          Sugerencias {today?.sugeridas_pendientes ? <span className="badge">{today.sugeridas_pendientes}</span> : null}
        </button>
        <button className={`nav-item${vista === "settings" ? " active" : ""}`} onClick={() => setVista("settings")}>Settings</button>
        <div className="sidebar-foot">
          <button className="nav-item" onClick={toggleTheme}>Cambiar tema</button>
          <div style={{ padding: "6px 10px" }}><kbd>⌘K</kbd> palette · <kbd>/</kbd> buscar · <kbd>A/X/E</kbd> triage</div>
        </div>
      </aside>
      <main className="main">
        <div className="saludo" style={{ textTransform: "capitalize" }}>{hoyTxt}</div>
        <div className="sub">
          {vista === "hoy" && "Tu día ordenado por el Priority Engine."}
          {vista === "sugerencias" && "Tareas detectadas con confianza media: tú decides."}
          {vista === "settings" && "Conectores y personalidad del scoring."}
        </div>
        {vista === "hoy" && <VistaHoy data={today} error={err} retry={refresh} onDone={(id) => api.complete(id).then(refresh)} />}
        {vista === "sugerencias" && <VistaSugerencias items={sugs} error={sugsErr} retry={refresh} onTriage={triage} sel={sel} />}
        {vista === "settings" && <VistaSettings />}
      </main>
      {paletteOpen && <Palette onClose={() => setPaletteOpen(false)} onCreated={refresh} goto={setVista} />}
    </div>
  );
}
