#!/usr/bin/env bash
# 10 — Host node / npm dependency check. After commit 9b87b0b, host npm
# install for biome is gated to --local mode; HPC mode picks biome up
# from the SIF. After the broader no-wrap-via-sif refactor, the only
# remaining hard host requirements for HPC mode are:
#   - claude (curl-installed; symlinked into <install_dir>/bin/claude)
#   - ccstatusline (npm-installed for Claude statusbar; SIF has fallback)
set -u

INSTALL_DIR=${CODING_AGENT_INSTALL_DIR:-/hpc/compgen/users/$USER/coding_agents}
[ -d "$INSTALL_DIR" ] || INSTALL_DIR=$HOME/coding_agents

echo "[10] Host node/npm presence"
echo "----------------------------------------------------------------"
which node && node --version 2>&1 || echo "  no host node"
which npm && npm --version 2>&1 || echo "  no host npm"
echo

echo "[10] Host biome — should NOT be present in HPC mode (post-9b87b0b)"
echo "----------------------------------------------------------------"
if [ -f "$INSTALL_DIR/tools/node_modules/.bin/biome" ]; then
  ls -la "$INSTALL_DIR/tools/node_modules/.bin/biome"
  echo "[10] PRESENT — either install pre-dates 9b87b0b, or installer ran in --local mode."
else
  echo "[10] absent — correct for HPC mode (biome lives in the SIF)."
fi
echo

echo "[10] SIF biome on PATH (post-9b87b0b verification)"
echo "----------------------------------------------------------------"
SIF=${SIF:-/hpc/compgen/users/shared/agent/current.sif}
apptainer exec --containall --no-mount home --writable-tmpfs "$SIF" \
  biome --version 2>&1 | head -3 \
  || echo "[10] biome NOT in SIF — SIF needs rebuild for 9b87b0b"
echo

echo "[10] Claude binary symlink"
echo "----------------------------------------------------------------"
if [ -L "$INSTALL_DIR/bin/claude" ]; then
  echo "  $INSTALL_DIR/bin/claude → $(readlink -f "$INSTALL_DIR/bin/claude")"
elif [ -f "$INSTALL_DIR/bin/claude" ]; then
  echo "  $INSTALL_DIR/bin/claude is a regular file (not the expected symlink)"
else
  echo "  $INSTALL_DIR/bin/claude not present"
fi
echo

echo "[10] ccstatusline location"
echo "----------------------------------------------------------------"
which ccstatusline 2>/dev/null \
  && echo "  found via PATH" \
  || echo "  not on PATH (expected — usually called from Claude statusline config)"
[ -f "$INSTALL_DIR/node_modules/.bin/ccstatusline" ] \
  && echo "  $INSTALL_DIR/node_modules/.bin/ccstatusline (host npm install)"
apptainer exec --containall --no-mount home --writable-tmpfs "$SIF" \
  ccstatusline --version 2>&1 | head -1 \
  && echo "  SIF copy works" \
  || echo "  SIF ccstatusline broken/absent"
