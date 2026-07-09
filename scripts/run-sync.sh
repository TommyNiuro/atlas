#!/bin/bash
# Sync horario de Atlas: conectores + pipeline de agentes. Respeta quiet hours
# y notifica en macOS si algo falla (auditoría 07-09).
export PATH="/Users/enderys/.local/bin:/usr/local/bin:/usr/bin:/bin"
set -a; . /Users/enderys/atlas/.env 2>/dev/null; set +a
cd /Users/enderys/atlas/apps/api || exit 1

# quiet hours: no sincronizar dentro del rango (default 22:00-06:30)
QH="${QUIET_HOURS:-22:00-06:30}"
now=$(date +%H%M)
ini=$(echo "$QH" | cut -d- -f1 | tr -d :)
fin=$(echo "$QH" | cut -d- -f2 | tr -d :)
if [ "$ini" -gt "$fin" ]; then  # cruza medianoche
  { [ "$now" -ge "$ini" ] || [ "$now" -lt "$fin" ]; } && { echo "quiet hours ($QH), salto"; exit 0; }
else
  { [ "$now" -ge "$ini" ] && [ "$now" -lt "$fin" ]; } && { echo "quiet hours ($QH), salto"; exit 0; }
fi

notify() { osascript -e "display notification \"$1\" with title \"Atlas\"" 2>/dev/null || true; }

echo "=== sync $(date '+%F %T') ==="
uv run python -m atlas.connectors.sync outlook_mail || notify "Falló el sync de Outlook Mail"
uv run python -m atlas.connectors.sync outlook_cal  || notify "Falló el sync de Outlook Calendar"
uv run python -m atlas.agents.orchestrator          || notify "Falló el pipeline de agentes"
