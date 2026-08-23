#!/usr/bin/env bash
# fresh-install.sh — Server auf einen sauberen Zustand bringen und weblab NEU installieren.
#
# ACHTUNG: Dieser Schritt ist für einen Neuaufbau von Grund auf gedacht und ENTFERNT:
#   - konkurrierende Panel-/Webserver-Software (Cockpit, Apache, Nginx, Webmin …),
#   - ALLE Docker-Container und -Volumes,
#   - eine frühere weblab-Installation samt Daten (/opt/weblab, /var/lib/weblab).
# Danach läuft die reguläre Installation (run.sh) und der Setup-Assistent im Browser
# legt Admin-Konto + Domain an.
#
# Interaktiv wird vor dem Löschen mit „JA" bestätigt. Für einen automatischen Lauf
# (z. B. per SSH-Einzeiler) FORCE=1 setzen oder --yes übergeben.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[ "$(id -u)" -eq 0 ] || { echo "Bitte als root ausführen (sudo)."; exit 1; }
export DEBIAN_FRONTEND=noninteractive

FORCE="${FORCE:-0}"
[ "${1:-}" = "--yes" ] && FORCE=1

echo "=================================================================="
echo "  weblab — Neuinstallation von Grund auf"
echo "  Entfernt vorhandene Panel-/Webserver-Software, alle Docker-"
echo "  Container/Volumes und frühere weblab-Daten auf diesem Server."
echo "=================================================================="

# 1) Erkennen, was bereits vorhanden ist ------------------------------------
echo "== Vorhandene Software erkennen =="
detected=()
for svc in cockpit.socket cockpit apache2 nginx caddy webmin \
           mysql mariadb postfix dovecot named bind9 lshttpd lscpd; do
  if systemctl is-active --quiet "$svc" 2>/dev/null \
     || systemctl list-unit-files 2>/dev/null | grep -q "^${svc}\."; then
    detected+=("$svc")
  fi
done
for panel in /usr/local/cpanel /usr/local/psa /usr/local/CyberCP \
             /usr/local/lsws /usr/local/ispconfig /usr/share/webmin; do
  [ -e "$panel" ] && detected+=("$(basename "$panel")")
done
[ -e /opt/weblab ] && detected+=("weblab (bestehend)")
if [ "${#detected[@]}" -gt 0 ]; then
  echo "   Gefunden: ${detected[*]}"
else
  echo "   Keine bekannte Fremd-Software gefunden."
fi

# 2) Bestätigung ------------------------------------------------------------
if [ "$FORCE" != "1" ]; then
  echo
  read -r -p 'Alles bereinigen und weblab frisch installieren? Tippe JA: ' answer
  [ "$answer" = "JA" ] || { echo "Abgebrochen — nichts verändert."; exit 1; }
fi

# 3) Konkurrierende Dienste stoppen -----------------------------------------
echo "== Dienste stoppen =="
for svc in cockpit.socket cockpit apache2 nginx caddy webmin weblab; do
  systemctl disable --now "$svc" >/dev/null 2>&1 || true
done

# 4) Docker-Container und -Volumes entfernen --------------------------------
if command -v docker >/dev/null 2>&1 && systemctl is-active --quiet docker; then
  echo "== Docker-Container und -Volumes entfernen =="
  ids="$(docker ps -aq || true)"
  [ -n "$ids" ] && docker rm -f $ids >/dev/null 2>&1 || true
  vols="$(docker volume ls -q || true)"
  [ -n "$vols" ] && docker volume rm $vols >/dev/null 2>&1 || true
fi

# 5) Ports 80/443/8099 freimachen -------------------------------------------
echo "== Ports 80/443/8099 freimachen =="
if command -v fuser >/dev/null 2>&1; then
  for port in 80 443 8099; do fuser -k "${port}/tcp" >/dev/null 2>&1 || true; done
fi

# 6) Frühere weblab-Installation entfernen ----------------------------------
echo "== Frühere weblab-Daten entfernen =="
rm -rf /opt/weblab /var/lib/weblab
rm -f /etc/systemd/system/weblab.service /etc/caddy/Caddyfile
systemctl daemon-reload >/dev/null 2>&1 || true

# 7) Bekannte Fremd-Webserver/Panels deinstallieren -------------------------
echo "== Fremd-Webserver/Panels deinstallieren =="
apt-get remove -y --purge apache2 'apache2-*' nginx 'nginx-*' \
        cockpit 'cockpit-*' webmin >/dev/null 2>&1 || true
apt-get autoremove -y >/dev/null 2>&1 || true

# 8) Frische Installation ----------------------------------------------------
echo "== Server ist bereinigt — starte frische Installation =="
bash "$HERE/run.sh"
