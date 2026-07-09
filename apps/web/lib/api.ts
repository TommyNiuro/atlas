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
};

export function connectWS(onChange: () => void): () => void {
  try {
    const ws = new WebSocket(`${BASE.replace("http", "ws")}/ws`);
    ws.onmessage = onChange;
    const ping = setInterval(() => ws.readyState === 1 && ws.send("ping"), 30000);
    return () => {
      clearInterval(ping);
      ws.close();
    };
  } catch {
    return () => {};
  }
}
