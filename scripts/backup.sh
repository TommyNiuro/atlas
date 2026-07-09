#!/bin/bash
# pg_dump diario de Atlas a ~/AtlasBackups con rotacion de 14 dias (riesgo 9
# del spec: sin esto los datos viven solo en el volumen docker). launchd diario.
export PATH="/usr/local/bin:/usr/bin:/bin"
DEST="$HOME/AtlasBackups"
mkdir -p "$DEST"
f="$DEST/atlas-$(date +%Y%m%d-%H%M).sql.gz"
if docker exec atlas-postgres-1 pg_dump -U atlas atlas | gzip > "$f"; then
  echo "backup: $f ($(du -h "$f" | cut -f1))"
  ls -1t "$DEST"/atlas-*.sql.gz | tail -n +15 | xargs rm -f 2>/dev/null || true
else
  rm -f "$f"
  osascript -e 'display notification "Falló el backup de Atlas" with title "Atlas"' 2>/dev/null || true
  exit 1
fi
