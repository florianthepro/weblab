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
ALLOW_ROOT_LOGIN="${ALLOW_ROOT_LOGIN:-true}"; ADMIN_USER="${ADMIN_USER:-}"; ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"

if [ -z "$DOMAIN" ] && [ -t 0 ]; then read -rp "Manage-Domain (z.B. example.com): " DOMAIN; fi
[ -n "$DOMAIN" ] || { echo "DOMAIN ist nötig (in box.env eintragen oder als ENV setzen)."; exit 1; }
if [ -z "$CF_TOKEN" ] && [ -t 0 ]; then
  read -rsp "Cloudflare API-Token (Enter = überspringen, DNS dann manuell): " CF_TOKEN; echo
fi

echo "### 1) Basis-Härtung + Firewall + Storage ###"
DATA_MOUNT="$DATA_MOUNT" DATA_DEVICE="$DATA_DEVICE" ADMIN_SSH_PUBKEY="$ADMIN_SSH_PUBKEY" \
  bash "$HERE/bootstrap.sh"

echo "### 2) Kontrollzentrum (Cockpit) + Caddy + DNS ###"
DOMAIN="$DOMAIN" CF_TOKEN="$CF_TOKEN" DATA_MOUNT="$DATA_MOUNT" \
  ALLOW_ROOT_LOGIN="$ALLOW_ROOT_LOGIN" ADMIN_USER="$ADMIN_USER" ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  bash "$HERE/install.sh"

echo "### FERTIG. Kontrollzentrum: https://$DOMAIN  (Login = Linux-User) ###"
