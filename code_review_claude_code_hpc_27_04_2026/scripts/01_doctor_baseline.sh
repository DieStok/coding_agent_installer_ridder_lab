#!/usr/bin/env bash
# 01 — coding-agents doctor baseline.
# Read-only. Just runs `coding-agents doctor` and prints the table.
set -u
echo "[01] coding-agents doctor — full table"
echo "----------------------------------------------------------------"
coding-agents doctor || echo "[doctor exited non-zero: $?]"
echo
echo "[01] coding-agents doctor --scan-cron --scan-systemd"
echo "----------------------------------------------------------------"
coding-agents doctor --scan-cron --scan-systemd 2>&1 \
  || echo "[doctor scans exited non-zero: $?]"
