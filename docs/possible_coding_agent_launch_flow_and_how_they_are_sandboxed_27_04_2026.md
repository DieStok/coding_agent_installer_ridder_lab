# Coding-agent launch flows and sandbox coverage

**Date:** 2026-04-27 (last updated for the no-wrap-via-sif refactor)
**Status:** authoritative reference for operators + users
**Scope:** every plausible way to start a coding agent CLI (Claude, Codex, OpenCode, Pi) on a HPC cluster + VSCode workflow, and what sandboxing each path receives.

## Executive summary

There are **two hooks** that route an agent CLI through the lab's Apptainer sandbox:

1. **Settings.json wrapper hook** for Claude, Codex, and Pi — VSCode reads `claudeCode.claudeProcessWrapper`, `chatgpt.cliExecutable`, and `pi-vscode.path` and spawns those wrappers directly via absolute path. Deterministic.
2. **Shell-rc `$PATH` prefix shim** for everything else — `<install_dir>/bin/path-shim/` is prepended to `$PATH` so any process resolving binaries by name (`claude`, `codex`, `opencode`, `pi`) hits our wrapper before npm's copy. Deterministic *if* the calling process inherited the `$PATH` prefix.

Inside both hooks, a shared **`agent-vscode`** helper handles SLURM allocation: if `SLURM_JOB_ID` is set, exec the existing `agent-<n>` directly (zero overhead); otherwise allocate a single per-session SLURM job (`salloc --time=08:00:00 --mem=10G --cpus-per-task=2`) and run subsequent spawns into it via `srun --jobid=<cached>`. Every wrapped invocation runs in the SIF with audit logging, deny rules, and per-agent HOME bind-mounts.

**The matrix below is exhaustive.** Most cases are sandboxed automatically. Three are documented gaps: cron jobs, systemd-user units, and (rarely) custom debug adapters. Each gap has an explicit user-side workaround.

## When am I sandboxed? (decision tree)

```
Did you click a button in a Claude / Codex / Pi sidebar in VSCode?
  YES → Sandboxed (settings.json hook fires).

Did you click a button in OpenCode (any version)?
  YES, and you launched VSCode via SSH from a shell → Sandboxed (PATH-prefix).
  YES, and VSCode is local-app-launched → Not sandboxed; OpenCode v2 spawns the npm binary directly.

Did you type `claude` / `codex` / `opencode` / `pi` in any shell terminal?
  YES, your shell sources ~/.bashrc → Sandboxed (PATH-prefix).
  YES, you're inside a cron job / systemd unit / script started by such → Not sandboxed (gap).

Did you type `agent-claude` / `agent-codex` / `agent-opencode` / `agent-pi`?
  YES → Sandboxed if SLURM_JOB_ID is set; refused otherwise.

Did you `sbatch` a script that calls one of these agents?
  YES → Sandboxed; the job's own SLURM_JOB_ID is reused (no double allocation).

Did you set CODING_AGENTS_NO_WRAP=1?
  YES → SIF + deny rules + --containall isolation still apply (the env var
        only bypasses the lab wrapper template's preconditions). Triage-only
        path; technical-staff use only — see §23.
```

## Overview table

Legend: ✅ = caught and sandboxed; ⚠ = caught conditionally (caveat in notes); ❌ = not caught.

| # | Launch path | Caller / trigger | Hook that catches | Sandboxed? | First-spawn latency | Notes |
|---|---|---|---|---|---|---|
| 1 | Click "Send" in Claude / Codex / Pi sidebar | User mouse | settings.json | ✅ | ~5–15s on cold cache; ~200ms–2s warm | Worked example §1. |
| 2 | Click "Open Chat" in OpenCode v2 sidebar | User mouse | shell-rc PATH | ⚠ | ~5–15s cold | Only if VSCode was launched from a shell (Remote-SSH always does). §2. |
| 3 | Click "Open Terminal" in OpenCode classic | User mouse | shell-rc PATH (via integrated terminal) | ✅ | ~5–15s cold | Integrated terminal sources rc files. §3. |
| 4 | Right-click → "Explain this" / CodeLens (Claude) | User mouse | settings.json | ✅ | ~200ms–2s if jobid cached | One-shot; no UI session. §4. |
| 5 | Workspace open → extension auto-activation | VSCode itself | settings.json | ✅ | Hidden inside VSCode "Loading…" phase | Auto-srun fires before user clicks anything. **UX win.** §5. |
| 6 | Cmd-Shift-P → "Claude: Initialize" etc. | User keystroke | settings.json | ✅ | ~200ms–2s warm | Same as §1 mechanically. §6. |
| 7 | Integrated terminal: type `claude` (etc.) | User keystroke | shell-rc PATH | ✅ | Zero if in srun; ~5–15s if not | Auto-srun fires on login node. §7. |
| 8 | Integrated terminal: type `agent-claude` (etc.) | User keystroke | direct wrapper | ⚠ | n/a | Refuses if `SLURM_JOB_ID` unset (existing strict behaviour). §8. |
| 9 | Plain SSH terminal: type `claude` | User keystroke | shell-rc PATH | ✅ | Same as §7 | Auto-srun applies. §9. |
| 10 | Plain SSH terminal: type `agent-claude` | User keystroke | direct wrapper | ⚠ | n/a | Same as §8. §10. |
| 11 | `sbatch` script invoking the CLI | SLURM batch | shell-rc PATH or direct | ✅ | Zero (already in job) | `SLURM_JOB_ID` already set. §11. |
| 12 | `srun --pty bash` then type `claude` | User keystroke | shell-rc PATH | ✅ | Zero overhead | Existing-job path. §12. |
| 13 | `tasks.json` task running `claude --review` | User runs task | shell-rc PATH (via integrated terminal) | ✅ | Same as §7 | §13. |
| 14 | `launch.json` debug config | User F5 | varies | ⚠ | varies | Most debug adapters shell out → PATH catches. Some don't. §14. |
| 15 | Git pre-commit hook calls `claude --check` | User `git commit` | shell-rc PATH | ✅ | Same as §7 | §15. |
| 16 | Other extension calling Claude CLI | Extension host | shell-rc PATH | ⚠ | varies | If extension has hardcoded path, bypassed. §16. |
| 17 | User script: `subprocess.run(["claude", ...])` | User script | shell-rc PATH | ⚠ | varies | Catches if script ran from interactive shell. §17. |
| 18 | `coding-agents doctor` / `sync` exec'ing CLIs | Internal | bypass (absolute path) | n/a | n/a | We control this; intentionally unwrapped. §18. |
| 19 | Mac/Win VSCode → Remote-SSH'd workspace | App launcher | settings.json (Claude/Codex/Pi); shell-rc (OpenCode) | ✅ | ~5–15s cold | The path-shim is sourced by the SSH session, not your local launchd. §19. |
| 20 | Local-app-launched VSCode, local workspace, no SSH | App launcher | none (`coding-agents install --local`) | n/a | n/a | HPC sandbox doesn't apply; out of scope. §20. |
| 21 | **Cron job** running an agent | crond | none (cron shell ≠ login shell) | ❌ | n/a | **GAP.** Workaround in §21. |
| 22 | **Systemd-user unit** running an agent | systemctl | none (no .bashrc) | ❌ | n/a | **GAP.** Workaround in §22. |
| 23 | **`CODING_AGENTS_NO_WRAP=1`** (technical staff only) | env var override | bypasses wrapper template; goes through SIF | ⚠ | ~5–15s cold (apptainer exec direct) | **Triage-only path.** Use only when technical staff explicitly asks; SIF deny rules + `--containall` still apply, but the audit log, lab cwd policy, and per-agent bind tables are skipped. §23. |

---

## Worked examples

Each example walks through what the user does, what happens at process and SLURM levels, and what the user sees. Failures and recovery hints included.

### §1 — Click "Send" in the Claude sidebar

**User flow.** SSH-Remote'd VSCode connected to `hpcs05`. User opens a workspace at `/hpc/compgen/projects/lab_ai_automation/coding_agent_installer`. Cursor's extension host activates `anthropic.claude-code`. User opens the Claude pane, types "summarise this file", hits Cmd-Enter.

**Process tree.**
```
extension-host (node)
  └── /hpc/compgen/users/$USER/coding_agents/bin/agent-claude-vscode
        └── /hpc/compgen/users/$USER/coding_agents/bin/agent-vscode --agent claude -- ...
              ├── (first run only) salloc --account=compgen --time=08:00:00 --mem=10G --cpus-per-task=2
              └── srun --jobid=<cached> agent-claude --output-format stream-json ...
                    └── apptainer exec ... claude (in SIF)
```

**SLURM.** First user message after Cursor restart: 5–15s salloc latency. Subsequent messages: ~200ms–2s for `srun --jobid` to enter the job.

**Sandboxing applied.** SIF + audit log JSONL + deny rules from `bundled/hooks/deny_rules.json` + bind-mounts (`~/.claude/`, `~/.cache/`, `~/.gitconfig:ro`, `/etc/ssl/certs:ro`). The native `claude` binary inside the SIF connects out to `CLAUDE_CODE_SSE_PORT` on host loopback (default Apptainer netns is shared).

**What the user sees.** First click after Cursor restart shows the spinner for ~10s. Subsequent messages respond at normal Claude latency. `squeue -u $USER` shows a job named `cod-ag-vscode-$USER-$PID`.

**Failure modes.** `salloc` fails (account out of allocation). User sees a Claude error notification *"Could not allocate SLURM job — account=compgen denied. Run `sacctmgr show qos` or contact lab admin."* Lazy retry: next click 30+ seconds later attempts salloc once more.

---

### §2 — Click "Open Chat" in OpenCode v2 sidebar

**User flow.** Same setup. OpenCode v2 sidebar; click "+" → "New chat".

**Process tree.**
```
extension-host (node)
  └── child_process.spawn("opencode", ["--port", "21337", ...])
        └── (PATH lookup) <install_dir>/bin/path-shim/opencode
              └── exec <install_dir>/bin/agent-opencode-vscode
                    └── agent-vscode --agent opencode -- --port 21337
                          ├── (first run) salloc → JOB_ID
                          └── srun --jobid=$JOB_ID agent-opencode --port 21337
                                └── apptainer exec ... opencode --port 21337
```

The path-shim wins because the extension host inherited `$PATH` from the SSH session, which sourced `~/.bashrc`, which contains the `coding-agents`-injected line `export PATH=<install_dir>/bin/path-shim:$PATH`.

**Sandboxing applied.** Full SIF + audit log + bind-mounts (`~/.config/opencode/`, `~/.local/share/opencode/`, `~/.cache/opencode/`, `~/.local/state/opencode/` — all four).

**What the user sees.** Same UX as §1 — first-cold delay, then normal interaction. `curl -s http://127.0.0.1:21337/` from a separate terminal returns the OpenCode server-info JSON, confirming the SIF-bound port is reachable from the host.

**Failure modes.** If the shim is NOT inherited (rare on Remote-SSH; possible if the user disabled `.bashrc` sourcing), the npm-installed `opencode` runs unsandboxed. Mitigation: `coding-agents doctor` checks that `<install_dir>/bin/path-shim` is at the front of `$PATH` and warns otherwise.

---

### §3 — Click "Open Terminal" in OpenCode classic

**User flow.** OpenCode classic only has a single command: open an integrated terminal and run `opencode`.

**Process tree.**
```
extension-host
  └── vscode.window.createTerminal(...)
        └── /bin/bash (sources .bashrc → path-shim added)
              └── opencode (resolved via PATH to path-shim)
                    └── ... same as §2
```

Functionally identical to §2 from the wrapper's perspective. The terminal layer is invisible to the agent; the only difference is the user's UI surface (bash terminal vs sidebar webview).

---

### §4 — Right-click → "Explain this" (Claude CodeLens)

**User flow.** Right-click on a code selection in the editor → "Explain this with Claude" (or similar).

**Process tree.** Same as §1 but with one-shot argv:
```
extension-host
  └── agent-claude-vscode "explain" "<file_content>" "--no-chrome" ...
        └── agent-vscode → srun --jobid=<cached> agent-claude → apptainer exec claude
```

If a session jobid is already cached and the SLURM job is alive, this is a ~200ms–2s overhead. If not, full salloc latency applies.

**Sandboxing.** Identical to §1. Audit log records the one-shot invocation with full argv.

---

### §5 — Workspace open → extension auto-activation

**User flow.** User opens a folder in VSCode. VSCode auto-activates Claude / Codex / Pi extensions on `onStartupFinished` (within ~5s of window open).

**Process tree.** Same as §1, but **fired without user attention**. The extension does an init handshake with the CLI (auth check, version check) which spawns the binary.

**Why this matters for UX.** The 5–15s salloc latency is hidden inside VSCode's "Loading…" phase. By the time the user clicks "Send" 30s later, the SLURM job is allocated, cached, and warm. Their first message responds at normal latency.

**Caveat.** If VSCode crashes or the user closes/reopens the window quickly, the cached jobid file may be stale (job died but file lingers). The shim re-checks via `squeue -j $JOBID -h` and re-allocates if needed.

---

### §6 — Cmd-Shift-P → "Claude: Initialize project"

Functionally identical to §1. The Cmd-Shift-P pick triggers a command handler that calls `child_process.spawn(<settings-path>)`.

---

### §7 — Integrated terminal: user types `claude`

**User flow.** User opens VSCode integrated terminal (`Ctrl-`​​​`​). Terminal sources their `.bashrc`, which has the `coding-agents` injection block. User types `claude` and hits enter.

**Process tree.**
```
bash (sourced .bashrc)
  └── PATH-resolves "claude" → <install_dir>/bin/path-shim/claude
        └── exec <install_dir>/bin/agent-claude-vscode
              └── agent-vscode → ... (auto-srun if not in job)
```

If the user already started Cursor inside `srun --pty bash`, `SLURM_JOB_ID` is set in the inherited env. The shim sees it and execs `agent-claude` directly with zero overhead. Otherwise auto-srun fires.

**What the user sees.** If on login node: "Allocating SLURM job…" status (we'll print this from the shim) for 5–15s, then claude REPL. If in srun: instant claude REPL.

**Why we auto-srun even from a terminal.** Cases like "user opens a terminal to ask Claude a quick question" should still apply lab-wide sandboxing. The `cd` they're in might be sensitive; the deny rules + audit log apply. Forcing them to manually `srun --pty bash` first would be hostile UX for what's intended to be a uniform "type the agent name and it works" experience.

---

### §8 — Integrated terminal: user types `agent-claude`

**User flow.** User explicitly types `agent-claude` (the wrapper) instead of `claude` (the bare CLI).

**Process tree.**
```
bash → PATH-resolves "agent-claude" → <install_dir>/bin/agent-claude (existing wrapper, NOT shim)
        ├── if SLURM_JOB_ID set: continue with apptainer exec
        └── if SLURM_JOB_ID unset: exit 3 with "refusing to run on submit node"
```

**Why no auto-srun.** `agent-claude` is the explicit terminal wrapper. Typing it is an explicit "I know what I'm doing, refuse if I'm wrong" gesture. Auto-srun is reserved for the bare-CLI-name path (`claude`) where the user may not realise they're being routed through the wrapper.

**Recovery.** User sees `agent-claude: refusing to run on submit node (SLURM_JOB_ID unset).` in the terminal, with a hint to run `srun --pty bash` first. They follow the hint, retry.

---

### §9 — Plain SSH terminal: type `claude`

Functionally identical to §7. The user SSHs to the cluster, gets a bash shell, types `claude`. Bash sources `.bashrc` on interactive login → path-shim is on PATH → wrapper fires → auto-srun if needed.

---

### §10 — Plain SSH terminal: type `agent-claude`

Functionally identical to §8.

---

### §11 — `sbatch script.sh` where the script invokes `claude`

**User flow.** User submits a batch job via `sbatch my_review_job.sh`. The script contains `claude --review --files src/` or similar.

**Process tree.**
```
slurmctld → slurmstepd (script runs in SLURM-allocated env, SLURM_JOB_ID set)
  └── bash my_review_job.sh
        └── PATH-resolves "claude" → path-shim → agent-claude-vscode
              └── agent-vscode sees SLURM_JOB_ID → no salloc, just exec agent-claude
                    └── apptainer exec ... claude
```

**Sandboxing.** Full SIF + audit log + bind-mounts. Audit log entries from this batch job are distinguishable by `slurm_job_id` field.

**No double-allocation.** The shim correctly detects the existing SLURM_JOB_ID and reuses it.

---

### §12 — `srun --pty bash` then `claude`

**User flow.** User runs `srun --account=compgen --time=08:00:00 --mem=10G --cpus-per-task=2 --pty bash` from a login terminal. Inside the resulting compute-node shell, types `claude`.

**Process tree.** As §7, but `SLURM_JOB_ID` already set → no salloc → zero overhead.

**This is the canonical "good user" flow.** Users who care about resource accounting allocate explicitly; the wrapper runs with full sandboxing and zero auto-allocation.

---

### §13 — `tasks.json` task running `claude --review`

**User flow.** User defined a VSCode task in `.vscode/tasks.json`:
```json
{
  "label": "Claude review",
  "type": "shell",
  "command": "claude --review --files ${file}"
}
```
User runs the task via Cmd-Shift-B or Quick Pick.

**Process tree.** VSCode default `type: "shell"` runs the command via the user's shell. Shell inherits the path-shim. Same as §7. `${file}` substitution happens at the VSCode level before the shell sees it.

**Edge case.** If the user used `"type": "process"` instead, VSCode `execve`'s directly — bypassing the shell. PATH lookup still happens (via `posix_spawn`'s PATH search), so the shim is still found. ✅

---

### §14 — `launch.json` debug config

**User flow.** User F5's a debug config that exec's an agent CLI (rare; this would be debugging the CLI itself).

**Process tree.** Depends on the debug adapter. Most adapters shell out to start the debuggee, which means the shell-rc PATH applies. Some adapters use a custom `execve` with a pristine env — bypasses the shim.

**Verdict.** Mostly ✅, occasional ⚠. **Not a critical path** — debugging an agent CLI is rare; if it matters for a user, they can hardcode the absolute path in their launch config.

---

### §15 — Git pre-commit hook calls `claude --check`

**User flow.** User has a pre-commit hook (`.git/hooks/pre-commit` or via the `pre-commit` framework) that runs `claude --check src/` to lint with Claude before each commit.

**Process tree.**
```
git commit
  └── /bin/sh .git/hooks/pre-commit (interactive shell — sources whatever git's PATH set up)
        └── claude → path-shim → agent-claude-vscode → ... (auto-srun if not in job)
```

**Caveat.** Git hooks run in a shell whose env was inherited from the calling `git` process. If the user started `git commit` from a terminal that had path-shim on PATH, the hook does too. ✅

If the user used a GUI git client (sourcetree, GitHub Desktop) that runs git in a non-interactive context, the hook may not have `path-shim` on PATH. Mitigation: hooks should call `<install_dir>/bin/agent-claude` explicitly, not `claude`.

---

### §16 — Other extension calling Claude CLI

**User flow.** A third-party VSCode extension (e.g., a "code review with AI" extension) does `child_process.spawn("claude", [...])`.

**Process tree.** Extension host inherits the same `$PATH` we set up for Remote-SSH sessions. Path-shim catches. ✅

**Caveat.** If the extension uses a hardcoded absolute path (e.g., `~/.claude/bin/claude` or `/usr/local/bin/claude`), the shim is bypassed. Doctor can scan installed extensions' source for hardcoded paths and warn.

---

### §17 — User script: `subprocess.run(["claude", ...])`

**User flow.** User has a Python or bash script that calls `claude` programmatically.

**Process tree.**
```
python script.py
  └── subprocess.run(["claude", ...]) → execvp PATH lookup → path-shim → agent-claude-vscode → ...
```

**Caught by the shim** if the parent Python script ran from a shell with path-shim on PATH. If the script was launched non-interactively (cron, systemd, docker, …), see §21/§22 — gap.

---

### §18 — `coding-agents doctor` / `sync` exec'ing CLIs

**Internal flow.** Our own `coding-agents` Python doesn't exec the agent binaries at all anymore. After the no-wrap-via-sif refactor (plan: `docs/plans/2026-04-27-003-...`):

- `doctor` checks each agent by verifying that the **wrapper** at `<install_dir>/bin/agent-<key>` exists AND that the configured SIF is readable. No binary exec required.
- `doctor`'s SIF-level probes (Codex protocol drift, Pi defaults baked) call `apptainer exec <sif> <agent> --version` or `apptainer exec <sif> test -r /opt/...` — through the SIF, with `--containall`. Short query-only invocations on a compute node.
- `sync` doesn't exec any agent binary; it only emits config files (Codex hooks, OpenCode permissions, VSCode wrapper settings).

**Sandboxing applied for the SIF probes.** All apptainer-exec calls go through the SIF. No host binary is exec'd by `coding-agents doctor` / `sync` anywhere.

---

### §19 — Mac/Win VSCode → Remote-SSH'd workspace

**User flow.** User on a Mac runs VSCode locally, opens a Remote-SSH'd folder on the cluster. The extension host runs on the cluster (in the user's SSH-spawned shell context), not on the Mac.

**Process tree.** All four agents' settings.json hooks (Claude/Codex/Pi) work because the settings.json is read from `~/.vscode-server/data/User/settings.json` on the cluster, and points at `/hpc/.../coding_agents/bin/agent-<n>-vscode` paths that exist on the cluster. ✅

For OpenCode: the Remote-SSH session sourced `.bashrc` on the cluster → path-shim is on the cluster-side `$PATH` → extension host's `child_process.spawn("opencode")` finds the shim. ✅

**This is the lab's expected primary workflow.** Everything works.

---

### §20 — Local-app-launched VSCode, local workspace, no SSH

**Out of scope for this doc.** The HPC sandbox doesn't apply to a Mac-only workflow. Users on local-only workflows install with `coding-agents install --local`, which:
- Does NOT emit the VSCode wrap settings (the wrappers wouldn't exist locally anyway).
- Does NOT do SLURM stuff.
- Just provides a clean `coding-agents`-managed install of the four agents on PATH.

**Sandboxing not provided.** Users who want sandboxing must use Remote-SSH'd VSCode against a real HPC cluster.

---

### §21 — Cron job running an agent (DOCUMENTED GAP)

**User flow.** User has a crontab entry like `0 9 * * * /usr/bin/claude --daily-summary > /tmp/log 2>&1`.

**Why this isn't caught.** Cron's bash runs **non-interactively** — it does NOT source `~/.bashrc`. Therefore the path-shim injection in `.bashrc` is invisible. `claude` resolves via cron's hardcoded `PATH=/usr/bin:/bin` to `/usr/bin/claude` (or wherever it lives), unsandboxed.

**Workaround:**
```cron
# Wrong (unsandboxed):
0 9 * * * claude --daily-summary

# Right (always sandboxed):
0 9 * * * /hpc/compgen/users/$USER/coding_agents/bin/agent-claude --daily-summary
```

Use the absolute path to `agent-<n>` (the wrapper, not the shim). The wrapper enforces SLURM gating, so the cron entry will need to either:
- Run inside an `sbatch` (submit a batch job from cron), OR
- Set `SLURM_JOB_ID` itself somehow (rare — usually you want sbatch).

A safer cron pattern:
```cron
0 9 * * * sbatch -J daily-claude --account=compgen --time=00:30:00 --mem=10G --wrap="$HOME/coding_agents/bin/agent-claude --daily-summary"
```

**Mitigation in `coding-agents doctor`.** Add a `--scan-cron` mode that reads `crontab -l` and warns if it finds bare `claude`/`codex`/`opencode`/`pi` invocations.

---

### §22 — Systemd-user unit running an agent (DOCUMENTED GAP)

**User flow.** User has `~/.config/systemd/user/claude-watcher.service` that ExecStart's `claude --watch /tmp/queue/`.

**Why this isn't caught.** Same as §21: systemd doesn't source `.bashrc`. The unit's PATH is whatever the user explicitly set in the unit file (or systemd-user's default).

**Workaround.** Same as §21: use absolute path to the wrapper.

```ini
# Wrong:
ExecStart=/usr/bin/claude --watch /tmp/queue/

# Right:
ExecStart=/hpc/compgen/users/%u/coding_agents/bin/agent-claude --watch /tmp/queue/
```

Or, better: use a `ExecStartPre` that allocates a SLURM job and launch the agent inside the allocation.

**Mitigation.** `coding-agents doctor` should `systemctl --user list-unit-files` and warn on bare CLI invocations.

---

### §23 — `CODING_AGENTS_NO_WRAP=1` (technical staff triage path)

> **⚠️ Do not use this path unless lab technical staff explicitly asks
> you to.** It exists for one purpose only: isolating wrapper-template
> bugs from agent-level bugs during triage. It is **not** a way to
> "make the agent run faster" or "skip prompts" or "use my host
> credentials" — there is no legitimate user-facing reason to set it.
> Doctor surfaces a warn row when the variable is in the environment.

**What it bypasses, what it preserves.**

| Skipped (wrapper template's job) | Preserved (SIF + apptainer's job) |
|---|---|
| SLURM auto-srun + jobid cache + flock | The SIF itself (deny rules, `--containall`, `--no-mount home`, `--bind $TMPDIR:/tmp`) |
| Lab cwd-policy refusal | Apptainer's bind-mount discipline + `--no-privs` |
| Audit-log JSONL emission | Version pinning (codex/opencode/pi/claude all SIF-baked) |
| Per-agent lab bind tables (`~/.cache`, `/etc/ssl/certs`, …) | Cwd + agent's config dir (rw) — minimal binds |
| Pre-existing `APPTAINER_BIND` merge | The SIF's baked-in deny rules and isolation |

**Process tree.**
```
extension-host (or shell)
  └── agent-<n>-vscode (3-line bash stub)
        └── agent-vscode --agent <n> -- ARGV
              └── (NO_WRAP=1 detected → BYPASS the wrapper template)
                  apptainer exec --containall --no-mount home \
                    --writable-tmpfs --no-privs \
                    --bind $TMPDIR:/tmp \
                    --bind <cwd>:<cwd>:rw \
                    --bind <agent_config_dir>:<agent_config_dir>:rw \
                    <sif> <agent> ARGV
```

**Sandboxing applied.** SIF-level only. The agent runs **inside** the
SIF, so deny rules + `--containall` isolation still apply, but the
wrapper template's *additional* protections (lab cwd refusal, audit
log, full bind-mount table, SLURM accounting) are skipped.

**Requires `apptainer` on PATH.** On the lab cluster apptainer is
compute-only — NO_WRAP=1 must run inside an `srun --pty` shell. On a
login node it exits non-zero with a clear `apptainer not on PATH`
error and a hint to switch to a compute-node session.

**When technical staff might ask you to use it.** Triage scenarios
like:
- *"Is the wrapper template's cwd policy refusing your invocation?"*
  Set NO_WRAP=1; if the agent now runs, the policy is the culprit.
- *"Is the audit-log JSONL emission breaking on a corrupted file?"*
  Same idea.
- *"Is one of the lab bind-mounts failing?"* Same idea.

If technical staff hasn't asked: **don't use this.** The wrapper
template's protections exist for good reasons (audit, accounting,
deny-rule discipline) and the wrapped flow is only ~200 ms slower
than NO_WRAP for the warm-cache case.

**How to clean up after a triage session.** Just `unset
CODING_AGENTS_NO_WRAP` in your shell, and the doctor warn row goes
away. No persistent state on disk.

---

## Summary of gap handling

| Gap | Workaround | Mitigation in installer |
|---|---|---|
| Cron jobs (§21) | Absolute path to `agent-<n>`; consider `sbatch --wrap=…` | `coding-agents doctor --scan-cron` warns |
| Systemd-user units (§22) | Absolute path to `agent-<n>` | `coding-agents doctor --scan-systemd` warns |
| Custom debug adapters (§14) | Hardcode absolute path in `launch.json` | Document in install README |
| Hardcoded paths in 3rd-party extensions (§16) | None automatic | `coding-agents doctor` scans extension JS for absolute path strings |

## See also

- `docs/wrapping_vscode_extensions_deep_research_27_04_2026.md` — research brief for the wrap implementation
- `docs/brainstorms/2026-04-27-vscode-extension-wrapping-brainstorm.md` — design decisions for this work
- `bundled/templates/wrapper/agent.template.sh` — the existing terminal wrapper (`agent-<n>` referenced throughout)
- README.md "Sandboxing reference" section — links here
