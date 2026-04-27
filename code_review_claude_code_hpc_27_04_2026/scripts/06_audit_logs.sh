#!/usr/bin/env bash
# 06 — Audit logs. The wrapper appends a JSONL line per agent invocation
# under ~/agent-logs/<agent>-YYYY-MM-DD.jsonl via `flock` + `jq -n`.
set -u

DIR=$HOME/agent-logs
if [ ! -d "$DIR" ]; then
  echo "[06] $DIR does not exist."
  echo "[06] If you ran any agent today, the wrapper should have created it."
  exit 0
fi

echo "[06] $DIR — directory listing"
echo "----------------------------------------------------------------"
ls -la "$DIR"
echo

echo "[06] Per-agent today's log tail (last 3 entries)"
echo "----------------------------------------------------------------"
for a in claude codex opencode pi; do
  F="$DIR/${a}-$(date -I).jsonl"
  if [ -f "$F" ]; then
    echo "--- $F ---"
    tail -3 "$F"
    echo "  (line count: $(wc -l <"$F"))"
  else
    echo "--- $F: not present ---"
  fi
done
echo

echo "[06] Validate JSONL: each line should parse as JSON"
echo "----------------------------------------------------------------"
for F in "$DIR"/*-$(date -I).jsonl; do
  [ -f "$F" ] || continue
  if command -v jq >/dev/null 2>&1; then
    bad=$(awk 'NF' "$F" | jq -e . >/dev/null 2>&1; echo $?)
    if [ "$bad" = "0" ]; then
      echo "  $F: all lines parse OK"
    else
      echo "  $F: AT LEAST ONE LINE FAILED TO PARSE"
      awk 'NF' "$F" | while IFS= read -r line; do
        echo "$line" | jq -e . >/dev/null 2>&1 || echo "    BAD: $line"
      done
    fi
  else
    echo "  $F: jq not on PATH; skipping JSON validation"
  fi
done
