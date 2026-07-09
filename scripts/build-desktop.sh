#!/usr/bin/env bash
# Compila Atlas como app nativa de Mac (Tauri, ventana WebKit real) e instala en
# /Applications. A diferencia del CRM, Atlas NO empaqueta el server (es Python +
# Postgres/Docker): la app es la ventana nativa sobre los servicios launchd.
# Requisitos: Rust (rustup) + Node. Ver docs/DESKTOP.md.
set -euo pipefail
ROOT="/Users/enderys/atlas"
cd "$ROOT"

echo "==> 1/3  Compilando la app nativa (Tauri)"
npx --yes @tauri-apps/cli@^2 build

APP=$(find src-tauri/target/release/bundle/macos -maxdepth 1 -name "Atlas.app" | head -1)
[ -n "$APP" ] || { echo "ERROR: no se generó Atlas.app"; exit 1; }

echo "==> 2/3  Instalando en /Applications"
rm -rf "/Applications/Atlas.app"
cp -R "$APP" "/Applications/Atlas.app"

echo "==> 3/3  Listo: /Applications/Atlas.app (nativa). Ábrela desde Launchpad."
