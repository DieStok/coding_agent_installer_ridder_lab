#!/usr/bin/env bash
# build_and_deploy_sif.sh — one-step SIF build + upload + atomic-swap.
#
# Builds coding_agent_hpc.sif via Docker+Apptainer, scp's it to the HPC
# share with a timestamped name, verifies sha256 round-trip, then
# atomic-swaps the canonical current.sif symlink.
#
# Usage:
#   bash scripts/build_and_deploy_sif.sh USER@HOST [OPTIONS]
#
# Required:
#   USER@HOST                 ssh target with passwordless key auth
#                             (e.g. dstoker@hpc_ext)
#
# Options:
#   --remote-share-dir PATH   default /hpc/compgen/users/shared/agent
#   --remote-name NAME        default coding_agent_hpc-<ts>.sif
#   --skip-build              reuse existing local coding_agent_hpc.sif
#   --no-swap                 upload + verify only; do NOT flip current.sif
#   -h, --help                this help
#
# Exit codes:
#   0  success
#   2  bad arguments
#   3  Docker not running / build prereqs missing
#   4  build failed
#   5  upload failed
#   6  sha256 mismatch (local != remote)
#   7  symlink swap failed
#
# Rollback after a swap:
#   ssh USER@HOST "
#     cd /hpc/compgen/users/shared/agent
#     ln -sfn <previous-sif-name> current.sif.rollback
#     mv -T current.sif.rollback current.sif
#     ln -sfn <previous-sif-name>.sha256 current.sif.sha256.rollback
#     mv -T current.sif.sha256.rollback current.sif.sha256
#   "
# The previous SIF is NOT deleted by this script — the only thing that
# changes during swap is the current.sif / current.sif.sha256 symlink
# pair.

set -euo pipefail

# ---------- arg parsing ----------

REMOTE=""
REMOTE_SHARE_DIR="/hpc/compgen/users/shared/agent"
REMOTE_NAME=""
SKIP_BUILD=0
NO_SWAP=0

while [ $# -gt 0 ]; do
    case "$1" in
        --remote-share-dir) REMOTE_SHARE_DIR="$2"; shift 2 ;;
        --remote-name)      REMOTE_NAME="$2"; shift 2 ;;
        --skip-build)       SKIP_BUILD=1; shift ;;
        --no-swap)          NO_SWAP=1; shift ;;
        -h|--help)          sed -n '2,42p' "$0"; exit 0 ;;
        -*)                 echo "unknown flag: $1" >&2; exit 2 ;;
        *)
            if [ -z "$REMOTE" ]; then
                REMOTE="$1"; shift
            else
                echo "unexpected positional arg: $1" >&2; exit 2
            fi ;;
    esac
done

if [ -z "$REMOTE" ]; then
    echo "usage: $0 USER@HOST [OPTIONS]" >&2
    echo "       $0 --help" >&2
    exit 2
fi

# Default the timestamped remote name once REMOTE is known.
if [ -z "$REMOTE_NAME" ]; then
    TS=$(date +%Y-%m-%d-%H%M)
    REMOTE_NAME="coding_agent_hpc-${TS}.sif"
fi

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
LOCAL_SIF="$REPO_ROOT/coding_agent_hpc.sif"
LOCAL_SHA="$REPO_ROOT/coding_agent_hpc.sif.sha256"

# ---------- step 1: build ----------

if [ "$SKIP_BUILD" -eq 0 ]; then
    if ! docker info >/dev/null 2>&1; then
        echo "ERROR: Docker is not running. Start Docker Desktop and retry." >&2
        exit 3
    fi
    echo "[1/4] Building SIF (Docker + Apptainer 1.4.5, ~5–15 min)..."
    docker pull --platform linux/amd64 \
        ghcr.io/apptainer/apptainer:1.4.5 >/dev/null
    docker run --rm --privileged --platform linux/amd64 \
        -v "$REPO_ROOT:/work" -w /work \
        ghcr.io/apptainer/apptainer:1.4.5 \
        apptainer build -F coding_agent_hpc.sif \
            src/coding_agents/bundled/coding_agent_hpc.def \
        || { echo "ERROR: apptainer build failed" >&2; exit 4; }
    echo "  built: $LOCAL_SIF ($(du -h "$LOCAL_SIF" | awk '{print $1}'))"
else
    if [ ! -f "$LOCAL_SIF" ]; then
        echo "ERROR: --skip-build requested but $LOCAL_SIF is missing." >&2
        exit 4
    fi
    echo "[1/4] Skipping build — reusing $LOCAL_SIF"
fi

# Always (re)compute sha256 — covers --skip-build with a stale sidecar.
echo "  computing sha256..."
shasum -a 256 "$LOCAL_SIF" | awk '{print $1}' > "$LOCAL_SHA"
LOCAL_HASH=$(cat "$LOCAL_SHA")
echo "  sha256: $LOCAL_HASH"

# ---------- step 2: upload ----------

echo "[2/4] Uploading to ${REMOTE}:${REMOTE_SHARE_DIR}/${REMOTE_NAME}..."
scp -B -q "$LOCAL_SIF" "${REMOTE}:${REMOTE_SHARE_DIR}/${REMOTE_NAME}" \
    || { echo "ERROR: scp of SIF failed" >&2; exit 5; }
scp -B -q "$LOCAL_SHA" "${REMOTE}:${REMOTE_SHARE_DIR}/${REMOTE_NAME}.sha256" \
    || { echo "ERROR: scp of sha256 sidecar failed" >&2; exit 5; }
echo "  upload complete."

# ---------- step 3: verify ----------

echo "[3/4] Verifying remote sha256..."
REMOTE_HASH=$(ssh -o BatchMode=yes "$REMOTE" \
    "sha256sum '${REMOTE_SHARE_DIR}/${REMOTE_NAME}' | awk '{print \$1}'")
if [ "$LOCAL_HASH" != "$REMOTE_HASH" ]; then
    echo "ERROR: sha256 mismatch!" >&2
    echo "  local : $LOCAL_HASH" >&2
    echo "  remote: $REMOTE_HASH" >&2
    echo "  remote SIF NOT swapped — investigate before retrying." >&2
    exit 6
fi
echo "  match: $REMOTE_HASH"

# ---------- step 4: atomic swap ----------

if [ "$NO_SWAP" -eq 1 ]; then
    echo "[4/4] --no-swap — leaving current.sif untouched."
    echo
    echo "Uploaded SIF: ${REMOTE_SHARE_DIR}/${REMOTE_NAME}"
    echo "To activate later:"
    echo "  ssh $REMOTE \\"
    echo "    \"cd $REMOTE_SHARE_DIR && \\"
    echo "     ln -sfn $REMOTE_NAME current.sif.new && \\"
    echo "     mv -T current.sif.new current.sif && \\"
    echo "     ln -sfn $REMOTE_NAME.sha256 current.sif.sha256.new && \\"
    echo "     mv -T current.sif.sha256.new current.sif.sha256\""
    exit 0
fi

echo "[4/4] Atomic-swapping current.sif on ${REMOTE}..."
PREV_SIF=$(ssh -o BatchMode=yes "$REMOTE" \
    "readlink '${REMOTE_SHARE_DIR}/current.sif' 2>/dev/null || echo '<none>'")
ssh -o BatchMode=yes "$REMOTE" "
    set -e
    cd '${REMOTE_SHARE_DIR}'
    ln -sfn '${REMOTE_NAME}' current.sif.new
    mv -T current.sif.new current.sif
    ln -sfn '${REMOTE_NAME}.sha256' current.sif.sha256.new
    mv -T current.sif.sha256.new current.sif.sha256
" || { echo "ERROR: swap failed" >&2; exit 7; }

# Confirm the swap landed.
NEW_TARGET=$(ssh -o BatchMode=yes "$REMOTE" \
    "readlink '${REMOTE_SHARE_DIR}/current.sif'")
echo "  current.sif -> $NEW_TARGET"

# ---------- summary ----------

echo
echo "============================================================"
echo "Deployed: ${REMOTE_SHARE_DIR}/${REMOTE_NAME}"
echo "Previous: ${PREV_SIF}  (preserved — not deleted)"
echo
echo "Verify on HPC:"
echo "  coding-agents doctor --probe-sif"
echo
echo "Rollback if needed:"
echo "  ssh $REMOTE \\"
echo "    \"cd $REMOTE_SHARE_DIR && \\"
echo "     ln -sfn $(basename "$PREV_SIF") current.sif.rollback && \\"
echo "     mv -T current.sif.rollback current.sif && \\"
echo "     ln -sfn $(basename "$PREV_SIF").sha256 current.sif.sha256.rollback && \\"
echo "     mv -T current.sif.sha256.rollback current.sif.sha256\""
echo "============================================================"
