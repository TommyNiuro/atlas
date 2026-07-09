#!/bin/bash
# Arranque robusto de la API: asegura que colima + postgres/redis esten arriba
# antes de uvicorn. Si la Mac reinicio, colima puede estar abajo y la api
# entraria en crash-loop (auditoría 07-09). El plist apunta a este wrapper.
export PATH="/Users/enderys/.local/bin:/usr/local/bin:/usr/bin:/bin"
colima status >/dev/null 2>&1 || colima start >/dev/null 2>&1 || true
docker compose -f /Users/enderys/atlas/infra/docker-compose.yml up -d >/dev/null 2>&1 || true
cd /Users/enderys/atlas/apps/api || exit 1
exec uv run uvicorn atlas.main:app --host 127.0.0.1 --port 8000
