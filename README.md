# coding-agents

Cross-agent configuration package for the UMC Utrecht HPC cluster. Provides a
unified installer, shared configuration, skills, hooks, and sandbox preparation
for multiple AI coding agents.

## Supported Agents

| Agent | CLI | VSCode Extension | Install Method |
|---|---|---|---|
| **Claude Code** | `claude` | `anthropic.claude-code` | Native binary (`curl -fsSL https://claude.ai/install.sh \| bash`) |
| **Codex CLI** | `codex` | `openai.chatgpt` | `npm i -g @openai/codex` |
| **OpenCode** | `opencode` | `sst-dev.opencode` | `npm i -g opencode-ai` |
| **Pi** | `pi` | `pi0.pi-vscode` | `npm i -g @mariozechner/pi-coding-agent` |
| **Gemini CLI** | `gemini` | — | `npm i -g @google/gemini-cli` |
| **Amp** | `amp` | — | `npm i -g @sourcegraph/amp` |

## Prerequisites

`coding-agents` is a thin orchestrator — it does not bootstrap your language
runtimes. The **must-haves** below need to be present before you can install
the package. Don't try to eyeball whether you have them: the repo ships a
diagnostic script that checks everything and prints a copy-paste install
command for anything missing (see Quick Start, step 2).

| Must-have | What it's for |
|---|---|
| `git` | Cloning this repo + the git-hosted skills (compound-engineering, scientific-agent-skills, autoresearch) |
| `curl` | Claude Code's native installer; also used by `uv`, `entire`, etc. |
| `bash` | Running the installer and its hooks/wrappers |
| `unzip`, `tar` | Extracting the `hpc-cluster.skill` archive and various tool tarballs |
| Node.js + `npm` | **HPC mode**: only needed for host-side tools (`@biomejs/biome`, `agent-browser`, `claude-statusbar`). Codex, OpenCode, Pi run from the SIF and don't require host node. **Local mode**: needed for every npm-installed agent. |
| Python ≥ 3.12 | Running the `coding-agents` CLI itself (enforced by `pyproject.toml`) |
| `uv` | Installing this package and managing the tools venv (ruff, vulture, pyright, yamllint, crawl4ai) + `claude-statusbar` |

Things the installer *does* handle for you once the above are present: the
Claude Code binary (`curl … | bash`), Codex/OpenCode/Pi (already baked into
the SIF — no install step), the Python tools venv, `@biomejs/biome`,
`agent-browser`, `shellcheck`, the `entire` CLI, and `claude-statusbar`.

### What is already there on the UMC Utrecht HPC submit nodes

Verified on `hpcs05`/`hpcs06` (RHEL 8.10) by `scripts/hpc_prereq_check.sh`:

- **System-wide (nothing to install)**: `git`, `bash`, `zsh`, `curl`,
  `node`/`npm` (Node.js 18 in `/usr/bin`), `unzip`, `tar`.
- **Not installed system-wide; install in your home directory** (no admin
  rights needed): `uv` and a Python ≥ 3.12 interpreter.
- **Network**: outbound HTTPS to `claude.ai`, `registry.npmjs.org`,
  `astral.sh`, `github.com`, and `entire.io` all work from submit nodes;
  no proxy configuration needed.
- **No Lmod `module load` step is required** for any of the prereqs on
  these nodes.

The exact install commands for `uv` and Python 3.12 are printed by the
diagnostic script — see Quick Start step 2. Don't copy-paste them from
someone else's shell; the script tells you which recipe is right for your
environment.

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/DieStok/coding_agent_installer_ridder_lab.git
cd coding_agent_installer_ridder_lab

# 2. Check prerequisites (non-destructive; exits non-zero if anything's missing)
bash scripts/hpc_prereq_check.sh
#    For each must-have marked [FAIL], the script prints the exact command
#    to install it (e.g. uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`,
#    Python 3.12: `uv python install 3.12`). Run those, open a fresh shell
#    (or `source ~/.bashrc`), and re-run the script until it exits 0.

# 3. Install the coding-agents CLI itself
#    `uv tool install .` puts it in an isolated env and puts `coding-agents`
#    on your PATH via ~/.local/bin. (If this is your first `uv tool` install,
#    run `uv tool update-shell` afterwards and open a fresh shell.)
uv tool install .

# 4. Run the interactive installer
#    default → UMC Utrecht HPC cluster
#    --local → laptop / workstation (skips jai, HPC-only skills & hooks)
coding-agents install           # HPC mode
coding-agents install --local   # local mode

# 5. (HPC) initialize a project directory
cd /hpc/compgen/projects/my-project/my-subproject
coding-agents project-init

# 6. Verify
coding-agents doctor

# Re-sync after config changes
coding-agents sync

# Update all agents
coding-agents update

# Clean removal
coding-agents uninstall
```

Every subcommand accepts `--dry-run` to walk through the full plan without
touching anything (implies `--debug`, writes a log under
`$INSTALL_DIR/logs/`).

## Subcommands

| Command | Description |
|---|---|
| `install [--local]` | Interactive Textual TUI installer (7 steps, back-navigation) |
| `update` | Update all agents + tools to latest, re-sync configs |
| `project-init [path]` | Bootstrap a project directory with AGENTS.md, hooks, agent configs |
| `sync` | Re-distribute shared config to all agent-native locations |
| `doctor [--scan-cron] [--scan-systemd]` | Health check; optional scans surface bare CLI invocations in user crontabs / systemd-user units |
| `vscode-reset` | Clear the cached VSCode SLURM session jobid (best-effort `scancel`); use after a session goes stale |
| `uninstall` | Clean removal of all installed components |

### VSCode extension wrapping

When at least one of Claude Code / ChatGPT-Codex / OpenCode v2 / Pi is
selected during install (HPC mode), the installer also wires the
extensions' "spawn" hooks into our SIF wrapper:

- **Claude / Codex / Pi**: a per-extension key in
  `~/.vscode-server/data/User/settings.json` (or `.cursor-server/...`)
  points at `<install_dir>/bin/agent-<n>-vscode`.
- **OpenCode v2** (no settings hook): a `<install_dir>/bin/path-shim/`
  dir is prepended to `$PATH` via a second shell-rc block, plus the
  `terminal.integrated.env.linux.PATH` setting as defence-in-depth.
- **`agent-vscode` helper** copied to `<install_dir>/bin/` allocates a
  per-VSCode-session SLURM job (`salloc --no-shell` at first spawn,
  cached under `flock` at `${XDG_RUNTIME_DIR:-$HOME/.coding-agents}/vscode-session.json`)
  and dispatches every subsequent spawn via `srun --jobid=<id>` into the
  existing terminal `agent-<n>` wrapper. The session is keyed by
  `VSCODE_GIT_IPC_HANDLE` (or `VSCODE_PID`, falling back to ppid) so a
  worker restart inside the extension host doesn't re-allocate a job.
- Set `CODING_AGENTS_NO_WRAP=1` to bypass the **wrapper template** (cwd
  policy, audit-log JSONL, lab bind tables, SLURM auto-srun) for triage —
  the agent **still runs inside the SIF** via direct `apptainer exec`,
  so the deny rules and `--containall` isolation are preserved. Requires
  `apptainer` on PATH (lab cluster: only available inside `srun --pty`).
  `doctor` surfaces this with a warn row when set.
- Run `coding-agents vscode-reset` if a session goes wrong (e.g. after
  VSCode restart while a salloc was retrying); next spawn re-allocates fresh.

## Building the SIF (lab admin)

The Apptainer SIF that the wrappers route through is built from
[`src/coding_agents/bundled/coding_agent_hpc.def`](src/coding_agents/bundled/coding_agent_hpc.def).
The full build runbook (Mac/Linux/WSL via Docker, smoke tests, SHA
sidecar, atomic-swap of `current.sif` on the cluster) lives at
[`src/coding_agents/bundled/sif/README.md`](src/coding_agents/bundled/sif/README.md).

The `%post` step bakes Node 20 + Codex/OpenCode/Pi/Claude + the four
lab-default Pi extensions (`pi-ask-user`, `pi-subagents`,
`pi-web-access`, `pi-mcp-adapter`) and snapshots
`/opt/pi-default-settings.json` so the wrapper template's first-run
hook can seed each user's `~/.pi/agent/settings.json` on their first
wrapped Pi message. After upload, `coding-agents doctor` verifies the
SIF labels + the Pi defaults file with two cheap probes.

## Sandboxing reference

Wondering when the Apptainer sandbox actually applies and when it doesn't? See
the dedicated reference:

**[`docs/possible_coding_agent_launch_flow_and_how_they_are_sandboxed_27_04_2026.md`](docs/possible_coding_agent_launch_flow_and_how_they_are_sandboxed_27_04_2026.md)**

It enumerates every plausible way to start an agent (sidebar click, integrated
terminal, plain SSH terminal, `sbatch`, cron, systemd, debug adapter, …) and
walks through what catches each — settings.json hook, shell-rc PATH-prefix,
direct wrapper invocation, or one of the documented gaps (cron / systemd /
hardcoded paths in third-party extensions). Every case has a worked example
with process tree and recovery hints.

If you're integrating the package into automation that runs outside an
interactive shell (cron, systemd, CI), read §21 / §22 / §17 first to avoid a
silent un-sandboxed invocation.

## Installer Walkthrough

`coding-agents install` is a Textual TUI with six screens (plus a
post-install next-steps screen). Every step has a back button; nothing
is written to disk until the final "Install" press. Defaults are tuned
for the UMC Utrecht HPC cluster in HPC mode; `--local` drops everything
HPC-specific automatically. Pass `--developer` to expand Steps 4 and 5
from info-only summaries to full multi-select pickers.

### Step 1 — Installation Directory

Single path field. Holds the per-agent wrapper scripts in `bin/`, the
linter/biome workspace in `tools/`, skills, hooks, and merged agent
configs. Agents themselves run from the SIF — no host `node_modules/`
for codex/opencode/pi.

- **Default (HPC)**: `/hpc/compgen/users/$USER/coding_agents` when
  `/hpc/compgen/users` exists, else `~/coding_agents`.
- **Default (local)**: `~/coding_agents`.
- **HPC rule**: paths over 100 characters are rejected (Linux shebang limit).
- If existing agent installations (`~/.claude`, `~/.codex`, …) are detected, a
  banner shows what will be backed up. Existing hooks, MCP servers, and deny
  rules are preserved and merged, never overwritten.

### Step 2 — Agent Selection

Radio choice between three presets; pick "Custom" to hand-pick agents.

- **Core (default)**: Claude Code, Codex CLI, OpenCode, Pi — the four with
  the strongest skill/hook support.
- **All**: Core + Gemini CLI + Amp.
- **Custom**: multi-select any subset of the six agents above.
- At least one agent must be selected.

### Step 3 — VSCode Extensions

Info-only on HPC; the user installs extensions in their *local* VSCode
and they ride along over Remote-SSH automatically. `--local` mode adds a
toggle for `code --install-extension` when the `code` binary is on PATH.

- A `vscode-extensions.json` recommendation file is always written into
  `<install_dir>/` for manual import.
- Extensions: `anthropic.claude-code`, `openai.chatgpt`,
  `sst-dev.opencode`, `pi0.pi-vscode` (Gemini and Amp don't publish
  one).

### Step 4 — Tools & Supporting Software

Info-only summary by default; `--developer` shows the multi-select picker.

The lab default set is **`linters`** only:

| Item | Installs into |
|---|---|
| Linters: ruff, vulture, pyright, yamllint | `tools/.venv/` (via `uv pip install`) |
| biome | `tools/node_modules/@biomejs/biome` |
| shellcheck v0.11.0 | `tools/bin/shellcheck` (static binary) |

In `--developer` mode you can additionally toggle the `entire` CLI
(session recording, system-wide install symlinked into
`<install_dir>/bin/`).

Pi's four lab-default extensions (`pi-ask-user`, `pi-subagents`,
`pi-web-access`, `pi-mcp-adapter`) are **not** installed by the host —
they're baked into the SIF and seeded into your
`~/.pi/agent/settings.json` on the first wrapped Pi message via the
wrapper template's first-run hook. Nothing to toggle here for that.

### Step 5 — Skills & Hooks

Info-only summary by default; `--developer` shows the two multi-select
lists. `--local` silently drops the HPC-only entries.

**Skills** (distributed to every compatible agent via symlinks during
`coding-agents sync`):

| Skill | Default (HPC) | Default (local) | Source |
|---|---|---|---|
| `compound-engineering` | on | on | git clone |
| `scientific-agent-skills` | on | on | git clone |
| `autoresearch` | on | on | git clone |
| `hpc-cluster` | on | **skipped** | HPC shared path (`.skill` zip) |

**Hooks** (agent lifecycle scripts, wired into Claude Code via
`~/.claude/settings.json` when Claude is selected):

| Hook | Default (HPC) | Default (local) | When |
|---|---|---|---|
| `agents_md_check` (create AGENTS.md if missing) | on | on | SessionStart |
| `cognitive_reminder` (compound-engineering prompt) | on | on | SessionStart |
| `git_check` (warn if no git repo for `entire`) | on | on | SessionStart |
| `lint_runner` (ruff, vulture, pyright, yamllint, biome, shellcheck) | on | on | Stop |
| `hpc_validator` (directory convention check) | on | **skipped** | Stop |

### Step 6 — Review & Install

Summary of all selections. Press **Install** to execute — the TUI
streams progress into a live log (and a "verbose output" pane for
subprocess stdout/stderr). Nothing on disk until this point.

When the install completes, a final next-steps screen lists the
post-install commands (`source ~/.bashrc`, `coding-agents sync`,
`coding-agents doctor`, VSCode extension links). Selections are
persisted to `~/.coding-agents.json` so re-running `install`
pre-populates the screens with your previous answers.

## Package Structure

```
├── pyproject.toml
├── src/coding_agents/
│   ├── cli.py                  # Typer entrypoint
│   ├── agents.py               # Agent registry (data-driven, no class hierarchy)
│   ├── config.py               # ~/.coding-agents.json management
│   ├── convert_mcp.py          # MCP format converter (pure Python, no Node)
│   ├── utils.py                # NFS-safe symlinks, subprocess, shell integration
│   ├── installer/
│   │   ├── tui.py              # Textual App with screen stack
│   │   ├── state.py            # InstallerState dataclass
│   │   ├── executor.py         # Installation execution logic
│   │   └── screens/            # 6 TUI screens + post-install next-steps
│   └── commands/
│       ├── sync.py             # Config distribution
│       ├── doctor.py           # Health checks
│       ├── update.py           # Update all components
│       ├── project_init.py     # Project bootstrapping
│       └── uninstall.py        # Clean removal
├── bundled/
│   ├── hooks/                  # 5 hook scripts + deny_rules.json
│   ├── jai/                    # .defaults + 6 agent .conf files
│   ├── config/                 # AGENTS.md, templates, MCP example
│   └── skills/                 # crawl4ai (bundled skills)
├── dist/                       # Distributable artifacts (hpc-cluster.skill)
├── scripts/                    # Packaging helpers (package_skill.py)
└── tests/
```

## Hooks

All hooks are agent-neutral Python scripts.

### SessionStart hooks
- **AGENTS.md check**: Creates project AGENTS.md from template if missing
- **Cognitive offloading reminder**: Reminds user about compound-engineering workflow
- **Git repo check**: Warns if no git repo (needed for `entire` session recording)

### Stop hooks (non-blocking)
- **Lint runner**: Runs ruff, vulture, pyright, yamllint, biome, shellcheck on changed files
- **HPC structure validator**: Validates files follow HPC directory conventions (scoped to CWD)

### Permission deny rules
Blocks agent access to `.env`, `.env.*`, `secrets/`, `config/credentials.json`, `.entire/metadata/`, `build/`

## jai Sandbox

Configs prepared for [jai](https://jai.scs.stanford.edu/) (Stanford's lightweight Linux sandbox).
All configs use **bare mode** (required for NFS filesystems on HPC).

jai must be installed system-wide by a sysadmin. Until then, wrapper scripts
run agents without sandboxing and print a warning.

## Skills

Skills are shared across agents via symlinks during `coding-agents sync`:

- **compound-engineering**: Brainstorm/plan/work/review development workflow
  (installed from https://github.com/EveryInc/compound-engineering-plugin)
- **scientific-agent-skills**: Research-oriented agent skills
  (installed from https://github.com/K-Dense-AI/scientific-agent-skills)
- **autoresearch**: Autonomous improvement engine with 10 commands
  (installed from https://github.com/uditgoenka/autoresearch)
- **crawl4ai**: Web crawling and content extraction (bundled)
- **hpc-cluster**: UMC Utrecht HPC cluster reference — SLURM, GPUs, storage.
  **Not shipped with the package.** In `--hpc` mode the installer extracts it from
  `/hpc/compgen/projects/ollama/hpc_skill/analysis/dstoker/hpc-cluster.skill` on the
  shared filesystem. See `dist/README.md` for how to (re)upload the archive and set
  world-readable permissions. Skipped entirely in `--local` mode.

## NFS Safety

The installer uses NFS-safe operations throughout:
- `--no-package-lock` for npm installs
- Local npm/uv caches per user
- Atomic symlinks via temp-file-then-rename
- Retry on stale file handles (errno 116)
- Shebang length validation

## References

- AGENTS.md spec: https://agents.md/
- jai sandbox: https://jai.scs.stanford.edu/
- Compound engineering: https://github.com/EveryInc/compound-engineering-plugin
- Entire CLI: https://github.com/entireio/cli
- Cognitive offloading essay: https://ergosphere.blog/posts/the-machines-are-fine/
