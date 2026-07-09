#!/usr/bin/env bash
# Toma el codigo nuevo (git pull opcional), reconstruye la web y reinicia los
# servicios launchd para que la .app corra la version actual. Sin rebuild de la
# .app (esa solo cambia si cambia make-mac-app.sh).
set -euo pipefail
ROOT="/Users/enderys/atlas"
cd "$ROOT"

echo "==> deps + build web"
(cd apps/api && uv sync >/dev/null)
(cd apps/web && pnpm install --silent && pnpm build >/dev/null)

echo "==> migraciones"
(cd apps/api && uv run alembic upgrade head)

echo "==> reinicio de servicios"
launchctl kickstart -k "gui/$(id -u)/io.niuro.atlas.api" 2>/dev/null || true
launchctl kickstart -k "gui/$(id -u)/io.niuro.atlas.web" 2>/dev/null || true

echo "==> esperando el server..."
for _ in $(seq 1 30); do
  curl -s -o /dev/null -m 2 http://127.0.0.1:8000/health && { echo "Listo: Atlas corre el build nuevo."; exit 0; }
  sleep 1
done
echo "AVISO: la api no respondio a tiempo; revisa logs/api.log"
