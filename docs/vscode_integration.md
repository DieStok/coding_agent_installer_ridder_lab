# VSCode integration — operator how-to

This is the user-facing companion to the implementation plan
(`docs/plans/2026-04-27-002-feat-vscode-extension-wrapping-plan.md`). If
you've installed `coding-agents` in HPC mode and you want to know what
got wired into your VSCode (or VSCode-derivative) settings, why your
sidebar takes 5 s to respond on the first message, and how to recover
when something gets stuck — this is the page.

## What gets wrapped

Every extension that exposes a "spawn this binary" hook gets pointed at
our wrapper:

| Extension | Mechanism | Settings key (or shim) |
|---|---|---|
| Claude Code (`anthropic.claude-code`) | settings.json key | `claudeCode.claudeProcessWrapper` → `<install_dir>/bin/agent-claude-vscode` |
| ChatGPT / Codex (`openai.chatgpt`) | settings.json key | `chatgpt.cliExecutable` → `<install_dir>/bin/agent-codex-vscode` |
| Pi (`pi0.pi-vscode`) | settings.json key | `pi-vscode.path` → `<install_dir>/bin/agent-pi-vscode` |
| OpenCode v2 (`sst-dev.opencode-v2`) | shell-rc PATH-prefix shim | `<install_dir>/bin/path-shim/opencode` symlink, `terminal.integrated.env.linux.PATH` defence-in-depth |

Each spawn flows: extension → `agent-<n>-vscode` (3-line bash stub) →
`agent-vscode` (Python helper) → `salloc --no-shell` (only if no live
SLURM job is cached) → `srun --jobid=<id>` → existing `agent-<n>`
wrapper → `apptainer exec ... <binary>`.

## What's the latency

| Event | Wall-clock |
|---|---|
| First spawn after VSCode connects | 5–15 s (salloc + SIF entry) |
| Subsequent spawns | 1–3 s (srun overhead only) |
| First spawn after walltime expiry (8 h default) | 5–15 s (one re-allocation) |

The first-spawn cost is hidden behind extension auto-activation for
Claude / Codex / Pi (the panel UI is responsive; the 5–15 s delay is in
the "thinking" indicator before the first response). OpenCode users see
it more directly because the panel mounts only after the binary
responds.

## How to bypass

Set `CODING_AGENTS_NO_WRAP=1` in the environment of whatever VSCode
session you want unwrapped. The helper exec's the npm-installed binary
directly without SLURM. `coding-agents doctor` will surface this as a
warning so you don't forget you set it.

## How to reset

If a session gets stuck (e.g. salloc was retrying when VSCode restarted,
or you want to release the SLURM allocation early):

```bash
coding-agents vscode-reset
```

Best-effort `scancel`s the cached jobid, removes the cache file. The
next sidebar spawn allocates fresh.

If the cache file is on a network FS that's gone unresponsive (rare),
you can also nuke it manually:

```bash
rm "${XDG_RUNTIME_DIR:-$HOME/.coding-agents}/vscode-session.json"
```

## Cron / systemd workarounds

The PATH-prefix mechanism only fires for processes that inherit a login
shell's environment. Cron jobs and systemd-user units skip the rc file,
so a `0 9 * * * claude --check` line in your crontab will run **outside**
the SIF.

`coding-agents doctor --scan-cron` and `coding-agents doctor --scan-systemd`
flag bare CLI invocations and propose absolute-path replacements:

```cron
# Before
0 9 * * * claude --check

# After
0 9 * * * /hpc/compgen/users/$USER/coding_agents/bin/agent-claude --check
```

For systemd-user units, point `ExecStart=` at the absolute path of
`agent-<n>` instead of the bare name.

## Pinning extension versions

VSCode auto-update can change settings keys (e.g.
`claudeCode.claudeProcessWrapper` was renamed once in 2024). The Codex
extension's bundled binary version can also drift past what the SIF was
built with, breaking the JSON-RPC handshake.

There is **no per-extension pin** in VSCode as of this writing. The
global pattern:

```bash
# 1. Download the exact .vsix you want
curl -L -o /shared/path/openai-chatgpt-26.422.30944.vsix \
  https://marketplace.visualstudio.com/_apis/public/gallery/publishers/openai/vsextensions/chatgpt/26.422.30944/vspackage

# 2. Install it
code --install-extension /shared/path/openai-chatgpt-26.422.30944.vsix

# 3. Disable global auto-update in <VSCODE_AGENT_FOLDER>/data/User/settings.json:
# {
#   "extensions.autoUpdate": false,
# }
```

Same flow works for any of the four extensions.

## Doctor checks

`coding-agents doctor` adds these checks on top of the base set:

- **Codex extension/SIF version** — warns on major.minor mismatch
  between the bundled extension binary and the SIF-pinned codex.
- **OpenCode path-shim resolves first** — warns if `which opencode`
  doesn't return our path-shim symlink (means a `~/.bashrc` change
  re-prepended someone else's bin dir; re-source the rc file).
- **CODING_AGENTS_NO_WRAP set** — surfaces the escape-hatch env var so
  it doesn't go unnoticed.

Add the scan flags for periodic crontab/systemd audits:

```bash
coding-agents doctor --scan-cron --scan-systemd
```

## Multi-IDE coexistence

If you have both `~/.vscode-server/` and `~/.cursor-server/` directories
(VSCode + a Cursor checkout sharing the same home), the resolver picks
the **first existing** path in this order:

1. `${VSCODE_AGENT_FOLDER}/data/User/settings.json` (override)
2. `~/.cursor-server/data/User/settings.json`
3. `~/.vscode-server/data/User/settings.json`
4. `~/.vscode-server-insiders/data/User/settings.json`
5. `~/.windsurf-server/data/User/settings.json`
6. `~/.vscodium-server/data/User/settings.json`

Only one settings.json is patched. If you use multiple IDEs and want
both to receive the wrapper hooks, set `VSCODE_AGENT_FOLDER` per-IDE in
your shell startup and run `coding-agents sync` from each.

## See also

- [`docs/possible_coding_agent_launch_flow_and_how_they_are_sandboxed_27_04_2026.md`](possible_coding_agent_launch_flow_and_how_they_are_sandboxed_27_04_2026.md)
  — 22-row matrix of every plausible agent-launch path and what catches each.
- [`docs/wrapping_vscode_extensions_deep_research_27_04_2026.md`](wrapping_vscode_extensions_deep_research_27_04_2026.md)
  — per-extension mechanism analysis (settings keys, IPC protocols, env contracts).
- [`docs/plans/2026-04-27-002-feat-vscode-extension-wrapping-plan.md`](plans/2026-04-27-002-feat-vscode-extension-wrapping-plan.md)
  — implementation plan and acceptance criteria.
