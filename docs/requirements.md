# Requirements: HPC Coding Agent Environment Installer

**Date:** 2026-04-10
**Status:** active
**Type:** tooling

---

## Summary

A Python CLI tool (`coding-agents`) that installs, configures, and manages multiple AI coding agents on the UMC Utrecht HPC cluster. It provides a TUI-driven installer, per-agent configuration with shared AGENTS.md and skills, optional jai sandbox preparation, VSCode extension installation, linting hooks, session recording via `entire`, and a `project-init` subcommand that bootstraps repos with project-local AGENTS.md and hooks.

**Target environment:** UMC Utrecht HPC — SLURM, no sudo, NFS home directories, no module system, Python 3.12 at `/usr/bin/python3.12`, Node 18.20.8 at `/usr/bin/node`, VSCode via Remote-SSH.

---

## CLI Interface

Invoked as `coding-agents <subcommand>`:

| Subcommand | Purpose |
|---|---|
| `install` | Full interactive TUI installer (first-time or re-run) |
| `update` | Re-run agent installations for new versions; re-sync configs |
| `project-init` | Bootstrap a project directory with AGENTS.md, hooks, agent configs |
| `sync` | Re-distribute shared config to all agent-native locations |
| `doctor` | Health check — verify agents installed, configs linked, tools available |

---

## Install Subcommand — Interactive TUI Flow

Uses Python `rich` for TUI presentation (prompts, checkboxes, panels). Each step is a screen. User can go back.

### Step 1: Installation Directory

- Default: `/hpc/compgen/users/$(whoami)/coding_agents`
- User can type a custom path
- Validate: writable, sufficient space
- Stored as `CODING_AGENT_INSTALL_DIR` in `~/.coding-agents.conf`

### Step 2: Agent Selection

**Presets** (radio buttons):
- **Core** (default): Claude Code, Codex CLI, OpenCode, Pi
- **All**: Core + Gemini CLI, Aider, Amp
- **Custom**: Opens checkbox selection

**Installation methods per agent** (verified April 2026):

| Agent | Package | Install method | Source |
|---|---|---|---|
| **Claude Code** | Native binary | `curl -fsSL https://claude.ai/install.sh \| bash` (npm deprecated per [anthropics/claude-code](https://github.com/anthropics/claude-code)) | [code.claude.com/docs/en/setup](https://code.claude.com/docs/en/setup) |
| **Codex CLI** | `@openai/codex` v0.118.0 | `npm i -g @openai/codex` or download Linux binary from [github.com/openai/codex/releases](https://github.com/openai/codex/releases) | [npmjs.com/package/@openai/codex](https://www.npmjs.com/package/@openai/codex) |
| **OpenCode** | `opencode` | `npm i -g opencode` (or binary from [github.com/anomalyco/opencode/releases](https://github.com/anomalyco/opencode/releases)) | [opencode.ai](https://opencode.ai) |
| **Pi** | `@mariozechner/pi-coding-agent` v0.66.x | `npm i -g @mariozechner/pi-coding-agent` | [npmjs.com/package/@mariozechner/pi-coding-agent](https://www.npmjs.com/package/@mariozechner/pi-coding-agent) |
| **Gemini CLI** | `@anthropic-ai/gemini-cli` [VERIFY] or via `npx @anthropic-ai/gemini-cli` | `npm i -g gemini-cli` or via Google's install script | [github.com/google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli) |
| **Aider** | `aider-chat` | `uv pip install aider-chat` into tools venv | [aider.chat](https://aider.chat), [github.com/Aider-AI/aider](https://github.com/Aider-AI/aider) |
| **Amp** | `@sourcegraph/amp` | `npm i -g @sourcegraph/amp` | [ampcode.com](https://ampcode.com), [npmjs.com/package/@sourcegraph/amp](https://www.npmjs.com/package/@sourcegraph/amp) |

**npm agents** installed into `$CODING_AGENT_INSTALL_DIR/node_modules/.bin/` using a local `package.json` with `--prefix`.
**Claude Code** installed via its native installer script with `CLAUDE_CODE_INSTALL_DIR=$CODING_AGENT_INSTALL_DIR/bin` (or equivalent env var — verify).
**pip agents** (Aider) installed into `$CODING_AGENT_INSTALL_DIR/tools/.venv/`.

All binaries are PATH-accessible via the shell integration block (Step 11).

### Step 3: VSCode Extensions

Prompt: "Install VSCode extensions for selected agents?"

Default selection: Claude Code, Codex, OpenCode, Pi

**Installation method:** `code --install-extension <ext-id>` (works via Remote-SSH — the `code` CLI is available on the HPC when the VSCode server is running)

| Agent | Extension ID | Marketplace |
|---|---|---|
| Claude Code | `anthropic.claude-code` | [marketplace.visualstudio.com](https://marketplace.visualstudio.com/items?itemName=anthropic.claude-code) |
| Codex | `openai.chatgpt-codex` | [marketplace.visualstudio.com](https://marketplace.visualstudio.com/items?itemName=openai.chatgpt-codex) [VERIFY exact ID] |
| OpenCode | `sst-dev.opencode` | [marketplace.visualstudio.com](https://marketplace.visualstudio.com/items?itemName=sst-dev.opencode) |
| Pi | `pi0.pi-vscode` | [marketplace.visualstudio.com](https://marketplace.visualstudio.com/items?itemName=pi0.pi-vscode) |

**Behavior:**
- First try `code --install-extension <id>`. If `code` is not on PATH (user not in a Remote-SSH session), write the extension IDs to `$CODING_AGENT_INSTALL_DIR/vscode-recommendations/extensions.json` and print instructions for manual install.
- Also generate a `.vscode/extensions.json` recommendations file for `project-init`.

### Step 4: Pi Extensions

If Pi selected in Step 2, install default extensions (inform user, not interactive):

| Extension | Source | Install method |
|---|---|---|
| `pi-ask-user` | [npmjs.com/package/pi-ask-user](https://www.npmjs.com/package/pi-ask-user) | `npm i -g pi-ask-user` |
| `pi-prompt-template-model` | [github.com/nicobailon/pi-prompt-template-model](https://github.com/nicobailon/pi-prompt-template-model) | `npm i -g pi-prompt-template-model` or clone to `~/.pi/agent/extensions/` |
| `pi-subagents` | [github.com/nicobailon/pi-subagents](https://github.com/nicobailon/pi-subagents/) | `npm i -g pi-subagents` or clone to `~/.pi/agent/extensions/` |

Display: "More Pi extensions: https://www.npmjs.com/search?q=keywords:pi-package and https://discord.gg/pi-coding-agent"

### Step 5: Agent Tools

Installed into `$CODING_AGENT_INSTALL_DIR/tools/`:

| Tool | Source | Install method | Purpose |
|---|---|---|---|
| **crawl4ai** | [docs.crawl4ai.com](https://docs.crawl4ai.com/core/installation/) | `uv pip install crawl4ai` into tools venv | Web crawling for agents |
| **agent-browser** | [github.com/vercel-labs/agent-browser](https://github.com/vercel-labs/agent-browser) | `npm install agent-browser` into tools node_modules | Headless browser automation |

Note: agent-browser may require Chromium/Playwright. If unavailable on HPC, skip with warning and document manual setup.

### Step 6: jai Sandbox Configuration

Prompt: "Prepare jai sandbox configs for terminal agents? (jai must be installed system-wide — configs are inactive until jai is available)"

- Default: All installed agents
- Mode: **Bare** (empty home dir, runs as your user — required for NFS per [jai docs](https://jai.scs.stanford.edu/modes.html))

What this creates in `$CODING_AGENT_INSTALL_DIR/jai/`:

**`.defaults`** — baseline security policy:
```ini
# Mask sensitive directories
mask .ssh
mask .gnupg
mask .aws
mask .docker
mask .kube
# Filter sensitive environment variables
unsetenv *_TOKEN
unsetenv *_KEY
unsetenv *_SECRET
unsetenv *_PASSWORD
unsetenv AWS_*
```

**Per-agent `.conf` files** — each grants only needed directories:
```ini
# claude.conf
conf .defaults
mode bare
dir .claude
rdir? ${PWD}/.git
setenv ANTHROPIC_API_KEY

# codex.conf
conf .defaults
mode bare
dir .codex
setenv OPENAI_API_KEY

# pi.conf
conf .defaults
mode bare
dir .pi
setenv ANTHROPIC_API_KEY
setenv OPENAI_API_KEY
setenv GOOGLE_API_KEY
```

**Per-agent wrapper scripts** in `$CODING_AGENT_INSTALL_DIR/bin/jai-<agent>`:
```bash
#!/bin/bash
if command -v jai &>/dev/null; then
    exec jai -C "$CODING_AGENT_INSTALL_DIR/jai/<agent>.conf" <agent-binary> "$@"
else
    echo "⚠️  jai not available — running <agent> without sandbox"
    exec <agent-binary> "$@"
fi
```

Reference: [jai man page](https://github.com/stanford-scs/jai/blob/master/jai.1.md), [jai security model](https://jai.scs.stanford.edu/security.html), [jai v0.3 release](https://github.com/stanford-scs/jai/releases)

Second prompt: "Prepare jai sandboxing for VSCode extension agents?"
- Default: None
- If selected: document how to configure VSCode tasks.json to invoke agents through jai wrappers

### Step 7: Skills Installation

Default selection (all checked):

| Skill | Source | Install method |
|---|---|---|
| **compound-engineering** | [github.com/EveryInc/compound-engineering-plugin](https://github.com/EveryInc/compound-engineering-plugin/tree/main) | `git clone` into `$INSTALL_DIR/skills/` |
| **scientific-agent-skills** | [github.com/K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills) | `git clone` into `$INSTALL_DIR/skills/` |
| **crawl4ai skill** | [docs.crawl4ai.com/assets/crawl4ai-skill.zip](https://docs.crawl4ai.com/assets/crawl4ai-skill.zip) | Download and extract into `$INSTALL_DIR/skills/` |
| **hpc-cluster** | Bundled (from uploaded `hpc-cluster.skill`) | Extract into `$INSTALL_DIR/skills/` |

Skills are symlinked to each agent's native skill location during `sync`:
- Claude Code: `~/.claude/skills/<name>/SKILL.md` (per [code.claude.com/docs](https://code.claude.com/docs/en/sub-agents))
- Codex CLI: `~/.codex/skills/<name>/SKILL.md` (per [developers.openai.com/codex/config-reference](https://developers.openai.com/codex/config-reference))
- Pi: `~/.pi/agent/skills/<name>/SKILL.md` (per [pi-mono/packages/coding-agent/docs/skills.md](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/skills.md))
- OpenCode: `~/.config/opencode/skills/<name>/SKILL.md` (per [opencode.ai/docs/config](https://opencode.ai/docs/config/))
- Amp: `~/.config/amp/skills/<name>/SKILL.md` (per [ampcode.com/manual](https://ampcode.com/manual))

### Step 8: Linting & Code Quality Tools

Default: Yes

**Python tools** via `uv pip install` into `$INSTALL_DIR/tools/.venv/`:

| Tool | PyPI | Purpose |
|---|---|---|
| ruff | [github.com/astral-sh/ruff](https://github.com/astral-sh/ruff) | Python linter + formatter |
| vulture | [github.com/jendrikseipp/vulture](https://github.com/jendrikseipp/vulture) | Dead code detection |
| pyright | [github.com/microsoft/pyright](https://github.com/microsoft/pyright) | Python type checking |
| yamllint | [github.com/adrienverge/yamllint](https://github.com/adrienverge/yamllint) | YAML linting |

**Node tools** via `npm install` into `$INSTALL_DIR/tools/node_modules/`:

| Tool | npm | Purpose |
|---|---|---|
| @biomejs/biome | [biomejs.dev](https://biomejs.dev/guides/getting-started/) | JSON linting |

**Binary tool** (static download):

| Tool | Source | Purpose |
|---|---|---|
| shellcheck | [github.com/koalaman/shellcheck/releases](https://github.com/koalaman/shellcheck) — download `shellcheck-v0.10.0.linux.x86_64.tar.xz` | Bash/shell linting |

### Step 9: Hooks Installation

Default: all checked.

**SessionStart hooks:**

1. **AGENTS.md check** (`on_start_agents_md_check.py`):
   - If CWD has no `AGENTS.md` (or `CLAUDE.md`), create one from `PROJECT_LOCAL_AGENTS_TEMPLATE.md`
   - Non-blocking — informs user it was created

2. **Cognitive offloading reminder** (`on_start_cognitive_reminder.py`):
   - Displays a brief panel:
     > 🧠 **Remember: the thinking is the work.**
     > For best results, use the compound-engineering workflow: /ce:brainstorm → /ce:plan → /ce:work → /ce:review
     > AI agents augment your understanding — don't let them replace it.
     > Read more: https://ergosphere.blog/posts/the-machines-are-fine/
   - Non-blocking, informational only

3. **Git repo check** (`on_start_git_check.py`, only if `entire` installed):
   - If no `.git/` in CWD, prompt: "No git repo found. Initialize one for session recording? [y/N]"

**Stop hooks (non-blocking — surfaces results to agent as context):**

4. **Lint runner** (`on_stop_lint_runner.py`):
   - Detects changed files since session start (via git diff or filesystem timestamps)
   - Runs appropriate linter per file extension:
     - `.py` → ruff check, vulture, pyright
     - `.yml`/`.yaml` → yamllint
     - `.json` → biome check
     - `.sh`/`.bash` → shellcheck
   - Collects all warnings/errors, returns as agent context
   - Non-blocking: agent sees results but is not stopped

5. **HPC structure validator** (`on_stop_hpc_validator.py`):
   - Reworked from uploaded `hpc-folder-structure-validator.py`
   - Changes: remove all "Claude Code"-specific wording → agent-neutral ("The coding agent created files outside...")
   - Same path validation logic for `/hpc/compgen/projects/`

**Permission deny rules** (applied to agents that support them):

```json
{
  "deny": [
    "Read(./.env)",
    "Read(./.env.*)",
    "Read(./secrets/**)",
    "Read(./config/credentials.json)",
    "Read(./.entire/metadata/**)",
    "Read(./build)"
  ]
}
```

Wired into:
- Claude Code: `permissions.deny` array in `settings.json` (per [code.claude.com/docs/en/settings](https://code.claude.com/docs/en/changelog))
- Codex CLI: Starlark `prefix_rule(pattern=["cat", ".env"], decision="forbidden")` (per [developers.openai.com/codex/config-reference](https://developers.openai.com/codex/config-reference))
- OpenCode: `permission` config (per [opencode.ai/docs/config](https://opencode.ai/docs/config/))
- Pi: No native deny rules (document limitation — recommend using jai sandbox instead)
- Aider/Amp: No native deny rules (document limitation)

### Step 10: Entire CLI (Session Recording)

Default: Yes

| Component | Source | Install |
|---|---|---|
| entire CLI | [github.com/entireio/cli](https://github.com/entireio/cli) | `npm i -g entire` into `$INSTALL_DIR/node_modules/.bin/` |

Configuration:
- Telemetry **off** by default: set `ENTIRE_TELEMETRY=off` in shell integration block (or via `entire config set telemetry false` — verify exact flag)
- The git hook is configured via `entire init` in each project (done by `project-init`)
- The SessionStart hook (Step 9.3) handles "no git repo" case

### Step 11: Shell Integration

Appends a guarded block to `~/.bashrc`:

```bash
# >>> coding-agents >>>
export CODING_AGENT_INSTALL_DIR="/hpc/compgen/users/dstoker/coding_agents"
export PATH="$CODING_AGENT_INSTALL_DIR/bin:$CODING_AGENT_INSTALL_DIR/node_modules/.bin:$PATH"
# Activate tools venv for linters
export CODING_AGENTS_TOOLS_VENV="$CODING_AGENT_INSTALL_DIR/tools/.venv"
# jai config location (prepared but inactive until jai is system-installed)
export JAI_CONFIG_DIR="$CODING_AGENT_INSTALL_DIR/jai"
# Entire telemetry off
export ENTIRE_TELEMETRY=off
# <<< coding-agents <<<
```

Guarded by marker comments — re-runs replace rather than duplicate.

---

## project-init Subcommand

`coding-agents project-init [directory]`

Bootstraps a project directory (default: cwd) with:

1. **AGENTS.md** from `PROJECT_LOCAL_AGENTS_TEMPLATE.md` (see below)
2. **Symlinks**: `CLAUDE.md -> AGENTS.md`, `GEMINI.md -> AGENTS.md`
3. **Per-agent project configs** for installed agents:
   - `.claude/settings.json` — hooks wired, deny rules applied
   - `.codex/config.toml` — stub with project-specific overrides
   - `opencode.json` — stub
   - `.pi/settings.json` — stub
4. **`.gitignore` additions**: `.claude/`, `.codex/`, `.pi/`, `.opencode/`, `.gemini/`, `.entire/`
5. If `entire` installed and no `.git/`: offer to `git init`, then `entire init`
6. **`.vscode/extensions.json`** with recommended agent extensions

---

## PROJECT_LOCAL_AGENTS_TEMPLATE.md

```markdown
# Project: [PROJECT_NAME]

> This file guides AI coding agents working in this repository.
> It is read by Claude Code, Codex CLI, OpenCode, Pi, Gemini CLI, Amp, and others.

## 🧠 Before You Start

AI agents are powerful tools, but **the thinking is the work**. Use agents to
augment your understanding, not replace it. If you find yourself accepting code
you don't fully understand, pause and work through it manually first.

Read: https://ergosphere.blog/posts/the-machines-are-fine/

## Recommended Workflow

For substantial work (new features, refactors, bug investigations), follow the
compound-engineering loop for best results:

1. **`/ce:brainstorm`** — Explore the problem space, produce a requirements doc
2. **`/ce:plan`** — Create a technical spec with acceptance criteria
3. **`/ce:work`** — Implement with tests, referencing the plan
4. **`/ce:review`** — Adversarial review of the implementation

For small changes (typos, config tweaks, one-liner fixes), skip directly to implementation.

## Environment

- **Platform**: UMC Utrecht HPC cluster (SLURM-based)
- **Submit jobs**: Use `srun` for interactive, `sbatch` for batch
- **Project data**: `/hpc/compgen/projects/<project>/`
- **Your analysis output**: `<subproject>/analysis/$(whoami)/`
- **No sudo** available — all tools are user-space installed

## Code Conventions

- [Language/framework — fill in]
- [Testing approach — fill in]
- [Style guide — fill in]

## Directory Structure

Follow the mandatory HPC project structure:
```
/hpc/compgen/projects/<project>/
    <subproject>/
        raw/           # Input/reference data (read-only in practice)
        analysis/
            <username>/ # Your analysis outputs go here
```

## Agent Configuration

Agent configs for this project live in `.claude/`, `.codex/`, `.pi/`, and `opencode.json`.
Global skills and hooks are managed by `coding-agents sync`.
```

---

## Directory Structure

```
$CODING_AGENT_INSTALL_DIR/
├── bin/                          # CLI + wrapper scripts
│   ├── coding-agents             # Main CLI entry point (Python)
│   ├── jai-claude                # jai wrapper (noop if jai unavailable)
│   ├── jai-codex
│   ├── jai-opencode
│   ├── jai-pi
│   ├── jai-gemini
│   ├── jai-aider
│   └── jai-amp
├── config/
│   ├── AGENTS.md                 # Global user-level AGENTS.md
│   ├── coding-agents.conf        # Installation state (selections, paths)
│   ├── mcp/
│   │   ├── servers.json          # Canonical MCP definitions
│   │   └── convert-mcp.js        # Format converter (from deep-research report)
│   └── templates/
│       ├── PROJECT_LOCAL_AGENTS_TEMPLATE.md
│       └── hooks/                # Hook source templates
├── skills/                       # Shared skill packs
│   ├── compound-engineering/     # git clone from EveryInc
│   ├── scientific-agent-skills/  # git clone from K-Dense-AI
│   ├── crawl4ai/                 # Extracted from zip
│   └── hpc-cluster/              # Extracted from uploaded .skill
├── hooks/                        # Hook implementations (agent-neutral Python)
│   ├── on_start_agents_md_check.py
│   ├── on_start_cognitive_reminder.py
│   ├── on_start_git_check.py
│   ├── on_stop_lint_runner.py
│   ├── on_stop_hpc_validator.py
│   └── deny_rules.json
├── jai/                          # jai configs (inactive until jai available)
│   ├── .defaults
│   ├── claude.conf
│   ├── codex.conf
│   ├── opencode.conf
│   ├── pi.conf
│   ├── gemini.conf
│   ├── aider.conf
│   └── amp.conf
├── tools/
│   ├── .venv/                    # uv venv: ruff, vulture, pyright, yamllint, crawl4ai, aider
│   ├── node_modules/             # biome, agent-browser
│   └── bin/
│       └── shellcheck            # Static binary download
├── node_modules/                 # Agent npm packages
│   └── .bin/                     # codex, opencode, pi, gemini, amp
├── vscode-recommendations/       # Fallback if `code` CLI not available
│   └── extensions.json
└── logs/                         # Install/sync/doctor logs
```

---

## sync Subcommand

`coding-agents sync`

Distributes config from `$INSTALL_DIR/config/` and `$INSTALL_DIR/skills/` to each agent's native location via **symlinks**:

| Source | → Target(s) |
|---|---|
| `config/AGENTS.md` | `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.config/opencode/AGENTS.md`, `~/.pi/agent/AGENTS.md`, `~/.gemini/GEMINI.md`, `~/.config/amp/AGENTS.md` |
| `skills/<name>/` | Each agent's skill dir (see Step 7 table) |
| `hooks/*` | Wired into agent-native hook configs |
| `hooks/deny_rules.json` | Written to agent permission configs |
| `jai/*.conf` | Symlinked to `~/.jai/` if jai available |
| `config/mcp/servers.json` | Converted via `convert-mcp.js` to each agent format |

Idempotent — safe to re-run. Logs to `$INSTALL_DIR/logs/sync.log`.

---

## doctor Subcommand

Checks (color-coded ✅/⚠️/❌):

- Python 3 available
- Node.js available and version ≥ 18
- uv available
- Each selected agent binary exists and runs `--version`
- Each agent's config directory has expected symlinks
- Skills symlinked correctly
- Hooks wired correctly
- Linting tools available in tools venv
- shellcheck binary available
- jai status: available / not installed / configs prepared
- entire status: installed / telemetry off / git hook present
- Shell PATH includes `$INSTALL_DIR/bin`
- VSCode extensions installed (via `code --list-extensions`)

Output: pass/warn/fail per check, with fix command for each failure.

---

## update Subcommand

- Claude Code: `claude update` (native binary self-updates)
- npm agents: `npm update -g @openai/codex @mariozechner/pi-coding-agent opencode @sourcegraph/amp` (with `--prefix`)
- pip agents: `uv pip install --upgrade aider-chat ruff vulture pyright yamllint crawl4ai`
- Skills from git: `git -C $INSTALL_DIR/skills/<name> pull`
- shellcheck: re-download latest release binary
- Re-runs `sync` afterward
- Shows summary of what changed

---

## Non-Functional Requirements

- **No sudo required** — everything user-space
- **NFS-safe** — symlinks only, no hardlinks, no file locking
- **Idempotent** — re-running install/sync is safe
- **Offline-tolerant** — skip unavailable fetches, report what failed
- **Shell-agnostic** — bash primary, zsh secondary
- **Config persistence** — `~/.coding-agents.conf` stores install dir; `$INSTALL_DIR/config/coding-agents.conf` stores all selections
- **Re-runnable** — running `install` again reads previous selections as defaults

---

## Items to Verify During Build

1. **Claude Code install script** — verify `curl -fsSL https://claude.ai/install.sh | bash` supports custom install dir via env var, or whether we need to install to default location and symlink
2. **Gemini CLI package name** — `@anthropic-ai/gemini-cli` is wrong; need to find correct npm package or install method from [github.com/google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli)
3. **Codex VSCode extension ID** — verify `openai.chatgpt-codex` is correct (may be `openai.codex`)
4. **agent-browser on HPC** — may require Chromium binary not available; make optional with clear warning
5. **entire telemetry opt-out** — verify exact env var or config command
6. **Pi extensions install method** — verify whether `npm i -g pi-ask-user` works or if they need to be cloned into `~/.pi/agent/extensions/`
7. **shellcheck static binary** — verify `shellcheck-v0.10.0.linux.x86_64.tar.xz` works on the HPC (glibc version)
