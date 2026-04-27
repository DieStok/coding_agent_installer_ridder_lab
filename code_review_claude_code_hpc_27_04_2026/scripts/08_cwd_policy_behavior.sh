#!/usr/bin/env bash
# 08 — Cwd-policy behavior matrix. Verify the wrapper bash check fires
# correctly for refusal / warn / OK cwds, and is silent on
# `coding-agents` Python CLI commands (per the 7b523b0 fix).
#
# Note on exit-code capture: piping through `head -5` overrides $?
# with head's exit code (always 0 once it has read 5 lines). We
# therefore run the agent first, capture $? immediately, THEN truncate
# the output for display.
set -u

start_dir=$PWD
trap "cd '$start_dir'" EXIT

# Run an agent in a given dir; print at most 5 lines of output and the
# agent's real exit code (NOT head's exit code).
_run_with_exit() {
  local dir="$1"; shift
  if ! cd "$dir" 2>/dev/null; then
    echo "[08] cd '$dir' failed — skipping"
    return
  fi
  local out
  out=$("$@" 2>&1)
  local rc=$?
  printf '%s\n' "$out" | head -5
  echo "[08] exit=$rc  (agent's real exit code, not head's)"
  cd "$start_dir"
}

echo "[08] Refusal: cwd /hpc/compgen/users/shared (should exit 12)"
echo "----------------------------------------------------------------"
_run_with_exit /hpc/compgen/users/shared agent-claude --help
echo

echo "[08] Refusal: cwd /hpc/compgen/projects bare root (should exit 12)"
echo "----------------------------------------------------------------"
_run_with_exit /hpc/compgen/projects agent-claude --help
echo

echo "[08] Warn: cwd has no \$USER component (should exit 0 with yellow line)"
echo "----------------------------------------------------------------"
warn_dir=/hpc/compgen/projects/lab_ai_automation/coding_agent_installer
_run_with_exit "$warn_dir" agent-claude --version
echo

echo "[08] OK: analysis subdir under \$USER (should exit 0, no warn)"
echo "----------------------------------------------------------------"
ok_dir=$(find /hpc/compgen/projects -maxdepth 4 \
              -path "*/analysis/$USER" -type d 2>/dev/null | head -1)
if [ -n "$ok_dir" ]; then
  _run_with_exit "$ok_dir" agent-claude --version
else
  echo "[08] No analysis/$USER dir found under /hpc/compgen/projects — skipping."
fi
echo

echo "[08] coding-agents doctor MUST NOT print cwd-policy warning"
echo "    (was a regression before 7b523b0)"
echo "----------------------------------------------------------------"
( cd "$warn_dir" 2>/dev/null && coding-agents doctor 2>&1 \
    | grep -i "cwd\|component\|Lab convention" | head -3 \
    || echo "[08] coding-agents doctor printed no cwd-policy lines (good)" )
