#!/usr/bin/env bash
# Crea /Applications/Atlas.app: ventana propia (Chrome modo app) sobre los
# servicios launchd. ponytail: el empaquetado Tauri con server embebido es V2
# (asi lo define la spec); esta .app cubre el uso diario con 40 lineas.
set -euo pipefail

APP="/Applications/Atlas.app"
URL="http://localhost:3005"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Atlas</string>
  <key>CFBundleDisplayName</key><string>Atlas</string>
  <key>CFBundleIdentifier</key><string>io.niuro.atlas.app</string>
  <key>CFBundleVersion</key><string>0.5.0</string>
  <key>CFBundleExecutable</key><string>atlas</string>
  <key>CFBundleIconFile</key><string>atlas</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
</dict>
</plist>
PLIST

cat > "$APP/Contents/MacOS/atlas" <<LAUNCHER
#!/bin/bash
# Arranca (si hace falta) los servicios de Atlas y abre la ventana de la app.
launchctl kickstart gui/\$(id -u)/io.niuro.atlas.api 2>/dev/null || true
launchctl kickstart gui/\$(id -u)/io.niuro.atlas.web 2>/dev/null || true
for i in \$(seq 1 30); do
  curl -s -o /dev/null -m 1 $URL && break
  sleep 1
done
if [ -d "/Applications/Google Chrome.app" ]; then
  open -na "Google Chrome" --args --app=$URL
else
  open $URL
fi
LAUNCHER
chmod +x "$APP/Contents/MacOS/atlas"

# icono: A dorada sobre navy, generado con Pillow -> icns
if [ ! -f "$APP/Contents/Resources/atlas.icns" ]; then
  TMP=$(mktemp -d)
  uv run --with pillow python - "$TMP/icon.png" <<'PY'
import sys
from PIL import Image, ImageDraw, ImageFont

png = sys.argv[1]
S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([64, 64, S - 64, S - 64], radius=190, fill=(10, 16, 32, 255))
font = None
for path in ("/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
             "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
             "/System/Library/Fonts/HelveticaNeue.ttc"):
    try:
        font = ImageFont.truetype(path, 560)
        break
    except OSError:
        continue
d.text((S / 2, S / 2 - 20), "A", font=font, fill=(255, 209, 102, 255), anchor="mm")
d.ellipse([S / 2 + 150, S - 340, S / 2 + 210, S - 280], fill=(91, 123, 255, 255))
img.save(png)
PY
  mkdir -p "$TMP/atlas.iconset"
  for s in 16 32 64 128 256 512; do
    sips -z $s $s "$TMP/icon.png" --out "$TMP/atlas.iconset/icon_${s}x${s}.png" >/dev/null
    sips -z $((s*2)) $((s*2)) "$TMP/icon.png" --out "$TMP/atlas.iconset/icon_${s}x${s}@2x.png" >/dev/null
  done
  iconutil -c icns "$TMP/atlas.iconset" -o "$APP/Contents/Resources/atlas.icns"
  rm -rf "$TMP"
fi

codesign --force --deep -s - "$APP" 2>/dev/null || true
echo "Listo: $APP"
