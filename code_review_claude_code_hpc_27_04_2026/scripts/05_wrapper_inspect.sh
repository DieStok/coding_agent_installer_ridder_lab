#!/usr/bin/env bash
# 05 — Wrapper template inspection. Confirm the deployed wrapper carries
# the post-2026-04-27 fixes, not stale code from before today.
set -u

INSTALL_DIR=${CODING_AGENT_INSTALL_DIR:-/hpc/compgen/users/$USER/coding_agents}
if [ ! -d "$INSTALL_DIR" ]; then
  INSTALL_DIR=$HOME/coding_agents
fi
echo "[05] Inspecting wrappers under: $INSTALL_DIR/bin/"
echo

for a in claude codex opencode pi; do
  W="$INSTALL_DIR/bin/agent-$a"
  if [ ! -x "$W" ]; then
    echo "[05] $W: NOT FOUND or NOT EXECUTABLE"
    continue
  fi
  echo "[05] === $W ==="
  echo "  size: $(wc -c <"$W") bytes"
  echo "  mtime: $(stat -c %y "$W" 2>/dev/null || stat -f %Sm "$W" 2>/dev/null)"
  echo "  apptainer flags:"
  grep -E '\-\-(no-mount|env|writable-tmpfs|no-privs|bind|home|pwd)' "$W" \
    | sed 's/^/    /' \
    | head -25
  echo "  APPTAINERENV_HOME exports (should be 0):"
  grep -c '^[^#]*export APPTAINERENV_HOME=' "$W" \
    | sed 's/^/    count=/'
  echo "  --no-mount home,tmp present (should be 0; superseded by 215ca9c):"
  grep -c -- '--no-mount home,tmp' "$W" \
    | sed 's/^/    count=/'
  echo "  --no-mount home only (should be 1):"
  grep -cE -- '--no-mount home([[:space:]]|\\)' "$W" \
    | sed 's/^/    count=/'
  echo "  cosmetic-warning filter (CODING_AGENTS_VERBOSE) — should be 1:"
  grep -c 'CODING_AGENTS_VERBOSE' "$W" \
    | sed 's/^/    count=/'
  echo "  _under_pwd helper (commit 8aed05f):"
  grep -c '_under_pwd()' "$W" \
    | sed 's/^/    count=/'
  echo
done

echo "[05] Path-shim symlink (expected: bin/path-shim/opencode → ../agent-opencode-vscode)"
ls -la "$INSTALL_DIR/bin/path-shim/" 2>&1 \
  | head -5
