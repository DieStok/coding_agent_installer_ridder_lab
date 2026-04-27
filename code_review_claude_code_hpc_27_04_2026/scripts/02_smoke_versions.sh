#!/usr/bin/env bash
# 02 — Per-agent --version smoke. For each of the four wrapped agents,
# run --version, capture stderr+stdout, and check whether apptainer was
# actually invoked (via audit log entry, since --version exits too fast
# for `ps` to catch).
set -u

AGENTS=(claude codex opencode pi)

for a in "${AGENTS[@]}"; do
  echo
  echo "[02] agent-$a --version"
  echo "----------------------------------------------------------------"
  log_before=$(wc -l "$HOME/agent-logs/${a}-$(date -I).jsonl" 2>/dev/null \
                | awk '{print $1}')
  log_before=${log_before:-0}

  agent-$a --version 2>&1 || echo "[agent-$a --version exited $?]"
  echo

  log_after=$(wc -l "$HOME/agent-logs/${a}-$(date -I).jsonl" 2>/dev/null \
               | awk '{print $1}')
  log_after=${log_after:-0}
  delta=$((log_after - log_before))
  echo "[02] audit-log lines added by this run: $delta"
  if [ "$delta" -gt 0 ]; then
    echo "[02] last audit log entry:"
    tail -1 "$HOME/agent-logs/${a}-$(date -I).jsonl" 2>/dev/null
  fi
done
