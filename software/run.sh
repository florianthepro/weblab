#!/usr/bin/env bash
# run.sh — EIN Einstieg: Konfiguration laden/abfragen -> Härtung/Firewall/Storage
#          -> Kontrollzentrum (Cockpit + Caddy) installieren.
# Als root ausführen (sudo). Frisches Ubuntu 24.04 LTS.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[ "$(id -u)" -eq 0 ] || { echo "Bitte als root ausführen (sudo)."; exit 1; }

# Konfiguration: box.env (aus box.env.example kopiert) falls vorhanden, sonst abfragen.
if [ -f "$HERE/box.env" ]; then set -a; . "$HERE/box.env"; set +a; fi
DOMAIN="${DOMAIN:-}"; CF_TOKEN="${CF_TOKEN:-}"
DATA_MOUNT="${DATA_MOUNT:-/mnt/data}"; DATA_DEVICE="${DATA_DEVICE:-}"; ADMIN_SSH_PUBKEY="${ADMIN_SSH_PUBKEY:-}"

if [ -z "$DOMAIN" ]; then read -rp "Manage-Domain (z.B. example.com): " DOMAIN; fi
[ -n "$DOMAIN" ] || { echo "DOMAIN ist nötig."; exit 1; }
if [ -z "$CF_TOKEN" ]; then
  read -rsp "Cloudflare API-Token (Enter = überspringen, DNS dann manuell): " CF_TOKEN; echo
fi

echo "### 1) Basis-Härtung + Firewall + Storage ###"
DATA_MOUNT="$DATA_MOUNT" DATA_DEVICE="$DATA_DEVICE" ADMIN_SSH_PUBKEY="$ADMIN_SSH_PUBKEY" \
  bash "$HERE/bootstrap.sh"

echo "### 2) Kontrollzentrum (Cockpit) + Caddy + DNS ###"
DOMAIN="$DOMAIN" CF_TOKEN="$CF_TOKEN" DATA_MOUNT="$DATA_MOUNT" \
  bash "$HERE/install.sh"

echo "### FERTIG. Kontrollzentrum: https://$DOMAIN  (Login = Linux-User) ###"
