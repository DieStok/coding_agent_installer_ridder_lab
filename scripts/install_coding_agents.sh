#!/usr/bin/env bash
# install_coding_agents.sh — bootstrap the coding-agents installer for a new
# HPC user. This is the entry-point script the lab admin distributes.
#
# DEPLOYMENT (lab admin, one-time):
#     cp scripts/install_coding_agents.sh /hpc/compgen/users/shared/agent/bin/
#     chmod +x /hpc/compgen/users/shared/agent/bin/install_coding_agents.sh
#
# USE (each user, one-time):
#     bash /hpc/compgen/users/shared/agent/bin/install_coding_agents.sh
#     # then follow the printed "Next steps".
#
# Override the clone target (defaults to the project area, NOT $HOME, to avoid
# eating into the small home-dir quota; matches the lab pattern of putting
# software in /hpc/compgen/users/$USER/Software/):
#     TARGET=$HOME/coding_agents \
#       bash /hpc/compgen/users/shared/agent/bin/install_coding_agents.sh
#
# Per-user footprint after running everything:
#   - This bootstrap (repo + .venv): ~23 MB total. Lives at $TARGET.
#   - `coding-agents install` (TUI, separate step): adds ~200-300 MB
#     (codex/opencode/pi npm installs) at the install_dir the user picks.
#   - SIF: lives at /hpc/compgen/users/shared/agent/current.sif (lab-shared,
#     not duplicated per user).
#
# What it does (each step bails cleanly on failure):
#   1. Verifies `uv` is on PATH (prints install command if not).
#   2. Clones (or fast-forward-pulls) the repo into $TARGET.
#   3. Runs scripts/hpc_prereq_check.sh — bails if a hard prereq is missing.
#   4. Creates a uv venv at .venv/ with Python 3.12 (asks uv to fetch one if
#      python3.12 isn't on PATH).
#   5. Installs the `coding-agents` CLI into the venv via `uv pip install -e .`.
#   6. Prints the next-step instructions for activating + running the TUI.

set -euo pipefail

REPO_URL="https://github.com/DieStok/coding_agent_installer_ridder_lab.git"
# Default to the project area (matches the lab's /hpc/compgen/users/$USER/Software/
# pattern) instead of $HOME to avoid HPC home-dir quota pressure. Override with
# TARGET=$HOME/coding_agents bash install_coding_agents.sh
TARGET="${TARGET:-/hpc/compgen/users/$USER/Software/coding_agents_installer}"
PKG_SUBDIR="coding-agents-package"

# --- Colors only on a real terminal ---
if [ -t 1 ]; then
    BOLD='\033[1m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; RESET='\033[0m'
else
    BOLD=''; GREEN=''; YELLOW=''; RED=''; RESET=''
fi

banner() {
    echo
    echo -e "${BOLD}=================================================================${RESET}"
    echo -e "${BOLD} coding-agents bootstrap${RESET}"
    echo -e "${BOLD} (de Ridder lab — sandboxed Claude Code / Codex / OpenCode / Pi)${RESET}"
    echo -e "${BOLD}=================================================================${RESET}"
}
step()  { echo; echo -e "${BOLD}==> $1${RESET}"; }
ok()    { echo -e "${GREEN}✓${RESET} $1"; }
warn()  { echo -e "${YELLOW}WARN:${RESET} $1"; }
fatal() { echo -e "${RED}ERROR:${RESET} $1" >&2; exit 1; }

banner
echo "Target install dir: $TARGET"
echo "(Override with: TARGET=/some/other/path bash install_coding_agents.sh)"

# --- 0. Sanity-check the target parent ---
TARGET_PARENT=$(dirname "$TARGET")
if [ ! -d "$TARGET_PARENT" ]; then
    echo
    warn "Parent dir $TARGET_PARENT doesn't exist yet."
    echo "  Creating it..."
    mkdir -p "$TARGET_PARENT" || fatal "could not create $TARGET_PARENT — pick a writable TARGET= override."
fi
if [ ! -w "$TARGET_PARENT" ]; then
    fatal "Parent dir $TARGET_PARENT is not writable. Pick a writable location with TARGET=/some/other/path."
fi

# --- 1. uv on PATH ---
step "Checking uv availability"
if ! command -v uv >/dev/null 2>&1; then
    echo
    echo "  uv is required (fast Python package manager + interpreter fetch)."
    echo "  Install it once with:"
    echo "      curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "  Then re-run this script."
    exit 1
fi
ok "uv is on PATH ($(uv --version))"

# --- 2. Clone or pull ---
step "Fetching repo"
if [ -d "$TARGET/.git" ]; then
    echo "Found existing checkout at $TARGET — pulling latest from main..."
    git -C "$TARGET" pull --ff-only origin main \
        || fatal "git pull --ff-only failed at $TARGET (uncommitted local changes?). Resolve manually with: cd $TARGET && git status"
    ok "pulled latest"
else
    echo "Cloning $REPO_URL → $TARGET..."
    git clone --depth 1 "$REPO_URL" "$TARGET"
    ok "cloned"
fi

PKG="$TARGET/$PKG_SUBDIR"
[ -d "$PKG" ] || fatal "expected $PKG to exist after clone (repo layout changed?)"
cd "$PKG"

# --- 3. Prereq check ---
step "Running HPC prereq check (scripts/hpc_prereq_check.sh)"
if ! bash scripts/hpc_prereq_check.sh; then
    echo
    fatal "hpc_prereq_check.sh reported missing prerequisites — install the items above and re-run."
fi
ok "prereq check passed"

# --- 4. uv venv ---
step "Setting up uv venv (.venv) with Python 3.12"
if [ -d .venv ]; then
    ok "found existing .venv — leaving it alone"
else
    if ! command -v python3.12 >/dev/null 2>&1; then
        warn "python3.12 not on PATH — asking uv to fetch a managed interpreter..."
        uv python install 3.12
    fi
    uv venv .venv --python python3.12
    ok "created .venv"
fi

# --- 5. Install the CLI ---
step "Installing the coding-agents CLI (editable)"
# shellcheck source=/dev/null
source .venv/bin/activate
uv pip install -e . 2>&1 | tail -3
ok "coding-agents installed: $(coding-agents --version 2>&1 || echo '<version cmd unavailable>')"

# --- 6. Next-step block ---
echo
echo -e "${BOLD}=================================================================${RESET}"
echo -e "${GREEN}✅ Bootstrap complete.${RESET}"
echo
echo -e "${BOLD}Next steps (on this submit node):${RESET}"
echo "    source $PKG/.venv/bin/activate"
echo "    coding-agents install        # interactive TUI; wires wrappers, secrets/, settings"
echo "    coding-agents doctor         # verify"
echo
echo -e "${BOLD}Optional safe self-test before touching your real Claude install:${RESET}"
echo "    coding-agents --dry-run install --exclude claude"
echo
echo -e "${BOLD}Smoke-test on a compute node (after install + claude login):${RESET}"
echo "    srun --account=compgen --time=00:30:00 --mem=2G --gres=tmpspace:2G \\"
echo "         --cpus-per-task=1 \\"
echo "         --export=PATH,VIRTUAL_ENV,CONDA_PREFIX,CONDA_DEFAULT_ENV,LD_LIBRARY_PATH,HOME,USER,TERM,LANG,LC_ALL \\"
echo "         --pty bash"
echo "    agent-claude --version"
echo
echo -e "${BOLD}Update later (no re-clone):${RESET}"
echo "    cd $PKG && git pull && source .venv/bin/activate && uv pip install -e ."
echo
echo -e "${BOLD}=================================================================${RESET}"
