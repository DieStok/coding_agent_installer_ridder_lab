#!/usr/bin/env bash
# hpc_prereq_check.sh — audit coding-agents prerequisites on a host.
#
# Intended for the UMC Utrecht HPC cluster (run on a submit node such as
# hpcs05 or hpcs06), but works anywhere. Prints a structured report, then
# a checklist of must-have prerequisites with copy-paste install commands
# for anything missing. Nothing is installed or modified by this script.
#
# Usage:
#   bash hpc_prereq_check.sh                   # print report
#   bash hpc_prereq_check.sh -o report.txt     # also write to file
#
# Exit codes:
#   0  all must-have prerequisites present
#   1  at least one must-have is missing (see checklist at the bottom)
#   2  bad arguments

set -u
set -o pipefail

out_file=""
while [ $# -gt 0 ]; do
    case "$1" in
        -o|--output)  out_file="$2"; shift 2 ;;
        -h|--help)    sed -n '2,16p' "$0"; exit 0 ;;
        *)            echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

# have <cmd>  → sets HAVE_PATH + HAVE_VERSION if cmd is on PATH, else unsets.
have() {
    unset HAVE_PATH HAVE_VERSION
    HAVE_PATH=$(command -v "$1" 2>/dev/null) || return 1
    HAVE_VERSION=$("$1" --version 2>&1 | head -1 | tr -d '\r')
    return 0
}

# Check whether `python3` (or python3.N where N>=12) reports >= 3.12. We test
# the coding-agents `requires-python = ">=3.12"` constraint, not a specific
# interpreter name. Echoes the (path,version) pair that satisfies on stdout
# if found.
find_python_ge_312() {
    local candidate v major minor
    for candidate in python3.13 python3.12 python3; do
        if command -v "$candidate" &>/dev/null; then
            v=$("$candidate" -c 'import sys; print("%d.%d"%sys.version_info[:2])' 2>/dev/null) || continue
            major=${v%%.*}; minor=${v##*.}
            if [ "$major" -ge 3 ] && [ "$minor" -ge 12 ]; then
                printf "%s\t%s\n" "$(command -v "$candidate")" "$v"
                return 0
            fi
        fi
    done
    return 1
}

# ----------------------------------------------------------------------------
# Report body
# ----------------------------------------------------------------------------

report() {
    echo "=== coding-agents prereq check ==="
    echo "host : $(hostname)"
    echo "date : $(date -u +%FT%TZ)"
    echo "user : $(whoami)   shell: ${SHELL:-?}"
    echo "home : $HOME  (write-ok: $(test -w "$HOME" && echo yes || echo no))"
    gdir="/hpc/compgen/users/$(whoami)"
    echo "group: $gdir (exists: $(test -d "$gdir" && echo yes || echo no))"
    command -v uname &>/dev/null && echo "kernel: $(uname -srm)"
    echo

    echo "=== tools on PATH ==="
    for cmd in git bash zsh curl jq python3 python3.11 python3.12 python3.13 \
               uv node npm yarn pnpm unzip tar; do
        if have "$cmd"; then
            printf "  %-12s FOUND    %-42s  (%s)\n" "$cmd" "$HAVE_PATH" "$HAVE_VERSION"
        else
            printf "  %-12s MISSING\n" "$cmd"
        fi
    done
    echo

    # Evaluate the Python >= 3.12 constraint explicitly.
    echo "=== Python >= 3.12 check (coding-agents requires this) ==="
    if py_line=$(find_python_ge_312); then
        echo "  OK       $py_line"
    else
        echo "  NOT FOUND — no python3 interpreter on PATH is >= 3.12"
    fi
    echo

    echo "=== agent binaries already on PATH (informational) ==="
    for c in claude codex opencode pi gemini amp; do
        if have "$c"; then
            printf "  %-10s %s\n" "$c" "$HAVE_PATH"
        else
            printf "  %-10s (not on PATH)\n" "$c"
        fi
    done
    echo

    echo "=== Lmod modules available for the prereqs ==="
    if command -v module &>/dev/null; then
        for name in python Python python3 node nodejs Node npm uv git curl Java; do
            hits=$(module -t avail "$name" 2>&1 \
                     | grep -Ei "^${name}([/-]|$)" \
                     | head -5)
            if [ -n "$hits" ]; then
                echo "  [$name]"
                echo "$hits" | sed 's/^/    /'
            fi
        done
        echo "  (currently loaded modules, for reference:)"
        module -t list 2>&1 | sed 's/^/    /'
    else
        echo "  module command not available"
    fi
    echo

    echo "=== network reachability (installer hits these URLs) ==="
    for url in https://claude.ai/install.sh \
               https://registry.npmjs.org/ \
               https://astral.sh/uv/install.sh \
               https://github.com \
               https://entire.io/install.sh; do
        if command -v curl &>/dev/null; then
            if curl -fsS --max-time 5 -o /dev/null "$url"; then
                echo "  OK    $url"
            else
                echo "  FAIL  $url"
            fi
        else
            echo "  SKIP  $url (curl missing)"
        fi
    done
    echo

    echo "=== HPC shared skill readable? ==="
    skill=/hpc/compgen/projects/ollama/hpc_skill/analysis/dstoker/hpc-cluster.skill
    if [ -r "$skill" ]; then
        ls -l "$skill"
    else
        echo "  not readable from $(hostname) — expected until the .skill is uploaded"
    fi
    echo

    # ------------------------------------------------------------------------
    # Must-have checklist. This is what users actually care about. Exit code
    # is derived here.
    # ------------------------------------------------------------------------
    echo "=== must-have checklist ==="
    echo "  (exit code reflects these — fix anything marked MISSING before installing coding-agents)"
    echo

    missing=()
    fixes=()

    check() {
        local name="$1" fix="$2"
        if have "$name"; then
            printf "  [ok]   %-8s  %s\n" "$name" "$HAVE_VERSION"
        else
            printf "  [FAIL] %-8s  %s\n" "$name" "missing"
            missing+=("$name")
            fixes+=("$fix")
        fi
    }

    check git   "Should be preinstalled on any UMC HPC submit node. If truly missing, email hpcsupport@umcutrecht.nl."
    check curl  "Should be preinstalled on any UMC HPC submit node. If truly missing, email hpcsupport@umcutrecht.nl."
    check bash  "You already have a shell — this check should never fail."
    check unzip "Should be preinstalled. If missing: 'conda install -n base unzip' into a personal conda env, or email hpcsupport@umcutrecht.nl."
    check tar   "Should be preinstalled. If missing, email hpcsupport@umcutrecht.nl."
    check node  "On hpcs05/hpcs06, Node.js is in /usr/bin. If it disappeared, reinstall in userspace: 'curl -o- https://fnm.vercel.app/install.sh | bash && source ~/.bashrc && fnm install 20'."
    check npm   "Ships with Node.js — if 'node' is fine but 'npm' is gone, reinstall Node.js via fnm (see 'node' row)."
    check uv    "Install into your home directory (no sudo needed): 'curl -LsSf https://astral.sh/uv/install.sh | sh && source ~/.bashrc' (installs to ~/.local/bin)."

    # Python is the one check that isn't just a "command on PATH" — it has
    # to be a version constraint.
    printf "  "
    if py_line=$(find_python_ge_312); then
        printf "[ok]   python3    %s\n" "$(echo "$py_line" | cut -f2)"
    else
        printf "[FAIL] python3    need >= 3.12 on PATH\n"
        missing+=("python3.12")
        fixes+=("Easiest: install uv first (above), then run 'uv python install 3.12'. Alternative: 'conda create -n py312 python=3.12 && conda activate py312'.")
    fi
    echo

    if [ ${#missing[@]} -eq 0 ]; then
        echo "  ✓ All must-haves present. You can run: uv tool install ."
        echo "    (from inside the cloned coding_agent_installer_ridder_lab directory)"
        rc=0
    else
        echo "  ✗ ${#missing[@]} prerequisite(s) missing:"
        echo
        for i in "${!missing[@]}"; do
            printf "    [%s]\n      %s\n" "${missing[$i]}" "${fixes[$i]}"
        done
        echo
        echo "  After fixing, open a fresh shell (or 'source ~/.bashrc') and re-run this script."
        rc=1
    fi
    echo
    echo "=== $0 complete ==="
    return $rc
}

# ----------------------------------------------------------------------------
# Driver — capture the report, then replay with tee if -o was given
# ----------------------------------------------------------------------------

if [ -n "$out_file" ]; then
    : > "$out_file"
    report | tee "$out_file"
    rc=${PIPESTATUS[0]}
    echo "(report also written to $out_file)"
else
    report
    rc=$?
fi
exit "$rc"
