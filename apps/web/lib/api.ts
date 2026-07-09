const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function req(path: string, init?: RequestInit) {
  const r = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export const api = {
  today: () => req("/api/today"),
  suggestions: () => req("/api/suggestions"),
  sources: () => req("/api/sources"),
  scoring: () => req("/api/scoring"),
  saveScoring: (weights: Record<string, number>) =>
    req("/api/scoring", { method: "PUT", body: JSON.stringify({ weights }) }),
  triage: (id: string, action: string, extra?: object) =>
    req(`/api/tasks/${id}/triage`, { method: "POST", body: JSON.stringify({ action, ...extra }) }),
  complete: (id: string) => req(`/api/tasks/${id}/complete`, { method: "POST" }),
  create: (text: string) => req("/api/tasks", { method: "POST", body: JSON.stringify({ text }) }),
  snooze: (id: string) => req(`/api/tasks/${id}/snooze`, { method: "POST" }),
  sync: () => req("/api/sync", { method: "POST" }),
  search: (q: string) => req(`/api/search?q=${encodeURIComponent(q)}`),
  budget: () => req("/api/budget"),
  reauth: (kind: string) => req(`/api/sources/${kind}/reauth`, { method: "POST" }),
};

export function connectWS(onChange: () => void): () => void {
  let ws: WebSocket | null = null;
  let ping: ReturnType<typeof setInterval> | undefined;
  let retry: ReturnType<typeof setTimeout> | undefined;
  let backoff = 1000;
  let cerrado = false;

  const connect = () => {
    try {
      ws = new WebSocket(`${BASE.replace("http", "ws")}/ws`);
      ws.onmessage = onChange;
      ws.onopen = () => {
        backoff = 1000;
      };
      ws.onclose = () => {
        clearInterval(ping);
        if (cerrado) return;
        retry = setTimeout(connect, backoff); // reconecta con backoff hasta 30s
        backoff = Math.min(backoff * 2, 30000);
      };
      ping = setInterval(() => ws?.readyState === 1 && ws.send("ping"), 30000);
    } catch {
      retry = setTimeout(connect, backoff);
    }
  };
  connect();

  return () => {
    cerrado = true;
    clearInterval(ping);
    clearTimeout(retry);
    ws?.close();
  };
}
