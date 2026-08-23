#!/usr/bin/env bash
# run.sh — EIN Kommando: Härtung/Firewall/Storage -> Docker + Caddy + weblab.
# Danach im Browser die Server-IP öffnen und den Setup-Assistenten durchlaufen
# (Admin + Passwort + Verwaltungs-Domain).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[ "$(id -u)" -eq 0 ] || { echo "Bitte als root ausführen (sudo)."; exit 1; }

if [ -f "$HERE/box.env" ]; then set -a; . "$HERE/box.env"; set +a; fi

echo "### 1) Basis-Härtung + Firewall + Storage ###"
DATA_MOUNT="${DATA_MOUNT:-/mnt/data}" DATA_DEVICE="${DATA_DEVICE:-}" \
ADMIN_SSH_PUBKEY="${ADMIN_SSH_PUBKEY:-}" bash "$HERE/bootstrap.sh"

echo "### 2) Docker + Caddy + weblab ###"
bash "$HERE/install.sh"
