---
name: VSCode coding-agent extension wrapping
description: Design decisions captured before implementing the SIF-wrap of Claude/Codex/OpenCode/Pi VSCode extensions, gating SLURM jobs, and documenting launch-flow coverage.
type: project
date: 2026-04-27
origin: docs/wrapping_vscode_extensions_deep_research_27_04_2026.md
companions:
  - docs/possible_coding_agent_launch_flow_and_how_they_are_sandboxed_27_04_2026.md
  - docs/vscode_extension_wrap_brief_27_04_2026.md  # input brief
---

# VSCode coding-agent extension wrapping — brainstorm

## What we're building

Make every coding-agent CLI invocation that originates from a VSCode (or Cursor) extension on the lab's HPC cluster route through the existing `agent-<n>` Apptainer wrapper, just as terminal-launched agents already do. Today only terminal CLI use is sandboxed; clicking "Send" in a Claude / Codex / Pi sidebar (or any OpenCode interaction) bypasses the SIF, the deny rules, the audit log, and SLURM accounting.

The goal is **uniform sandboxing across launch surfaces**: GUI sidebar clicks, integrated terminals, plain SSH terminals, batch scripts — all run the agent inside the SIF with audit logging and bind-mounted state, allocating SLURM resources transparently when the user hasn't pre-allocated them.

## Why this approach

The deep research brief established that:

- Three of four extensions expose a binary-path setting hook (`claudeCode.claudeProcessWrapper`, `chatgpt.cliExecutable`, `pi-vscode.path`). Pointing those at our wrapper script is sufficient and deterministic.
- OpenCode (both classic and v2) exposes no such setting. The only viable interception is a `$PATH`-prefix shim placed earlier in `$PATH` than npm's installed copy. That works deterministically when the calling process inherits the prefixed `$PATH` (which Remote-SSH-launched VSCode does via the user's `.bashrc`).
- Apptainer's defaults pass stdin/stdout/stderr through transparently and share the host loopback network namespace by default — so every IPC pattern the four extensions use (Claude's stream-JSON over stdio + SSE port; Codex's JSON-RPC over stdio; OpenCode's HTTP server on a localhost port; Pi's PTY-over-stdio + HTTP bridge) survives the wrapper unchanged.

Layered on top of the brief, the brainstorm round added **automatic SLURM job allocation**: VSCode runs on the login node where there's no `SLURM_JOB_ID`, but our existing wrapper requires one. Rather than refusing every GUI click or asking users to launch VSCode from inside `srun --pty bash`, the shim auto-allocates a single per-Cursor-session SLURM job and routes every spawn into it via `srun --jobid=<cached>`. For three of the four extensions (Claude, Codex, Pi) the first-spawn cost (5–15 s) is hidden inside `onStartupFinished` extension auto-activation — fired on workspace-open before the user clicks anything. For OpenCode v2 the cost lands on the user's first sidebar click, since OpenCode v2 only spawns on demand. Subsequent spawns within the session are ~200 ms–2 s. Existing `SLURM_JOB_ID` (e.g., user already ran `srun --pty bash`) is reused.

The architecture deliberately keeps the existing terminal `agent-<n>` wrapper unchanged. New work lives in a shared `agent-vscode` Python helper plus four thin per-extension stubs. This isolates the SLURM-allocation complexity from the proven terminal-path code; if the new code breaks, the terminal flow keeps working.

## Key decisions

### 1. Auto-srun primary, refuse-with-retry fallback
**Decided 2026-04-27.** When `SLURM_JOB_ID` is unset and no usable cached jobid exists, the shim runs `salloc --account=compgen --time=08:00:00 --mem=10G --cpus-per-task=2 --no-shell --job-name=cod-ag-vscode-${USER}-${$}` to allocate a single per-session job, caches the resulting JOB_ID at `~/.coding-agents/vscode-session.jobid` (under `flock`), and runs every subsequent spawn via `srun --jobid=$JOB_ID`.

**Failure handling.** If `salloc` fails (account out, partition full, network blip), the shim refuses with a clear error in the VSCode notification and writes a failure-timestamp sentinel next to the cached jobid file. The **next** spawn ≥30 s after the failure attempts `salloc` exactly once more. If that retry also fails, all subsequent spawns refuse (without retrying) until either (a) Cursor is restarted, (b) the user explicitly runs `coding-agents vscode-reset` (new helper, clears the sentinel), or (c) the failure-timestamp ages out after 4 hours. Rationale: avoid hammering SLURM with auto-retries every 30 s when the cluster is genuinely full; one retry handles transient blips, anything beyond that needs human attention.

Rejected: silently degrading to unwrapped (would defeat the whole point), or always wrapping without SLURM (loses accounting), or unbounded retry-every-30 s (wastes salloc rate-limit budget).

### 2. Single shared `agent-vscode` Python helper + per-extension stubs
**Decided 2026-04-27.** All SLURM/jobid-cache/auto-srun logic lives in `<install_dir>/bin/agent-vscode` (Python, ~150 lines). Each `agent-<n>-vscode` is a 3-line bash stub: `exec agent-vscode --agent <n> -- "$@"`. Rejected: 4× duplicate bash shims (the brief's default; ~30 lines × 4 = bigger audit surface), extending the existing terminal `agent-<n>` (bigger blast radius if logic breaks), one Python CLI subcommand on the main `coding-agents` typer app (~150 ms Python startup tax per spawn).

### 3. VSCode-first, Cursor-compatible
**Decided 2026-04-27.** The lab's actual setup is VSCode (`TERM_PROGRAM=vscode`, version 1.104.x). Cursor uses the same extension API and same remote-server `data/User/settings.json` layout, so the implementation works for both. The notable Cursor-specific divergence is the desktop settings store (Cursor desktop uses SQLite `state.vscdb`; Cursor *remote-server* uses JSON like VSCode). The remote-server case is what matters for the lab. The deep-research brief was rewritten to make this distinction explicit. (No separate `code-wrapped`/`cursor-wrapped` launcher is shipped — see decision 4 for the chosen mechanism.)

### 4. OpenCode wrapping via shell-rc `$PATH` prefix
**Decided 2026-04-27.** The installer's existing `inject_shell_block` already adds `<install_dir>/bin` to the user's `~/.bashrc`. Extend the same injection block to prepend `<install_dir>/bin/path-shim/` (with higher priority). Result: any Remote-SSH'd VSCode session inherits the prefix automatically; OpenCode v2's `child_process.spawn("opencode")` resolves to our shim before npm's `node_modules/.bin/opencode`. Rejected: a separate `code-wrapped`/`cursor-wrapped` launcher (relies on user discipline to not double-click the IDE icon — operational fragility); `terminal.integrated.env.linux.PATH` only (catches integrated terminal but misses extension-host spawn for OpenCode v2).

A `CODING_AGENTS_NO_WRAP=1` escape-hatch env var lets users explicitly bypass the shim for debugging, CI, or operator sanity-checks.

### 5. Codex SIF-pinned, document protocol-drift risk
**Decided 2026-04-27.** `agent-codex-vscode` runs the SIF's pinned `@openai/codex` (already in `bundled/sif/package.json`), not the extension's bundled binary. If a future extension auto-update bumps the JSON-RPC protocol past what the SIF supports, `assertSupportedCodexAppServerVersion` will reject the handshake; doctor warns and the user either freezes the extension version or the lab rebuilds the SIF. Rejected: bind-mounting the extension's bundled binary into the SIF (creates a brittle dependency on extension dir layout and the extension's library deps).

### 6. Settings-file resolution: explicit > VSCODE_AGENT_FOLDER > prefix probe
**Decided 2026-04-27.** `_emit_managed_vscode_settings(install_dir, target_settings_path=None)` resolves the settings.json in this order: (1) explicit caller-provided `target_settings_path`; (2) `${VSCODE_AGENT_FOLDER}/data/User/settings.json` if the env var is set; (3) probe known prefixes in this order: `~/.cursor-server`, `~/.vscode-server`, `~/.vscode-server-insiders`, `~/.windsurf-server`, `~/.vscodium-server`. The user's lab path (`/hpc/.../cursor_and_vscode_remote_server/.vscode-server/data/User/settings.json`) is captured by (1) in the installer or (2) via the env var. JSONC tolerance with comment loss accepted, data-preserving deep-merge, atomic write via `tempfile + os.replace`, `.bak` before first edit. Library choice (json5, commentjson, custom regex strip) is plan-level.

### 7. Bind-mount additions: minimal known-needed set per agent
**Decided 2026-04-27.** Each agent's `agent-<n>-vscode` shim adds the bind-mounts the agent demonstrably needs (already enumerated in the brief §5.3). Common across all four: `/etc/ssl/certs:ro`, `/etc/pki:ro`, `/etc/resolv.conf`, `/etc/hosts`, `~/.gitconfig:ro`. Per-agent: Claude needs `~/.cache:ro`, `~/.bun:ro`, `~/.npm:ro` (for MCP via npx); Codex needs `/tmp` (for the codex-arg0 lockdir); Pi needs the extension's own install dir read-only (the bundled pi-side extension lives there). The existing wrapper's `~/.{claude,codex,pi/agent,config/opencode,…}` writable binds (Sprint 1.5) cover the rest. Bind list lives in `agent-vscode` Python config, per-agent.

### 8. cwd policy unchanged
**Decided 2026-04-27.** The existing strict cwd policy (refuse `/hpc/compgen/users/shared/*` and bare `/hpc/compgen/projects/<project>/`; warn on missing `$USER` component) applies to VSCode-launched agents identically to terminal-launched. Lab convention is the same regardless of how the agent was invoked. If a user opens a VSCode workspace at a forbidden cwd, the first agent spawn refuses with the same exit-12 message as the terminal path.

### 9. Auto-srun for terminal users typing bare CLI names
**Decided 2026-04-27.** Case #7 in the launch-flow doc — a user on the login node types `claude` in a terminal — fires auto-srun via the path-shim, same as the GUI flow. Rejected: hard-refusing terminal users to enforce explicit `srun` discipline (would create inconsistent UX between "click Send in sidebar" and "type claude in terminal", both of which users perceive as the same kind of action). Users who prefer the explicit terminal flow can still run `srun --pty bash` first and then type `claude` — the shim detects the existing job and adds zero overhead.

### 10. Document gaps for cron / systemd / hardcoded-path edge cases
**Decided 2026-04-27.** Cron jobs and systemd-user units don't source `.bashrc`, so the path-shim is invisible to them. Third-party VSCode extensions that hardcode an absolute path to `claude`/`codex`/etc. bypass both hooks. These are documented as known limitations in `docs/possible_coding_agent_launch_flow_and_how_they_are_sandboxed_27_04_2026.md` (§21, §22, §16). Workaround for users: use absolute path `<install_dir>/bin/agent-<n>` in cron / systemd, possibly with `sbatch --wrap=…` for SLURM accounting. `coding-agents doctor` will gain optional `--scan-cron` and `--scan-systemd` modes that warn on bare-name invocations. Rejected: aggressively patching `BASH_ENV` or `/etc/profile.d` to inject the path-shim system-wide (unbounded blast radius; fights with other tools).

### 11. `CODING_AGENTS_NO_WRAP=1` escape hatch
**Decided 2026-04-27.** Both the path-shim and the per-extension stubs respect `CODING_AGENTS_NO_WRAP=1`. When set, the shim execs the npm-installed binary directly with no wrapping. Use cases: debugging the bare CLI; CI scripts that need the unwrapped output; operators sanity-checking against unwrapped behaviour. Doctor surfaces this in its env-summary.

### 12. Rollout order: Pi → Claude → Codex → OpenCode (per brief)
**Decided 2026-04-27.** Smallest surface area first; OpenCode last because it requires the path-shim work and the doctor scans. Each lands as its own commit (or commit pair: code + tests) with full test suite passing before the next starts. Per-agent manual-verification checklist captured in the launch-flow doc and the eventual implementation plan.

## Resolved questions

The questioning round resolved every "open" item that affects the implementation. No active open questions remain.

(Earlier draft had: "should auto-srun also apply when terminal users type bare CLI names?" — resolved as YES (decision 9). "Cron and systemd workarounds — auto-fix or document?" — resolved as document-only with doctor warnings (decision 10).)

## Out of scope

- **Local-mode VSCode without SSH.** Out of scope; users on a Mac running local VSCode against a local workspace install with `--local` and don't get the wrap settings (which would point at non-existent paths anyway).
- **Aggressive system-wide PATH injection** (`/etc/profile.d`, system bash configs). Bigger blast radius than the win; not pursued.
- **Symlink-replacing extension binaries.** Considered as fallback for OpenCode v2; rejected due to extension auto-update fragility.
- **Forking the extensions.** Marketplace-violating. Out of scope.
- **A long-lived background daemon that pre-allocates SLURM jobs.** Considered for warmup; deferred. The current "auto-srun fires during extension auto-activation" pattern hides most of the latency without needing a daemon.

## Sources & references

- **Input brief:** `docs/wrapping_vscode_extensions_deep_research_27_04_2026.md` — deep-research output covering per-extension launch mechanism, settings keys, env-var contracts, IPC protocols, Apptainer cross-cutting confirmations, and a baseline implementation plan.
- **Launch-flow companion doc:** `docs/possible_coding_agent_launch_flow_and_how_they_are_sandboxed_27_04_2026.md` — the 22-row matrix of every plausible startup path with worked examples and gap workarounds. README links to this.
- **Diagnostic capture:** `vscode_extensions_diagnostic_20260427_084046.txt` (in user's `~/Downloads/`) — live process snapshot from the lab HPC node, surfaced the running argv / env / state-dir use of each extension.
- **Earlier diagnostic-prep brief:** `docs/vscode_extension_wrap_brief_27_04_2026.md` — the input the deep-research agent worked from.

## Next step

Run `/ce:plan` against this brainstorm to produce the implementation plan. The plan should:
- Specify file-level changes (new `agent-vscode` Python module, `agent-<n>-vscode` stubs, `policy_emit._emit_managed_vscode_settings`, `merge_settings.deep_merge_jsonc_settings`, doctor `--scan-cron`/`--scan-systemd` modes).
- Sequence the rollout per decision 12 (Pi → Claude → Codex → OpenCode), one commit family per agent.
- Include the test matrix from the deep-research brief §5.4 plus the specific cases for the auto-srun logic (existing-jobid reuse, fresh-allocation, retry-on-failure, escape-hatch env var, settings-file resolution chain).
- Update the README "Sandboxing reference" link target if the launch-flow doc moves; otherwise leave the existing link.

Estimated scope: ~150 lines of Python (`agent-vscode` + `_emit_managed_vscode_settings` + `merge_settings` JSONC handling), ~50 lines of bash across the four shims and the path-shim, ~200 lines of tests, plus the doctor scan modes (~80 lines). Total: ~480 lines of new code; ~10–15 hours of implementation if no integration surprises.
