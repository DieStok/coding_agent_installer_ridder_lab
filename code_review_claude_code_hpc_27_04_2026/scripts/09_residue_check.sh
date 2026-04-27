#!/usr/bin/env bash
# 09 — Stale runtime residue check. Files that earlier agent runs left
# behind. Some are cosmetic; some can re-trigger bugs.
set -u

echo "[09] /tmp/pi-*-uid-$(id -u)/ residue (should be empty after a clean run)"
echo "----------------------------------------------------------------"
ls -la /tmp/pi-*-uid-$(id -u)/ 2>/dev/null \
  || echo "[09] No /tmp/pi-*-uid-$(id -u)/ — clean."
echo

echo "[09] ~/.codex/tmp/arg0/ (Codex's per-invocation arg0 sandbox)"
echo "----------------------------------------------------------------"
ls -la "$HOME/.codex/tmp/arg0/" 2>/dev/null \
  || echo "[09] No ~/.codex/tmp/arg0/ — clean."
echo

echo "[09] vscode-session.json (should be present only when a sidebar is alive)"
echo "----------------------------------------------------------------"
SESSION_FILE=${XDG_RUNTIME_DIR:-$HOME/.coding-agents}/vscode-session.json
if [ -f "$SESSION_FILE" ]; then
  ls -la "$SESSION_FILE"
  if command -v jq >/dev/null 2>&1; then
    jq . "$SESSION_FILE"
  else
    cat "$SESSION_FILE"
  fi
  echo
  echo "[09] If the cached job_id is no longer in 'squeue -u $USER', this is stale —"
  echo "[09] run 'coding-agents vscode-reset' to clean."
  squeue -u "$USER" 2>/dev/null | head -5 \
    || echo "[09] squeue not available (login node)."
else
  echo "[09] No vscode-session.json — no cached SLURM allocation. (Normal.)"
fi
echo

echo "[09] .backup-*.tar.gz tarballs from prior coding-agents installs"
echo "----------------------------------------------------------------"
ls -la "$HOME"/.{claude,codex,opencode,pi}.backup-*.tar.gz 2>/dev/null \
  | tail -10 \
  || echo "[09] No agent .tar.gz backups found."
echo

echo "[09] Per-file .backup-DATE files in agent config dirs"
echo "----------------------------------------------------------------"
find "$HOME/.claude" "$HOME/.codex" "$HOME/.pi" "$HOME/.config/opencode" \
     -maxdepth 3 -name "*.backup-*" 2>/dev/null \
  | head -10 \
  || echo "[09] No per-file backups."
