#!/usr/bin/env bash
# weblab — ein Befehl für alles: installieren, aktualisieren, neu aufsetzen.
#
#   sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/florianthepro/weblab/main/install.sh)"
#
# Das Skript sieht nach, was auf dem Server liegt:
#   • weblab vorhanden      -> fragt: Aktualisieren oder Neu installieren
#   • fremde Software da    -> bietet an, sie vorher zu entfernen
#   • sauberer Server       -> installiert direkt
#
# Aktualisieren vergleicht mit GitHub und ersetzt nur die weblab-Programmdateien.
# Eigene Daten (Apps, Webseiten, Datenbanken unter /var/lib/weblab) bleiben unberührt.
#
# Ohne Rückfragen: --update | --reinstall | --install, dazu --yes.
set -euo pipefail

REPO="${WEBLAB_REPO:-https://github.com/florianthepro/weblab}"
BRANCH="${WEBLAB_BRANCH:-main}"
TARGET="${WEBLAB_TARGET:-/opt/weblab}"
SRC="${WEBLAB_SRC:-$TARGET/src}"
DATA="${WEBLAB_DATA:-/var/lib/weblab}"
MODE="${WEBLAB_MODE:-}"
YES="${WEBLAB_YES:-0}"
DRY="${WEBLAB_DRY:-0}"
export DEBIAN_FRONTEND=noninteractive GIT_TERMINAL_PROMPT=0

for arg in "$@"; do
  case "$arg" in
    --update)    MODE=update ;;
    --refresh)   MODE=refresh ;;
    --wipe|--reinstall) MODE=reinstall ;;
    --install)   MODE=install ;;
    --yes|-y)    YES=1 ;;
    --dry-run)   DRY=1 ;;
  esac
done

[ "$(id -u)" -eq 0 ] || { echo "Bitte mit sudo ausführen."; exit 1; }

say() { printf '%s\n' "$*"; }
step() { printf '\n== %s ==\n' "$*"; }

# ---------------------------------------------------------------- erkennen ---
weblab_da() {
  [ -d "$TARGET/weblab" ] || [ -f "$DATA/weblab.db" ] \
    || systemctl list-unit-files 2>/dev/null | grep -q '^weblab\.service'
}

fremde_software() {
  local found=""
  for svc in cockpit.socket cockpit apache2 nginx webmin lshttpd; do
    systemctl list-unit-files 2>/dev/null | grep -q "^${svc}\." && found="$found $svc"
  done
  for panel in /usr/local/cpanel /usr/local/psa /usr/local/CyberCP /usr/local/lsws \
               /usr/local/ispconfig /usr/share/webmin; do
    [ -e "$panel" ] && found="$found $(basename "$panel")"
  done
  printf '%s' "${found# }"
}

frage() {          # frage "Text" "1" -> Auswahl auf stdout
  local prompt="$1" default="$2" answer=""
  if [ "$YES" = "1" ] || [ ! -t 0 ]; then printf '%s' "$default"; return; fi
  read -r -p "$prompt" answer || true
  printf '%s' "${answer:-$default}"
}

# ------------------------------------------------------------------ quellen ---
quellen_holen() {
  command -v git >/dev/null 2>&1 || { apt-get update -y >/dev/null; apt-get install -y git >/dev/null; }
  if [ -d "$SRC/.git" ]; then
    git -C "$SRC" fetch --depth 1 origin "$BRANCH" >/dev/null 2>&1 || true
  else
    rm -rf "$SRC"
    mkdir -p "$(dirname "$SRC")"
    git clone --depth 1 --branch "$BRANCH" "$REPO" "$SRC" >/dev/null 2>&1 \
      || { say "Quellen konnten nicht geladen werden."; exit 1; }
  fi
}

auf_stand_bringen() {          # 0 = es gab Änderungen
  local hier dort
  hier="$(git -C "$SRC" rev-parse HEAD 2>/dev/null || echo a)"
  dort="$(git -C "$SRC" rev-parse "origin/$BRANCH" 2>/dev/null || echo "$hier")"
  [ "$hier" = "$dort" ] && return 1
  git -C "$SRC" reset --hard "origin/$BRANCH" >/dev/null 2>&1
  return 0
}

kern_weicht_ab() {             # 0 = installierte Dateien != Repo
  local a b
  a="$SRC/software/weblab"; b="$TARGET/weblab"
  [ -d "$b" ] || return 0
  diff -rq --exclude=__pycache__ "$a" "$b" >/dev/null 2>&1 || return 0
  diff -rq "$SRC/connectors/keep" "$TARGET/connectors/keep" >/dev/null 2>&1 || return 0
  return 1
}

# ----------------------------------------------------------------- aktionen ---
kern_installieren() { bash "$SRC/software/install.sh"; }
haerten()           { bash "$SRC/software/bootstrap.sh"; }

aufraeumen() {
  step "Server bereinigen"
  for svc in cockpit.socket cockpit apache2 nginx caddy webmin weblab; do
    systemctl disable --now "$svc" >/dev/null 2>&1 || true
  done
  if command -v docker >/dev/null 2>&1 && systemctl is-active --quiet docker; then
    ids="$(docker ps -aq || true)";      [ -n "$ids" ]  && docker rm -f $ids >/dev/null 2>&1 || true
    vols="$(docker volume ls -q || true)"; [ -n "$vols" ] && docker volume rm $vols >/dev/null 2>&1 || true
  fi
  apt-get remove -y --purge apache2 'apache2-*' nginx 'nginx-*' cockpit 'cockpit-*' webmin \
    >/dev/null 2>&1 || true
  apt-get autoremove -y >/dev/null 2>&1 || true
}

weblab_entfernen() {
  step "Frühere weblab-Installation entfernen"
  systemctl disable --now weblab weblab-update.timer >/dev/null 2>&1 || true
  rm -rf "$TARGET/weblab" "$TARGET/connectors" "$TARGET/VERSION" "$DATA"
  rm -f /etc/systemd/system/weblab.service /etc/systemd/system/weblab-update.* \
        /etc/caddy/Caddyfile
  systemctl daemon-reload >/dev/null 2>&1 || true
}

fertig_hinweis() {
  ip="$(curl -s --max-time 8 https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')"
  say ""
  say "Fertig. Oberfläche: http://${ip}"
}

# --------------------------------------------------------------------- lauf ---
say "weblab"
quellen_holen

if [ -z "$MODE" ]; then
  if weblab_da; then
    # Keine Rückfragen: weblab wird frisch installiert, Apps und Daten bleiben.
    # Ein vollständiger Reset (alles löschen) nur ausdrücklich mit --wipe.
    MODE=refresh
  else
    gefunden="$(fremde_software)"
    if [ -n "$gefunden" ]; then
      say ""
      say "Gefunden: $gefunden"
      say "  1) Entfernen und weblab installieren"
      say "  2) Installieren, ohne etwas zu entfernen"
      say "  3) Abbrechen"
      case "$(frage 'Auswahl [1]: ' 1)" in
        2) MODE=install ;;
        3) say "Abgebrochen."; exit 0 ;;
        *) MODE=install; CLEAN=1 ;;
      esac
    else
      MODE=install
    fi
  fi
fi

if [ "$DRY" = "1" ]; then
  say "Trockenlauf: $MODE${CLEAN:+ (mit Bereinigung)}"
  exit 0
fi

case "$MODE" in
  update)
    step "Mit GitHub vergleichen"
    neu=0; auf_stand_bringen && neu=1
    if [ "$neu" = "1" ] || kern_weicht_ab; then
      say "Unterschiede gefunden — weblab wird aktualisiert."
      kern_installieren
      say "Aktualisiert auf $(git -C "$SRC" rev-parse --short HEAD 2>/dev/null)."
      say "Apps und Daten unter $DATA sind unverändert."
    else
      say "Bereits aktuell — nichts zu tun."
    fi
    ;;
  refresh)
    step "weblab neu installieren (Apps und Daten bleiben)"
    auf_stand_bringen || true
    systemctl stop weblab >/dev/null 2>&1 || true
    rm -rf "$TARGET/weblab" "$TARGET/connectors" "$TARGET/VERSION"
    kern_installieren
    say "Neu installiert auf $(git -C "$SRC" rev-parse --short HEAD 2>/dev/null)."
    say "Apps und Daten unter $DATA sind unverändert."
    fertig_hinweis
    ;;
  reinstall)
    if [ "$YES" != "1" ] && [ -t 0 ]; then
      antwort="$(frage 'Wirklich alles zurücksetzen? Apps und Daten gehen verloren. Tippe JA: ' '')"
      [ "$antwort" = "JA" ] || { say "Abgebrochen."; exit 0; }
    fi
    auf_stand_bringen || true
    aufraeumen
    weblab_entfernen
    haerten
    kern_installieren
    fertig_hinweis
    ;;
  install)
    [ "${CLEAN:-0}" = "1" ] && aufraeumen
    haerten
    kern_installieren
    fertig_hinweis
    ;;
esac
