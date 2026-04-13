# Coding agent configuration systems compared: Claude Code, OpenCode, and Codex

**All three major coding agents now support AGENTS.md as an emerging standard**, enabling straightforward configuration portability. Claude Code uses JSON settings with Markdown instructions, OpenCode employs flexible JSON/JSONC configuration with built-in Claude compatibility mode, and ChatGPT Codex utilizes TOML-based configuration with Starlark execution policies. While **40%+ of configuration concepts map directly across all three agents**, each platform offers unique capabilities—Claude Code excels in enterprise hooks, OpenCode provides the most granular permissions, and Codex introduces declarative execution policies.

## Configuration file formats diverge significantly

The three agents take fundamentally different approaches to configuration storage. **Claude Code** relies on JSON files (`.claude/settings.json`, `~/.claude/settings.json`) with a five-tier hierarchy from enterprise-managed down to user level. **OpenCode** uses JSON or JSONC (`opencode.json`) with the most extensive hierarchy—six precedence levels including remote organizational configs. **Codex** breaks from the pack with TOML format (`~/.codex/config.toml`) plus project-level overrides.

| Aspect | Claude Code | OpenCode | ChatGPT Codex |
|--------|-------------|----------|---------------|
| **Primary config file** | `settings.json` | `opencode.json` | `config.toml` |
| **Format** | JSON | JSON/JSONC | TOML |
| **User location** | `~/.claude/settings.json` | `~/.config/opencode/opencode.json` | `~/.codex/config.toml` |
| **Project location** | `.claude/settings.json` | `opencode.json` (root) | `.codex/config.toml` |
| **Local overrides** | `.claude/settings.local.json` | Via env vars | CLI flags, profiles |
| **Schema validation** | No | Yes (`config.json`) | Yes (`config.schema.json`) |
| **Enterprise/admin config** | `managed-settings.json` | Remote `.well-known/opencode` | `requirements.toml` |

Priority hierarchies follow similar patterns: enterprise/admin settings cannot be overridden, CLI flags take precedence for the session, project configs override user configs. OpenCode's **five-level merge system** is most sophisticated, with remote organizational defaults, global user, custom path, project, environment variable, and inline config all contributing.

## Agent instructions converge on AGENTS.md

The most portable component across all three agents is instruction files. While Claude Code introduced **CLAUDE.md**, both OpenCode and Codex have adopted **AGENTS.md** as their primary format—and OpenCode includes Claude Code compatibility mode that automatically reads CLAUDE.md when AGENTS.md is absent.

| Feature | Claude Code | OpenCode | ChatGPT Codex |
|---------|-------------|----------|---------------|
| **Primary instruction file** | `CLAUDE.md` | `AGENTS.md` | `AGENTS.md` |
| **Fallback files** | `CLAUDE.local.md` | `CLAUDE.md` (compatibility) | Configurable via `project_doc_fallback_filenames` |
| **User-level location** | `~/.claude/CLAUDE.md` | `~/.config/opencode/AGENTS.md` | `~/.codex/AGENTS.md` |
| **Project location** | `./CLAUDE.md` or `.claude/CLAUDE.md` | `./AGENTS.md` | `./AGENTS.md` |
| **Format** | Markdown | Markdown | Markdown |
| **Max size** | Unlimited | Unlimited | 32 KiB default (configurable) |
| **Directory walking** | No | No | Yes (root to CWD) |

Claude Code offers unique features: the `#` key during sessions adds instructions directly to CLAUDE.md, and the `/memory` command provides an editor interface. Codex uniquely **walks the directory tree** from repository root to current working directory, concatenating AGENTS.md files found along the path.

**For maximum portability**: Create an `AGENTS.md` file and symlink it to `CLAUDE.md`:
```bash
ln -s AGENTS.md CLAUDE.md
```

## Hooks and execution policies differ architecturally

Each agent handles automation and command control differently:

**Claude Code** defines hooks in `settings.json` with event-based triggers:
```json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "Write|Edit",
      "hooks": [{"type": "command", "command": "./format.sh"}]
    }],
    "PreToolUse": [{
      "matcher": "Bash(rm:*)",
      "hooks": [{"type": "command", "command": "echo 'blocked' && exit 1"}]
    }]
  }
}
```
Supported events: `PreToolUse`, `PostToolUse`, `PermissionRequest`, `Notification`, `UserPromptSubmit`, `Stop`, `SubagentStop`, `PreCompact`, `SessionStart`, `SessionEnd`.

**OpenCode** handles hooks through its **plugin system** (`.opencode/plugin/*.ts`), not native configuration. Plugins can define custom tools, hooks, and integrations.

**Codex** introduces **Starlark-based execution policies** (`~/.codex/rules/*.rules`):
```python
# ~/.codex/rules/default.rules
prefix_rule(
    pattern = ["gh", "pr", "create"],
    decision = "prompt",
    justification = "PR creation requires approval"
)
```
This declarative approach is unique—decisions cascade with `forbidden > prompt > allow` precedence.

| Capability | Claude Code | OpenCode | Codex |
|------------|-------------|----------|-------|
| **Hook definition** | JSON in settings | Plugin system | Starlark rules files |
| **Pre-execution hooks** | `PreToolUse` | Via plugins | `prefix_rule()` |
| **Post-execution hooks** | `PostToolUse` | Via plugins | `notify` config |
| **Command filtering** | Matcher patterns | Permission config | Starlark patterns |
| **Decision types** | Allow/deny/ask | Allow/ask/deny | Allow/prompt/forbidden |

## MCP server configuration shows strong alignment

All three agents support the Model Context Protocol with nearly identical configuration patterns:

**Claude Code** (`.mcp.json` or `~/.claude.json`):
```json
{
  "mcpServers": {
    "github": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"}
    }
  }
}
```

**OpenCode** (`opencode.json`):
```json
{
  "mcp": {
    "github": {
      "type": "local",
      "command": ["npx", "-y", "@modelcontextprotocol/server-github"],
      "environment": {"GITHUB_TOKEN": "{env:GITHUB_TOKEN}"}
    }
  }
}
```

**Codex** (`~/.codex/config.toml`):
```toml
[mcp_servers.github]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-github"]
[mcp_servers.github.env]
GITHUB_TOKEN = "value"
```

| MCP Feature | Claude Code | OpenCode | Codex |
|-------------|-------------|----------|-------|
| **Config location** | `.mcp.json`, `~/.claude.json` | `opencode.json` | `config.toml` |
| **Transport types** | stdio, http, sse | local, remote | stdio, streamable-http |
| **OAuth support** | Manual headers | Built-in OAuth flow | Built-in OAuth |
| **CLI management** | `claude mcp add/list/remove` | `opencode mcp add/list` | `codex mcp add/list/remove` |
| **Environment vars** | `${VAR}` syntax | `{env:VAR}` syntax | Direct values or env refs |

## Skills and custom commands have parallel structures

All three agents support extending capabilities through structured skill/command definitions:

| Aspect | Claude Code | OpenCode | Codex |
|--------|-------------|----------|-------|
| **Skills location** | `.claude/skills/` | `.opencode/agent/` | `.codex/skills/` |
| **Commands location** | `.claude/commands/` | `.opencode/command/` | N/A (use skills) |
| **File format** | Markdown + YAML frontmatter | Markdown + YAML frontmatter | Markdown + YAML frontmatter |
| **User-level skills** | `~/.claude/commands/` | `~/.config/opencode/agent/` | `~/.codex/skills/` |

**SKILL.md structure** (Codex example, similar for all):
```markdown
---
name: commit-message
description: Draft conventional commit messages
metadata:
  short-description: Create commit messages
---

Draft a conventional commit message following these rules:
- Use imperative mood
- Keep under 72 characters
```

Claude Code additionally supports **subagents** (`.claude/agents/*.md`) for specialized AI assistants, and **plugins** for extending functionality.

## Environment variables and API configuration

| Variable | Claude Code | OpenCode | Codex |
|----------|-------------|----------|-------|
| **API key** | `ANTHROPIC_API_KEY` | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | `OPENAI_API_KEY` |
| **Base URL** | `ANTHROPIC_BASE_URL` | Provider-specific config | Provider config |
| **Config dir override** | `CLAUDE_CONFIG_DIR` | `OPENCODE_CONFIG_DIR` | `CODEX_HOME` |
| **Disable telemetry** | `DISABLE_TELEMETRY` | Via config | Via config |
| **Model selection** | `ANTHROPIC_MODEL` | `model` in config | `model` in config |

OpenCode supports **75+ model providers** including OpenAI, Anthropic, Gemini, Bedrock, Azure, and local models—the most provider flexibility. Codex includes **profiles** for switching between model configurations:
```toml
[profiles.deep-review]
model = "gpt-5-pro"
model_reasoning_effort = "high"
```

## Comprehensive configuration mapping

### Direct equivalents across all three agents

| Concept | Claude Code | OpenCode | Codex |
|---------|-------------|----------|-------|
| Instructions file | `CLAUDE.md` | `AGENTS.md` | `AGENTS.md` |
| User config | `~/.claude/settings.json` | `~/.config/opencode/opencode.json` | `~/.codex/config.toml` |
| Project config | `.claude/settings.json` | `opencode.json` | `.codex/config.toml` |
| MCP config | `.mcp.json` | `opencode.json` (mcp section) | `config.toml` (mcp_servers) |
| Skills/commands | `.claude/commands/` | `.opencode/command/` | `.codex/skills/` |
| User skills | `~/.claude/commands/` | `~/.config/opencode/command/` | `~/.codex/skills/` |
| Permission rules | `permissions` in settings | `permission` in config | `approval_policy` + rules |

### Unique features with no direct equivalent

**Claude Code only:**
- `#` key to add instructions during sessions
- Enterprise `managed-settings.json` and `managed-mcp.json`
- Subagents (`.claude/agents/`)
- Plugin marketplace system
- `companyAnnouncements` for startup messages

**OpenCode only:**
- Claude Code compatibility mode (`OPENCODE_DISABLE_CLAUDE_CODE=1` to disable)
- Remote organizational config via `.well-known/opencode`
- `instructions` array in config to pull from multiple files/URLs
- Built-in formatters configuration
- 75+ model providers supported natively

**Codex only:**
- Starlark execution policies (`.rules` files)
- Profile system for switching configurations
- `requirements.toml` for admin-enforced constraints
- Directory tree walking for AGENTS.md discovery
- Shell environment policy controls
- `model_reasoning_effort` tuning

## GitHub tools for configuration synchronization

The ecosystem offers several mature solutions for maintaining cross-agent compatibility:

**vibe-rules** (425 stars) — The most comprehensive tool:
```bash
npm install -g vibe-rules
vibe-rules convert claude-code opencode ./project  # Convert CLAUDE.md to AGENTS.md
vibe-rules load my-rules claude-code cursor codex  # Apply rules to multiple agents
```
Supports: Claude Code, Cursor, Windsurf, Codex, OpenCode, Gemini, Amp, Cline, Zed, VSCode.

**rulesync** — Generate rule files for all tools from a single source:
```bash
npx rulesync generate  # Creates CLAUDE.md, AGENTS.md, .cursorrules from unified source
npx rulesync import --claude-code  # Import existing Claude config
```

**skills** (Rust CLI) — Specifically for Claude Code ↔ Codex skill synchronization:
```bash
cargo install skills
skills push   # Push skills to both ~/.claude/skills and ~/.codex/skills
skills sync   # Two-way sync based on timestamps
```

**knowhub** — Synchronize knowledge files across projects:
```bash
npx knowhub  # Sync configured files across multiple repositories
```

## Practical approach for mirroring .claude to Codex and OpenCode

### Recommended directory structure

```
~/.ai-config/                    # Single source of truth
├── AGENTS.md                    # Universal instructions
├── skills/                      # Shared skills
│   └── commit-message/SKILL.md
├── mcp-servers.json             # MCP definitions (convert per-tool)
└── sync.sh                      # Sync script

# Symlinks created by sync script:
~/.claude/CLAUDE.md        → ~/.ai-config/AGENTS.md
~/.config/opencode/AGENTS.md → ~/.ai-config/AGENTS.md
~/.codex/AGENTS.md         → ~/.ai-config/AGENTS.md
```

### Automated sync script

```bash
#!/bin/bash
# sync-ai-configs.sh - Mirror .claude configuration to OpenCode and Codex

SOURCE_DIR="$HOME/.claude"
OPENCODE_DIR="$HOME/.config/opencode"
CODEX_DIR="$HOME/.codex"

# 1. Sync instructions file
if [ -f "$SOURCE_DIR/CLAUDE.md" ]; then
    cp "$SOURCE_DIR/CLAUDE.md" "$OPENCODE_DIR/AGENTS.md"
    cp "$SOURCE_DIR/CLAUDE.md" "$CODEX_DIR/AGENTS.md"
fi

# 2. Convert MCP servers (Claude JSON → OpenCode JSON → Codex TOML)
if [ -f "$HOME/.mcp.json" ]; then
    # Use jq to transform Claude MCP format to OpenCode format
    jq '.mcpServers | to_entries | map({
        (.key): {
            type: (if .value.type == "stdio" then "local" else "remote" end),
            command: (if .value.command then [.value.command] + .value.args else null end),
            url: .value.url,
            environment: .value.env
        }
    }) | add | {mcp: .}' "$HOME/.mcp.json" > /tmp/opencode-mcp.json
    
    # Merge with existing opencode.json
    jq -s '.[0] * .[1]' "$OPENCODE_DIR/opencode.json" /tmp/opencode-mcp.json > "$OPENCODE_DIR/opencode.json.tmp"
    mv "$OPENCODE_DIR/opencode.json.tmp" "$OPENCODE_DIR/opencode.json"
fi

# 3. Sync skills/commands
rsync -av "$SOURCE_DIR/commands/" "$OPENCODE_DIR/command/"
rsync -av "$SOURCE_DIR/commands/" "$CODEX_DIR/skills/"

# 4. Convert hooks to Codex rules (manual review recommended)
echo "Note: Claude Code hooks require manual conversion to Codex .rules files"
```

### Using vibe-rules for automated sync

The most maintainable approach uses vibe-rules with a CI/CD pipeline:

```yaml
# .github/workflows/sync-ai-rules.yml
name: Sync AI Agent Rules
on:
  push:
    paths: ['.claude/**', 'CLAUDE.md']

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm install -g vibe-rules
      - run: |
          vibe-rules convert claude-code opencode .
          vibe-rules convert claude-code codex .
      - uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "Sync AI agent configurations"
```

### MCP server conversion reference

Since MCP configurations differ primarily in syntax, here's a conversion template:

```javascript
// mcp-converter.js - Convert Claude MCP to OpenCode and Codex formats
const claudeMcp = require('./.mcp.json');

// To OpenCode format
const opencodeMcp = { mcp: {} };
for (const [name, config] of Object.entries(claudeMcp.mcpServers)) {
    opencodeMcp.mcp[name] = {
        type: config.type === 'stdio' ? 'local' : 'remote',
        command: config.command ? [config.command, ...(config.args || [])] : undefined,
        url: config.url,
        environment: config.env
    };
}

// To Codex TOML format
let codexToml = '';
for (const [name, config] of Object.entries(claudeMcp.mcpServers)) {
    codexToml += `[mcp_servers.${name}]\n`;
    if (config.command) {
        codexToml += `command = "${config.command}"\n`;
        codexToml += `args = ${JSON.stringify(config.args || [])}\n`;
    }
    if (config.env) {
        codexToml += `[mcp_servers.${name}.env]\n`;
        for (const [k, v] of Object.entries(config.env)) {
            codexToml += `${k} = "${v}"\n`;
        }
    }
}
```

## Conclusion

The three coding agents share more architecture than they diverge on. **AGENTS.md has emerged as a de facto standard** for agent instructions—OpenCode reads it natively and provides Claude Code compatibility; Codex uses it as the primary format. MCP server configuration is structurally identical across all three, differing only in JSON vs TOML syntax and minor key naming.

For practical cross-agent compatibility, maintain **a single source of truth** for instructions (AGENTS.md symlinked to CLAUDE.md), use **vibe-rules or rulesync** for automated conversion of rules and settings, and handle **MCP servers with a simple conversion script**. The primary gap remains **hooks/execution policies**: Claude Code's event-based JSON hooks, OpenCode's plugin system, and Codex's Starlark rules require manual translation between paradigms.

The **skills** Rust CLI specifically addresses Claude Code ↔ Codex skill synchronization, while broader tools like vibe-rules handle instruction files across 10+ editors. As the ecosystem matures, AGENTS.md adoption will likely simplify multi-agent workflows further—Cursor 1.6+ already supports it alongside its native `.cursorrules` format.