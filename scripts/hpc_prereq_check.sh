#!/usr/bin/env bash
# hpc_prereq_check.sh — audit coding-agents prerequisites on a host.
#
# Intended for the UMC Utrecht HPC cluster (run on a submit node such as
# hpcs05 or hpcs06), but works anywhere. Prints a structured report you can
# copy back to the maintainer so the README can be tailored for de Ridder
# lab HPC users.
#
# Usage:
#   bash hpc_prereq_check.sh              # human-readable report
#   bash hpc_prereq_check.sh -o out.txt   # also tee into out.txt
#
# Exits 0 on success. Nothing is installed or modified.

set -u

out_file=""
while [ $# -gt 0 ]; do
    case "$1" in
        -o|--output)  out_file="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,15p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

run() {
    if [ -n "$out_file" ]; then
        "$@" 2>&1 | tee -a "$out_file"
    else
        "$@" 2>&1
    fi
}

# Everything below is plain `echo`; group it inside a single function so we
# can redirect with tee without scattering redirections everywhere.
report() {
    echo "=== coding-agents prereq check ==="
    echo "host : $(hostname)"
    echo "date : $(date -u +%FT%TZ)"
    echo "user : $(whoami)   shell: ${SHELL:-?}"
    echo "home : $HOME  (write-ok: $(test -w "$HOME" && echo yes || echo no))"
    gdir="/hpc/compgen/users/$(whoami)"
    echo "group: $gdir (exists: $(test -d "$gdir" && echo yes || echo no))"
    if command -v uname &>/dev/null; then
        echo "kernel: $(uname -srm)"
    fi
    echo

    echo "=== tools on PATH ==="
    # Format:   name  FOUND/MISSING  path  (version)
    for cmd in git bash zsh curl jq python3 python3.11 python3.12 python3.13 \
               uv node npm yarn pnpm unzip tar; do
        if p=$(command -v "$cmd" 2>/dev/null); then
            v=$("$cmd" --version 2>&1 | head -1 | tr -d '\r')
            printf "  %-12s FOUND    %-42s  (%s)\n" "$cmd" "$p" "$v"
        else
            printf "  %-12s MISSING\n" "$cmd"
        fi
    done
    echo

    echo "=== agent binaries already on PATH (informational) ==="
    for c in claude codex opencode pi gemini amp; do
        if p=$(command -v "$c" 2>/dev/null); then
            printf "  %-10s %s\n" "$c" "$p"
        else
            printf "  %-10s (not on PATH)\n" "$c"
        fi
    done
    echo

    echo "=== Lmod modules available for the prereqs ==="
    if command -v module &>/dev/null; then
        # module writes to stderr; capture both.
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

    echo "=== network reachability (installer needs these) ==="
    # Claude Code binary, npm registry, uv installer, github clones.
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

    echo "=== $0 complete ==="
}

if [ -n "$out_file" ]; then
    : > "$out_file"
    report | tee "$out_file"
    echo "(report also written to $out_file)"
else
    report
fi
