#!/usr/bin/env bash
# diagnose_vscode_extensions.sh
#
# Capture everything we need to reverse-engineer how the four
# coding-agent VSCode extensions invoke their backing CLIs, what
# settings they expose, and what env vars they read at runtime.
#
# Run AFTER installing the extensions and ideally AFTER opening VSCode
# at least once (extension host activates and we can capture live procs).
#
# Output: a single timestamped text file in $PWD that the user can paste
# back so we can diagnose the wrapper-wiring story.
#
# Usage:
#   bash scripts/diagnose_vscode_extensions.sh
#
# No sudo needed. Read-only. Won't modify any extension or settings.
set -euo pipefail

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

OUT="vscode_extensions_diagnostic_$(date -u +%Y%m%d_%H%M%S).txt"
EXTENSIONS=(
  "anthropic.claude-code"
  "openai.chatgpt"
  "sst-dev.opencode"
  "pi0.pi-vscode"
)

# Common binary names the extensions might spawn. Used in process snapshot
# + JS-grep section.
BINARY_PATTERNS=(
  claude
  codex
  opencode
  "@mariozechner/pi-coding-agent"
  pi-coding-agent
  "node.*pi"
  "node.*claude"
  "node.*codex"
  "node.*opencode"
)

# Resolve VSCode install variants. Different installs land extensions
# in different roots — we hit all known ones.
VSCODE_EXT_ROOTS=(
  "$HOME/.vscode/extensions"            # stable
  "$HOME/.vscode-insiders/extensions"   # insiders
  "$HOME/.vscode-server/extensions"     # remote-ssh server
  "$HOME/.cursor/extensions"            # Cursor (VSCode fork)
  "$HOME/.windsurf/extensions"          # Windsurf
  "$HOME/.vscodium/extensions"          # VSCodium
)

# Settings file locations on macOS / Linux / Windows-WSL.
case "$OSTYPE" in
  darwin*)
    USER_SETTINGS_PATHS=(
      "$HOME/Library/Application Support/Code/User/settings.json"
      "$HOME/Library/Application Support/Code - Insiders/User/settings.json"
      "$HOME/Library/Application Support/Cursor/User/settings.json"
    )
    ;;
  linux*|*)
    USER_SETTINGS_PATHS=(
      "$HOME/.config/Code/User/settings.json"
      "$HOME/.config/Code - Insiders/User/settings.json"
      "$HOME/.config/Cursor/User/settings.json"
    )
    ;;
esac

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

section() {
  printf '\n\n========================================================================\n' >> "$OUT"
  printf '%s\n' "$1" >> "$OUT"
  printf '========================================================================\n\n' >> "$OUT"
}

subsection() {
  printf '\n--- %s ---\n\n' "$1" >> "$OUT"
}

note() {
  printf '%s\n' "$@" >> "$OUT"
}

# Find the most recent installed dir matching a publisher.name prefix.
# VSCode names extension dirs as <publisher>.<name>-<version>. We pick
# the one with the highest version (lex sort works for semver-prefixed
# dirs).
find_extension_dir() {
  local ext_id="$1"
  for root in "${VSCODE_EXT_ROOTS[@]}"; do
    [ -d "$root" ] || continue
    # Both .vscode and .vscode-server use the same naming; .cursor too.
    local match
    match=$(ls -1d "$root/${ext_id}"-* 2>/dev/null | sort -V | tail -1 || true)
    if [ -n "$match" ] && [ -d "$match" ]; then
      printf '%s\n' "$match"
      return 0
    fi
  done
  return 1
}

# Pretty-print a JSON file, falling back to raw cat if jq missing.
print_json() {
  local path="$1"
  if [ ! -r "$path" ]; then
    note "(file not readable: $path)"
    return
  fi
  if command -v jq >/dev/null 2>&1; then
    jq '.' "$path" >> "$OUT" 2>/dev/null || cat "$path" >> "$OUT"
  else
    cat "$path" >> "$OUT"
  fi
}

# Extract only the `contributes.configuration` block from a package.json,
# which is where extensions declare the settings they expose. Falls back
# to printing whole package.json minus the noisy bits if jq isn't there.
print_extension_config() {
  local pkg="$1"
  if [ ! -r "$pkg" ]; then
    note "(no package.json at $pkg)"
    return
  fi
  if command -v jq >/dev/null 2>&1; then
    note "## name + version"
    jq -r '"  name:        " + (.name // "?"),
           "  publisher:   " + (.publisher // "?"),
           "  version:     " + (.version // "?"),
           "  displayName: " + (.displayName // "?")' "$pkg" >> "$OUT" 2>/dev/null || true

    note ""
    note "## activationEvents (when the extension wakes up)"
    jq '.activationEvents // []' "$pkg" >> "$OUT" 2>/dev/null || note "(no activationEvents key)"

    note ""
    note "## contributes.configuration (settings the extension exposes)"
    jq '.contributes.configuration // null' "$pkg" >> "$OUT" 2>/dev/null || note "(no contributes.configuration)"

    note ""
    note "## contributes.commands (commands the extension registers)"
    jq '.contributes.commands // []' "$pkg" >> "$OUT" 2>/dev/null || true

    note ""
    note "## contributes.languages + breakpoints (debug-style integrations)"
    jq '{languages: (.contributes.languages // []),
         breakpoints: (.contributes.breakpoints // []),
         debuggers: (.contributes.debuggers // [])}' "$pkg" >> "$OUT" 2>/dev/null || true

    note ""
    note "## main / browser / module entry points"
    jq -r '"  main:    " + (.main // "(none)"),
           "  browser: " + (.browser // "(none)"),
           "  module:  " + (.module // "(none)")' "$pkg" >> "$OUT" 2>/dev/null || true

    note ""
    note "## extensionDependencies + extensionPack"
    jq '{extensionDependencies: (.extensionDependencies // []),
         extensionPack: (.extensionPack // [])}' "$pkg" >> "$OUT" 2>/dev/null || true
  else
    note "(jq not installed — printing whole package.json)"
    cat "$pkg" >> "$OUT"
  fi
}

# Grep the extension's compiled JS for spawn/exec/execFile patterns and
# any references to the agent binary names. This is the key signal:
# *which command does the extension actually try to run?*
grep_extension_for_spawns() {
  local ext_dir="$1"
  local main_js
  # Extensions are usually shipped as a single bundled JS file (esbuild,
  # webpack). The path is in package.json under "main"; if we don't have
  # jq, just grep the whole tree.
  if command -v jq >/dev/null 2>&1 && [ -r "$ext_dir/package.json" ]; then
    main_js=$(jq -r '.main // empty' "$ext_dir/package.json" 2>/dev/null)
    if [ -n "$main_js" ] && [ -f "$ext_dir/$main_js" ]; then
      note "Grepping main JS bundle: $main_js"
      _grep_in "$ext_dir/$main_js"
      return
    fi
  fi
  note "(falling back to recursive grep of $ext_dir)"
  while IFS= read -r -d '' f; do
    _grep_in "$f"
  done < <(find "$ext_dir" -name '*.js' -not -path '*/node_modules/*' -print0 2>/dev/null)
}

_grep_in() {
  local f="$1"
  note ""
  note ">>> $f"
  note ""

  note "## child_process.* call sites:"
  LC_ALL=C grep -EHno '(spawn|spawnSync|exec|execSync|execFile|execFileSync|fork)\s*\(' "$f" 2>/dev/null \
    | head -40 >> "$OUT" \
    || note "(no child_process matches)"

  note ""
  note "## binary-name references — claude / codex / opencode / pi (40 chars context):"
  for binname in claude codex opencode '\bpi\b' pi-coding-agent '@mariozechner/pi-coding-agent'; do
    note ""
    note "  pattern: $binname"
    LC_ALL=C grep -EHno ".{0,40}$binname.{0,40}" "$f" 2>/dev/null \
      | head -10 >> "$OUT" \
      || note "  (no matches)"
  done

  note ""
  note "## process.env.* reads (which env vars the extension consults):"
  LC_ALL=C grep -EHno 'process\.env\.[A-Z_][A-Z0-9_]+' "$f" 2>/dev/null \
    | sort -u \
    | head -40 >> "$OUT" \
    || note "(no process.env.* reads)"

  note ""
  note "## hardcoded paths under \$HOME / .vscode / config dirs:"
  LC_ALL=C grep -EHno '\.(claude|codex|config/opencode|local/share/opencode|pi/agent)[a-zA-Z./_-]*' "$f" 2>/dev/null \
    | head -20 >> "$OUT" \
    || note "(no hardcoded agent-state paths)"
}

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

cat > "$OUT" <<HEADER
VSCode coding-agent extension diagnostic
========================================

Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Host:      $(uname -a)
User:      ${USER:-<unset>}
PWD:       $PWD
Shell:     ${SHELL:-<unset>}
PATH:      $PATH
VSCode:    $(command -v code 2>/dev/null || echo "(not on PATH)")
node:      $(command -v node 2>/dev/null || echo "(not on PATH)")
jq:        $(command -v jq 2>/dev/null || echo "(not on PATH; some sections will be raw)")

Extensions probed:
$(printf '  - %s\n' "${EXTENSIONS[@]}")

Search roots:
$(for r in "${VSCODE_EXT_ROOTS[@]}"; do
    if [ -d "$r" ]; then
      printf '  ✓ %s (%d entries)\n' "$r" "$(ls -1 "$r" 2>/dev/null | wc -l | tr -d ' ')"
    else
      printf '    %s (absent)\n' "$r"
    fi
  done)
HEADER

# ---------------------------------------------------------------------------
# 1. Per-extension dump
# ---------------------------------------------------------------------------

section "1. Per-extension dump"

for ext_id in "${EXTENSIONS[@]}"; do
  subsection "$ext_id"
  if ext_dir=$(find_extension_dir "$ext_id"); then
    note "Install dir: $ext_dir"
    note ""
    note "Tree (top level only):"
    ls -la "$ext_dir" >> "$OUT" 2>&1 || true
    note ""

    pkg="$ext_dir/package.json"
    note "## package.json metadata"
    print_extension_config "$pkg"

    note ""
    note "## process spawn signatures"
    grep_extension_for_spawns "$ext_dir"
  else
    note "NOT INSTALLED at any of the search roots."
    note "Install with: code --install-extension $ext_id"
  fi
done

# ---------------------------------------------------------------------------
# 2. Currently-running agent processes
# ---------------------------------------------------------------------------

section "2. Currently-running agent processes (snapshot)"

note "If any of the four agents are spawned by VSCode right now, they'll"
note "appear below with full argv. Re-run this script after triggering"
note "the extension (e.g. opening the chat panel) to capture live procs."
note ""

note "## ps output filtered to agent binaries:"
# Use `ps -ef` then grep — works on Linux + macOS without extra flags.
for pat in "${BINARY_PATTERNS[@]}"; do
  note ""
  note "  pattern: $pat"
  ps -ef 2>/dev/null | grep -E "$pat" | grep -v 'grep -E' >> "$OUT" 2>&1 || note "  (no matches)"
done

note ""
note "## Per-process detail for matched agent processes (PIDs only):"
# macOS default bash is 3.2; `mapfile` needs 4+. Use a portable loop.
AGENT_PIDS=()
while IFS= read -r line; do
  [ -n "$line" ] && AGENT_PIDS+=( "$line" )
done < <(
  ps -ef 2>/dev/null | grep -E '(\bclaude\b|\bcodex\b|\bopencode\b|\bpi\b|@mariozechner/pi-coding-agent)' \
  | grep -v 'grep -E' \
  | awk '{print $2}' \
  | sort -u
)

if [ "${#AGENT_PIDS[@]}" -eq 0 ]; then
  note "(no agent processes running right now — open the extension panel and re-run)"
else
  for pid in "${AGENT_PIDS[@]}"; do
    note ""
    note ">>> PID $pid"
    note "argv (cmdline):"
    if [ -r "/proc/$pid/cmdline" ]; then
      tr '\0' ' ' < "/proc/$pid/cmdline" >> "$OUT"; printf '\n' >> "$OUT"
    else
      # macOS: use ps with -ww for full argv
      ps -p "$pid" -ww -o command= 2>/dev/null >> "$OUT" || note "(unreadable)"
    fi

    note ""
    note "cwd:"
    if [ -L "/proc/$pid/cwd" ]; then
      readlink "/proc/$pid/cwd" >> "$OUT" 2>&1 || true
    else
      lsof -p "$pid" 2>/dev/null | awk '$4 == "cwd" {print $NF}' >> "$OUT" || note "(lsof unavailable)"
    fi

    note ""
    note "parent (PPID + ppid argv):"
    if [ -r "/proc/$pid/status" ]; then
      ppid=$(awk '/^PPid:/{print $2}' "/proc/$pid/status")
      printf '  PPID=%s\n' "$ppid" >> "$OUT"
      tr '\0' ' ' < "/proc/$ppid/cmdline" 2>/dev/null >> "$OUT"; printf '\n' >> "$OUT"
    else
      ppid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
      [ -n "$ppid" ] && {
        printf '  PPID=%s\n' "$ppid" >> "$OUT"
        ps -p "$ppid" -ww -o command= 2>/dev/null >> "$OUT" || true
      }
    fi

    note ""
    note "open files (top 30):"
    lsof -p "$pid" 2>/dev/null | head -30 >> "$OUT" || note "(lsof unavailable)"

    note ""
    note "env (only A-Z* vars to keep PII low):"
    if [ -r "/proc/$pid/environ" ]; then
      tr '\0' '\n' < "/proc/$pid/environ" \
        | grep -E '^[A-Z_][A-Z0-9_]*=' \
        | grep -vE '^(MAIL|SSH_AUTH_SOCK|XDG_RUNTIME_DIR)=' \
        >> "$OUT" || true
    else
      note "(/proc/$pid/environ unavailable on this OS — see process detail above for argv)"
    fi
  done
fi

# ---------------------------------------------------------------------------
# 3. VSCode user / workspace settings
# ---------------------------------------------------------------------------

section "3. VSCode settings (User + Workspace)"

subsection "User settings"
for p in "${USER_SETTINGS_PATHS[@]}"; do
  note ""
  note ">>> $p"
  if [ -r "$p" ]; then
    print_json "$p"
  else
    note "(absent)"
  fi
done

subsection "Workspace settings ($PWD/.vscode/settings.json)"
if [ -r "$PWD/.vscode/settings.json" ]; then
  print_json "$PWD/.vscode/settings.json"
else
  note "(no .vscode/settings.json in cwd)"
fi

# ---------------------------------------------------------------------------
# 4. Existing CLI binaries on PATH (what would the extension find?)
# ---------------------------------------------------------------------------

section "4. CLI binaries on PATH that the extensions might invoke"

for bin in claude codex opencode pi; do
  note ""
  note ">>> $bin"
  if which="$(command -v $bin 2>/dev/null)"; then
    note "  PATH:        $which"
    note "  resolved:    $(readlink -f "$which" 2>/dev/null || echo "$which")"
    note "  shebang/header (first 3 lines):"
    head -3 "$which" 2>/dev/null | LC_ALL=C sed 's/^/    /' >> "$OUT" || true
    note "  version:"
    "$bin" --version 2>&1 | head -3 | LC_ALL=C sed 's/^/    /' >> "$OUT" || note "    (version command failed)"
  else
    note "  (not on PATH)"
  fi
done

note ""
note "Wrapper symlinks under coding-agents install dir (if any):"
for w in agent-claude agent-codex agent-opencode agent-pi; do
  note ""
  note ">>> $w"
  if which="$(command -v $w 2>/dev/null)"; then
    note "  PATH: $which"
    note "  resolved: $(readlink -f "$which" 2>/dev/null || echo "$which")"
  else
    note "  (not on PATH — coding-agents install hasn't run yet, or shell rc not re-sourced)"
  fi
done

# ---------------------------------------------------------------------------
# 5. VSCode extension host log tail (if findable)
# ---------------------------------------------------------------------------

section "5. VSCode extension host log tail"

# VSCode logs land under ~/.config/Code/logs/<date>/exthost*.log on Linux,
# ~/Library/Application Support/Code/logs/<date>/exthost*.log on Mac.
case "$OSTYPE" in
  darwin*) LOG_ROOT="$HOME/Library/Application Support/Code/logs" ;;
  *)       LOG_ROOT="$HOME/.config/Code/logs" ;;
esac

if [ -d "$LOG_ROOT" ]; then
  latest_session=$(ls -1d "$LOG_ROOT"/2* 2>/dev/null | sort -V | tail -1)
  if [ -n "$latest_session" ]; then
    note "Latest session dir: $latest_session"
    note ""
    while IFS= read -r logf; do
      note ">>> $logf (last 60 lines)"
      tail -60 "$logf" >> "$OUT" 2>&1 || true
      note ""
    done < <(find "$latest_session" -name 'exthost*.log' 2>/dev/null)
  else
    note "(no session dir under $LOG_ROOT)"
  fi
else
  note "(VSCode log root $LOG_ROOT does not exist)"
fi

# ---------------------------------------------------------------------------
# 6. Hints for the operator
# ---------------------------------------------------------------------------

section "6. What to do next"

cat >> "$OUT" <<'HINTS'
If §2 showed no running agent processes:
  1. Open VSCode in this directory.
  2. Activate ONE extension at a time:
     - Claude Code:  Cmd-Shift-P → "Claude: Start"  (or open the chat panel)
     - ChatGPT/Codex: Cmd-Shift-P → "ChatGPT: ..."
     - OpenCode:     Cmd-Shift-P → "OpenCode: ..."
     - Pi:           Cmd-Shift-P → "Pi: ..."
  3. Re-run this diagnostic — §2 will now show what each one spawned.

If §1 showed an extension as NOT INSTALLED:
  - Install via marketplace URL (printed in the script header) or via
    `code --install-extension <id>`.

If you're on a Mac without `lsof`/`/proc`:
  - §2's "open files" + "env" subsections will be sparse. The argv +
    cwd + ppid sections still work via `ps`.

To send the result back:
  - Compress with `gzip <output_filename>` (it's plain text, gzips well)
    and attach. The file should be 50KB-2MB depending on how many JS
    bundles got grepped.
HINTS

echo
echo "=========================================================="
echo "Diagnostic written to: $OUT"
echo "=========================================================="
echo
echo "Next steps:"
echo "  1. Open VSCode and activate each extension at least once"
echo "     (open the chat / sidebar panel for each)."
echo "  2. Re-run this script to capture the live processes."
echo "  3. Send me $OUT (gzip first if you like)."
echo
echo "Quick install (if you haven't already):"
for ext in "${EXTENSIONS[@]}"; do
  echo "  code --install-extension $ext"
done
