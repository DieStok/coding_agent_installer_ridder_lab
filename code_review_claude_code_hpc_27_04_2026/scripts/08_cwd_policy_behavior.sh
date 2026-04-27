#!/usr/bin/env bash
# 08 — Cwd-policy behavior matrix. Verify the wrapper bash check fires
# correctly for refusal / warn / OK cwds, and is silent on
# `coding-agents` Python CLI commands (per the 7b523b0 fix).
set -u

start_dir=$PWD
trap "cd '$start_dir'" EXIT

echo "[08] Refusal: cwd /hpc/compgen/users/shared (should exit 12)"
echo "----------------------------------------------------------------"
( cd /hpc/compgen/users/shared 2>/dev/null && \
  agent-claude --help 2>&1 | head -5; \
  echo "[08] exit=$?" ) || echo "[08] cd refused — skipping"
echo

echo "[08] Refusal: cwd /hpc/compgen/projects bare root (should exit 12)"
echo "----------------------------------------------------------------"
( cd /hpc/compgen/projects 2>/dev/null && \
  agent-claude --help 2>&1 | head -5; \
  echo "[08] exit=$?" ) || echo "[08] cd refused — skipping"
echo

echo "[08] Warn: cwd has no \$USER component (should exit 0 with yellow line)"
echo "----------------------------------------------------------------"
warn_dir=/hpc/compgen/projects/lab_ai_automation/coding_agent_installer
( cd "$warn_dir" 2>/dev/null && \
  agent-claude --version 2>&1 | head -5; \
  echo "[08] exit=$?" ) || echo "[08] $warn_dir not accessible — skipping"
echo

echo "[08] OK: analysis subdir under \$USER (should exit 0, no warn)"
echo "----------------------------------------------------------------"
ok_dir=$(find /hpc/compgen/projects -maxdepth 4 \
              -path "*/analysis/$USER" -type d 2>/dev/null | head -1)
if [ -n "$ok_dir" ]; then
  ( cd "$ok_dir" && agent-claude --version 2>&1 | head -5; \
    echo "[08] exit=$?" )
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
