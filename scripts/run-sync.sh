#!/bin/bash
# Sync horario de Atlas: conectores + pipeline de agentes. Tolera fuentes sin
# autenticar (el conector queda en error y se reintenta a la hora siguiente).
export PATH="/Users/enderys/.local/bin:/usr/local/bin:/usr/bin:/bin"
cd /Users/enderys/atlas/apps/api || exit 1
echo "=== sync $(date '+%F %T') ==="
uv run python -m atlas.connectors.sync outlook_mail || true
uv run python -m atlas.connectors.sync outlook_cal || true
uv run python -m atlas.agents.orchestrator || true
