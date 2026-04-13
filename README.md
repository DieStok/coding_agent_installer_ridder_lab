# coding-agents

Cross-agent configuration package for the UMC Utrecht HPC cluster. Provides a
unified installer, shared configuration, skills, hooks, and sandbox preparation
for multiple AI coding agents.

## Supported Agents

| Agent | CLI | VSCode Extension | Install Method |
|---|---|---|---|
| **Claude Code** | `claude` | `anthropic.claude-code` | Native binary (`curl -fsSL https://claude.ai/install.sh \| bash`) |
| **Codex CLI** | `codex` | `openai.chatgpt` | `npm i -g @openai/codex` |
| **OpenCode** | `opencode` | `sst-dev.opencode` | `npm i -g opencode` |
| **Pi** | `pi` | `pi0.pi-vscode` | `npm i -g @mariozechner/pi-coding-agent` |
| **Gemini CLI** | `gemini` | — | `npm i -g @google/gemini-cli` |
| **Amp** | `amp` | — | `npm i -g @sourcegraph/amp` |

## Quick Start

```bash
# Install the package
uv pip install .

# Run the interactive installer
coding-agents install

# Initialize a project
cd /hpc/compgen/projects/my-project/my-subproject
coding-agents project-init

# Check health
coding-agents doctor

# Re-sync after config changes
coding-agents sync

# Update all agents
coding-agents update

# Clean removal
coding-agents uninstall
```

## Subcommands

| Command | Description |
|---|---|
| `install` | Interactive Textual TUI installer (7 steps, back-navigation) |
| `update` | Update all agents + tools to latest, re-sync configs |
| `project-init` | Bootstrap a project directory with AGENTS.md, hooks, agent configs |
| `sync` | Re-distribute shared config to all agent-native locations |
| `doctor` | Health check with color-coded pass/warn/fail + fix commands |
| `uninstall` | Clean removal of all installed components |

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
│   │   └── screens/            # 7 TUI screens
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
│   └── skills/                 # crawl4ai, hpc-cluster (bundled skills)
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
- **hpc-cluster**: UMC Utrecht HPC cluster reference — SLURM, GPUs, storage (bundled)

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
