#!/usr/bin/env bash
# update.sh — weblab auf den neuesten Stand von main bringen.
# Wird vom Timer (weblab-update.timer) oder manuell aus den Einstellungen gestartet.
# Holt den aktuellen Stand aus dem öffentlichen Repo und installiert ihn bei Änderung neu.
set -euo pipefail
REPO_URL="${WEBLAB_REPO:-https://github.com/florianthepro/weblab}"
SRC="${WEBLAB_SRC:-/opt/weblab/src}"
STATE=/var/lib/weblab
STAMP="$STATE/last-update"
LOG="$STATE/update.log"
export GIT_TERMINAL_PROMPT=0
mkdir -p "$STATE"

log() { echo "$(date -u +%FT%TZ) $*" >>"$LOG"; }

command -v git >/dev/null 2>&1 || { log "git fehlt"; exit 0; }

if [ ! -d "$SRC/.git" ]; then
  rm -rf "$SRC"
  git clone --depth 1 "$REPO_URL" "$SRC" >>"$LOG" 2>&1 || { log "clone fehlgeschlagen"; exit 0; }
fi

if ! git -C "$SRC" fetch --depth 1 origin main >>"$LOG" 2>&1; then
  log "fetch fehlgeschlagen"
  date -u +%FT%TZ >"$STAMP"
  exit 0
fi

local_rev="$(git -C "$SRC" rev-parse HEAD 2>/dev/null || echo none)"
remote_rev="$(git -C "$SRC" rev-parse origin/main 2>/dev/null || echo none)"
date -u +%FT%TZ >"$STAMP"

if [ "$local_rev" = "$remote_rev" ] && [ "${1:-}" != "--force" ]; then
  log "aktuell ($local_rev)"
  exit 0
fi

git -C "$SRC" reset --hard origin/main >>"$LOG" 2>&1
log "aktualisiere ${local_rev:0:7} -> ${remote_rev:0:7}"
if bash "$SRC/software/install.sh" >>"$LOG" 2>&1; then
  log "fertig ($(git -C "$SRC" rev-parse --short HEAD 2>/dev/null))"
else
  log "install.sh fehlgeschlagen"
fi
