#!/usr/bin/env bash
# 07 — OpenCode PATH-shim resolution. The shell-rc block prepends
# <install_dir>/bin/path-shim/ to PATH, where `opencode` is a symlink
# to `../agent-opencode-vscode`. That stub then `exec`s the
# Python helper (agent-vscode) to wrap the call. Verify resolution.
set -u

echo "[07] PATH dump (first 10 entries, : delimited)"
echo "----------------------------------------------------------------"
echo "$PATH" | tr ':' '\n' | head -10
echo

echo "[07] which opencode"
which opencode || echo "[07] opencode not on PATH — shell-rc not sourced?"

echo
echo "[07] readlink -f <which opencode>"
oc=$(which opencode 2>/dev/null)
if [ -n "$oc" ]; then
  readlink -f "$oc"
else
  echo "[07] skipped — opencode not on PATH"
fi

echo
echo "[07] Path-shim dir contents (expect single 'opencode' symlink)"
echo "----------------------------------------------------------------"
INSTALL_DIR=${CODING_AGENT_INSTALL_DIR:-/hpc/compgen/users/$USER/coding_agents}
[ -d "$INSTALL_DIR/bin/path-shim" ] || INSTALL_DIR=$HOME/coding_agents
ls -la "$INSTALL_DIR/bin/path-shim/" 2>&1
echo

echo "[07] First three lines of agent-opencode-vscode (must use readlink -f)"
echo "----------------------------------------------------------------"
head -3 "$INSTALL_DIR/bin/agent-opencode-vscode" 2>&1
