#!/usr/bin/env bash
# 03 — Pi interactive extension load. Pi prints its [Extensions] block
# during startup; we drive it with `</dev/null` so it exits immediately
# after the banner, capturing the load result. If pi-subagents fails to
# load (the EPERM /tmp/pi-subagents-uid-<uid>/ regression), the Error
# line shows up here.
set -u

echo "[03] Current ~/.pi/agent/settings.json (if any):"
echo "----------------------------------------------------------------"
if [ -f "$HOME/.pi/agent/settings.json" ]; then
  cat "$HOME/.pi/agent/settings.json"
  echo
  if command -v jq >/dev/null 2>&1; then
    echo "[03] packages array (jq):"
    jq '.packages // .extensions // "—"' "$HOME/.pi/agent/settings.json"
  fi
else
  echo "[03] ~/.pi/agent/settings.json does not exist."
  echo "[03] First-run hook will copy /opt/pi-default-settings.json on"
  echo "[03] the first wrapped Pi message."
fi
echo

echo "[03] agent-pi (driven with </dev/null; capture banner only)"
echo "----------------------------------------------------------------"
# 5-second timeout: Pi prints its banner well within 5 seconds; if it
# hangs longer, something is wrong with subagent registration.
timeout 5 agent-pi </dev/null 2>&1 || rc=$?
echo "[03] agent-pi exit/timeout: ${rc:-0}"
echo

echo "[03] Stale tmp residue check"
echo "----------------------------------------------------------------"
ls -la /tmp/pi-*-uid-$(id -u)/ 2>/dev/null \
  || echo "[03] No /tmp/pi-*-uid-$(id -u)/ entries — clean."
