#!/usr/bin/env bash
# install.sh — Kontrollzentrum (Cockpit) + Podman + Caddy + Cloudflare-DNS.
# Läuft als root auf der Box (nach bootstrap.sh). Env: DOMAIN, CF_TOKEN, DATA_MOUNT.
set -euo pipefail
DOMAIN="${DOMAIN:?}"; CF_TOKEN="${CF_TOKEN:-}"; DATA_MOUNT="${DATA_MOUNT:-/mnt/data}"
ALLOW_ROOT_LOGIN="${ALLOW_ROOT_LOGIN:-true}"; ADMIN_USER="${ADMIN_USER:-}"; ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"
export DEBIAN_FRONTEND=noninteractive

echo "== Cockpit + Module (Storage/Netzwerk/Podman) + Podman =="
apt-get update -y
apt-get install -y --no-install-recommends \
  cockpit cockpit-storaged cockpit-networkmanager cockpit-podman podman \
  jq curl ca-certificates gnupg

echo "== Caddy (offizielles Repo) =="
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  apt-get update -y
  apt-get install -y caddy
fi

echo "== Cockpit hinter Reverse-Proxy =="
install -d /etc/cockpit
sed "s/__DOMAIN__/$DOMAIN/g" "$HERE/cockpit.conf" > /etc/cockpit/cockpit.conf
systemctl enable --now cockpit.socket
systemctl try-restart cockpit || true

echo "== Cockpit-Login (Linux-User via PAM) =="
# Ubuntu/Debian sperren root standardmäßig vom Cockpit-Web-Login (/etc/cockpit/disallowed-users).
# Damit "Login mit dem Linux-User" auf einem frischen (nur-root-)Server sofort funktioniert,
# wird root freigeschaltet — abgesichert durch HTTPS, Firewall und fail2ban.
touch /etc/cockpit/disallowed-users
# Optionaler dedizierter sudo-Admin (empfohlen gegenüber root-Web-Login):
if [ -n "$ADMIN_USER" ]; then
  id "$ADMIN_USER" >/dev/null 2>&1 || adduser --disabled-password --gecos "" "$ADMIN_USER"
  usermod -aG sudo "$ADMIN_USER"
  [ -n "$ADMIN_PASSWORD" ] && echo "$ADMIN_USER:$ADMIN_PASSWORD" | chpasswd
  sed -i "\|^$ADMIN_USER\$|d" /etc/cockpit/disallowed-users
  echo "  Admin-User: $ADMIN_USER (sudo)"
fi
if [ "$ALLOW_ROOT_LOGIN" = "true" ]; then
  sed -i '/^root$/d' /etc/cockpit/disallowed-users
  echo "  root-Web-Login aktiviert."
else
  grep -qx root /etc/cockpit/disallowed-users || echo root >> /etc/cockpit/disallowed-users
  echo "  root-Web-Login gesperrt (nur ${ADMIN_USER:-anderer sudo-User})."
fi

echo "== Ports 80/443 freimachen (alte Docker-Container früherer Designs entfernen) =="
# Der Reverse-Proxy ist Caddy (systemd). Früher testweise gestartete Docker-Container
# (Caddy/Apache/Portainer) belegen sonst 80/443 und verhindern den Caddy-Start.
if command -v docker >/dev/null 2>&1 && systemctl is-active --quiet docker; then
  ids="$( { docker ps -q --filter publish=80; docker ps -q --filter publish=443; } 2>/dev/null | sort -u )"
  if [ -n "$ids" ]; then
    echo "  entferne Container auf 80/443: $ids"
    docker rm -f $ids >/dev/null 2>&1 || true
  else
    echo "  keine Docker-Container auf 80/443"
  fi
fi

echo "== Caddy-Konfig (TLS + Proxy -> Cockpit 9090) =="
sed "s/__DOMAIN__/$DOMAIN/g" "$HERE/Caddyfile" > /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile 2>&1 | sed 's/^/  caddy-validate: /' || true
systemctl enable caddy || true
systemctl restart caddy || true
sleep 2
if ! systemctl is-active --quiet caddy; then
  echo "  WARN: Caddy nicht aktiv — Diagnose:"
  systemctl status caddy --no-pager -l 2>&1 | sed 's/^/    /' | head -n 20 || true
  journalctl -u caddy --no-pager -n 40 2>&1 | sed 's/^/    journal: /' || true
  echo "  Ports (80/443/9090):"; ss -tlnp 2>/dev/null | grep -E ':(80|443|9090)\b' | sed 's/^/    /' || true
fi

echo "== Server-IP =="
SERVER_IP="$(curl -s --max-time 10 https://api.ipify.org || true)"; [ -n "$SERVER_IP" ] || SERVER_IP="$(hostname -I | awk '{print $1}')"
echo "  $SERVER_IP"

echo "== Cloudflare-DNS (Apex -> Box; optional/best-effort) =="
if [ -z "$CF_TOKEN" ]; then
  echo "  Kein CF_TOKEN gesetzt -> DNS überspringen."
  echo "  -> In deinem DNS einen A-Record $DOMAIN -> $SERVER_IP setzen (Cloudflare: DNS only/grau)."
else
  ZRESP="$(curl -s -H "Authorization: Bearer $CF_TOKEN" "https://api.cloudflare.com/client/v4/zones?name=$DOMAIN")"
  ZONE="$(echo "$ZRESP" | jq -r '.result[0].id // empty')"
  if [ -z "$ZONE" ]; then
    echo "  WARN: Zone nicht abrufbar: success=$(echo "$ZRESP" | jq -r '.success // "?"') errors=$(echo "$ZRESP" | jq -rc '.errors // []')"
    echo "  -> A-Record $DOMAIN -> $SERVER_IP manuell setzen (DNS only), oder Token-IP-Filter auf $SERVER_IP erweitern."
  else
    # Stale A-Records für Apex entfernen, dann sauber neu setzen (DNS only / proxied=false).
    for rid in $(curl -s -H "Authorization: Bearer $CF_TOKEN" "https://api.cloudflare.com/client/v4/zones/$ZONE/dns_records?type=A&name=$DOMAIN" | jq -r '.result[]?.id'); do
      curl -s -o /dev/null -X DELETE -H "Authorization: Bearer $CF_TOKEN" "https://api.cloudflare.com/client/v4/zones/$ZONE/dns_records/$rid"
    done
    curl -s -o /dev/null -X POST -H "Authorization: Bearer $CF_TOKEN" -H 'Content-Type: application/json' \
      "https://api.cloudflare.com/client/v4/zones/$ZONE/dns_records" \
      -d "{\"type\":\"A\",\"name\":\"$DOMAIN\",\"content\":\"$SERVER_IP\",\"ttl\":120,\"proxied\":false}"
    echo "  $DOMAIN -> $SERVER_IP"
  fi
fi

echo "== Status =="
systemctl is-active cockpit.socket caddy | sed 's/^/  /'
echo "== fertig. Kontrollzentrum: https://$DOMAIN (Login = Linux-User) =="
