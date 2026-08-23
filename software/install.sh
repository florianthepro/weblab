#!/usr/bin/env bash
# install.sh — Docker + Caddy + weblab-Dienst installieren.
# Läuft als root auf einem frischen Ubuntu 24.04 (nach bootstrap.sh).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
TARGET=/opt/weblab
export DEBIAN_FRONTEND=noninteractive

echo "== Pakete (Python, Docker, Werkzeuge) =="
apt-get update -y
apt-get install -y --no-install-recommends \
  python3 python3-minimal ca-certificates curl gnupg jq iproute2 util-linux

if ! command -v docker >/dev/null 2>&1; then
  echo "== Docker (offizielles Repo) =="
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin
fi
systemctl enable --now docker

if ! command -v caddy >/dev/null 2>&1; then
  echo "== Caddy (offizielles Repo) =="
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y
  apt-get install -y caddy
fi

echo "== weblab-Dateien nach $TARGET =="
install -d "$TARGET" /var/lib/weblab /var/lib/weblab/data
rm -rf "$TARGET/weblab" "$TARGET/connectors"
cp -r "$HERE/weblab" "$TARGET/weblab"
install -d "$TARGET/connectors"
if [ -d "$REPO_ROOT/connectors/keep" ]; then
  cp -r "$REPO_ROOT/connectors/keep" "$TARGET/connectors/keep"
else
  install -d "$TARGET/connectors/keep"
fi
find "$TARGET" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
chmod 700 /var/lib/weblab

# Version festhalten (für Anzeige + Auto-Update-Vergleich).
if command -v git >/dev/null 2>&1 && git -C "$REPO_ROOT" rev-parse --short HEAD >/dev/null 2>&1; then
  printf '%s (%s)\n' "$(git -C "$REPO_ROOT" rev-parse --short HEAD)" "$(date -u +%F)" >"$TARGET/VERSION"
fi

echo "== Auto-Update (Timer) =="
cp "$HERE/update.sh" "$TARGET/update.sh"
chmod +x "$TARGET/update.sh"
cp "$HERE/weblab-update.service" /etc/systemd/system/weblab-update.service
cp "$HERE/weblab-update.timer" /etc/systemd/system/weblab-update.timer

echo "== Ports 80/443 freimachen (Reste früherer Installationen) =="
if systemctl is-active --quiet docker; then
  ids="$( { docker ps -q --filter publish=80; docker ps -q --filter publish=443; } 2>/dev/null | sort -u )"
  [ -n "$ids" ] && docker rm -f $ids >/dev/null 2>&1 || true
fi
for unit in cockpit.socket cockpit apache2 nginx; do
  systemctl disable --now "$unit" >/dev/null 2>&1 || true
done

echo "== Caddy-Startkonfiguration =="
install -d /etc/caddy
if [ ! -s /etc/caddy/Caddyfile ] || ! grep -q "8099" /etc/caddy/Caddyfile; then
  cp "$HERE/Caddyfile" /etc/caddy/Caddyfile
fi
caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1 \
  || { echo "  Caddyfile ungültig — Startkonfiguration wird gesetzt."; cp "$HERE/Caddyfile" /etc/caddy/Caddyfile; }
systemctl enable caddy >/dev/null 2>&1 || true
systemctl restart caddy || true

echo "== weblab-Dienst =="
cp "$HERE/weblab.service" /etc/systemd/system/weblab.service
systemctl daemon-reload
systemctl enable weblab >/dev/null 2>&1 || true
systemctl restart weblab
# Auto-Update-Timer aktivieren (sofern nicht ausdrücklich abgeschaltet).
if [ ! -f /var/lib/weblab/autoupdate-off ]; then
  systemctl enable --now weblab-update.timer >/dev/null 2>&1 || true
fi
sleep 2

echo "== Status =="
for unit in docker caddy weblab; do
  printf '  %-8s %s\n' "$unit" "$(systemctl is-active "$unit" 2>/dev/null || echo unbekannt)"
done
if ! systemctl is-active --quiet weblab; then
  echo "  Fehlerausgabe weblab:"
  journalctl -u weblab --no-pager -n 25 2>&1 | sed 's/^/    /' || true
fi
IP="$(curl -s --max-time 8 https://api.ipify.org || hostname -I | awk '{print $1}')"
echo "== fertig. Oberfläche: http://${IP}  (Setup: Admin + Passwort + Domain) =="
