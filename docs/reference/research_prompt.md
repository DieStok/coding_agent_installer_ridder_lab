# Deep Research: Coding Agent Configuration Ecosystem — What Changed Since January 2026

You are a senior developer-tools engineer with deep expertise in: (1) terminal-based AI coding agents and their configuration systems, (2) cross-agent portability of instructions, skills, hooks, and MCP servers, (3) Linux process isolation and sandboxing for AI agents, (4) VSCode extension ecosystems for coding agents, and (5) the AGENTS.md specification and its adoption. You have been working daily with Claude Code, OpenCode, ChatGPT Codex, Aider, Gemini CLI, Amp, and Pi (the "shitty coding agent" by Mario Zechner / @badlogic) since mid-2025.

## Context: Prior Work (January 2026)

You are provided with two reference documents from January 2026:

1. **`coding_agent_configuration_compared_codex_opencode_claude.md`** — A detailed comparison of configuration file formats, instruction files (CLAUDE.md / AGENTS.md), hooks and execution policies, MCP server configuration, skills/commands, environment variables, and cross-agent sync tooling (vibe-rules, rulesync, skills CLI, knowhub) across Claude Code, OpenCode, and ChatGPT Codex. Key findings at the time: AGENTS.md had emerged as a de facto standard; MCP config was structurally identical across agents differing only in JSON vs TOML syntax; hooks/execution policies remained the primary gap (Claude Code's JSON hooks vs OpenCode's plugins vs Codex's Starlark rules); vibe-rules (425 stars) was the leading sync tool.

2. **`ai-config-package_v1.zip`** — A complete cross-agent configuration package with: a `~/.ai-config/` single-source-of-truth directory structure; shared AGENTS.md, skills (code-review, security-audit, api-design), hooks (command_filter.py, auto_format.py, log_activity.py), commands, subagents, MCP server definitions with a convert-mcp.js converter; per-agent settings templates (claude-settings.json, opencode-settings.json, codex-config.toml); an example project with CI/CD sync workflow; and install/sync/project-init scripts.

**It is now April 10, 2026.** Three months have passed. The ecosystem has moved fast.

> **Central research question:** What has changed in the coding agent configuration and integration ecosystem since January 2026, and how should the cross-agent configuration package and comparison document be updated to reflect the current state — including new agents (Pi/OpenClaw, oh-my-pi), new sandboxing tools (jai from Stanford), the matured AGENTS.md spec, and VSCode integration patterns?

Sub-questions:
1. What configuration, hook, skill, MCP, and instruction-file changes have shipped in Claude Code, OpenCode, ChatGPT Codex, Gemini CLI, Aider, and Amp between January and April 2026?
2. How does Pi (shittycodingagent.ai / badlogic/pi-mono) fit into the configuration landscape — what are its config files, instruction files, extension system, MCP support, skill/agent definitions, and how do they map to the existing cross-agent config package?
3. How does Stanford's jai sandbox (jai.scs.stanford.edu / stanford-scs/jai) integrate with each of these coding agents — both in their terminal CLI versions and in their VSCode extension versions — and how does it compare to Claude Code's native sandboxing, Docker Sandboxes, and bubblewrap?
4. What is the current state of the AGENTS.md specification (agents.md), including its governance under the Linux Foundation's Agentic AI Foundation, and which agents now support it natively?
5. How should the cross-agent configuration package (ai-config-package_v1) be updated to incorporate these changes — new agents, new sandboxing, new sync tools, and any deprecated patterns?

## Output Specification

Produce a single comprehensive report of **12,000–18,000 words** across all Parts below. Use concrete version numbers, dates, GitHub star counts, config file snippets, and CLI commands throughout. Do not hedge or summarize vaguely — provide specific, actionable technical details.

---

## Part 1: Configuration Systems — What Changed (January → April 2026)

For each of the following agents, document every configuration-relevant change shipped between January 1 and April 10, 2026. For each change, provide: (a) the version or date it shipped, (b) what specifically changed in config file format or location, (c) a config snippet showing the new syntax, (d) whether it affects cross-agent portability, and (e) migration notes from the January 2026 baseline.

### Agents to cover (do not skip any):

1. **Claude Code** — Cover: sandboxing configuration (`/sandbox`, sandbox modes, `sandbox.failIfUnavailable`), any changes to `settings.json` schema, new hook events beyond the January 2026 set (PreToolUse, PostToolUse, PermissionRequest, Notification, UserPromptSubmit, Stop, SubagentStop, PreCompact, SessionStart, SessionEnd), changes to `.mcp.json` format, subagent configuration changes, any new managed-settings or enterprise features. Search specifically for Claude Code changelog entries and release notes from v2.0.x through v2.1.98+.

2. **ChatGPT Codex** — Cover: any changes to `config.toml` schema, Starlark rules updates, new MCP transport types, profile system enhancements, `requirements.toml` changes, model_reasoning_effort options. Search for Codex CLI releases and OpenAI developer blog posts from January–April 2026.

3. **OpenCode** — Cover: any changes to `opencode.json` schema, plugin system updates, new provider integrations, Claude Code compatibility mode changes, remote organizational config updates. Note the January 2026 incident where Anthropic briefly blocked OpenCode from the Claude API and its resolution. Search for OpenCode GitHub releases and documentation updates.

4. **Gemini CLI** — Cover: configuration file format (`.gemini/` directory structure, `settings.json`), AGENTS.md support, MCP server configuration, subagent definitions (`.gemini/agents/`), Plan Mode configuration (shipped March 11, 2026), Conductor automated reviews. Search for Gemini CLI GitHub releases v0.30–v0.35+ and Google AI developer documentation.

5. **Aider** — Cover: any configuration file changes, new model support (GPT-5 models, Grok-4, Gemini 2.5 Flash Lite added in v0.86.0), AGENTS.md adoption status, MCP support status. Search for Aider GitHub releases and changelog from January–April 2026.

6. **Amp** (from Sourcegraph) — Cover: configuration format, AGENTS.md support, composable tool system, sub-agents (Oracle, Librarian), Deep mode with GPT-5.2-Codex, MCP support. Search for Amp documentation and release notes.

**Search for:** "Claude Code v2.1 changelog 2026", "Codex CLI release notes 2026", "OpenCode releases 2026", "Gemini CLI v0.35 release", "Aider changelog 2026", "Amp coding agent configuration", "AGENTS.md supported agents list 2026"

### Deliverable for Part 1:
An updated version of the January 2026 comparison tables, showing what cells have changed. Use a format like:

| Aspect | Claude Code (Jan→Apr) | OpenCode (Jan→Apr) | Codex (Jan→Apr) | Gemini CLI (NEW) | Aider (NEW) | Amp (NEW) |

---

## Part 2: Pi (shittycodingagent.ai) — Configuration Deep Dive

Pi is a TypeScript-based coding agent by Mario Zechner (@badlogic), hosted at https://shittycodingagent.ai/ with source at https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent (npm: `@mariozechner/pi-coding-agent`, currently v0.66.x with 1.5M+ npm downloads). It is built from a layered monorepo: `pi-ai` (unified LLM API), `pi-agent-core` (agent loop + tool calling), `pi-coding-agent` (full agent runtime), and `pi-tui` (terminal UI).

Also cover **oh-my-pi** (`can1357/oh-my-pi`), a major fork/extension of Pi that adds Hashline editing, Cursor OAuth bridge, swarm extensions, 65+ themes, multi-agent task management, and xhigh thinking level.

For Pi, document the following with the same specificity as Part 1:

1. **Configuration files and locations**: What is Pi's equivalent of `settings.json` / `opencode.json` / `config.toml`? Where is it stored (`~/.pi/agent/` or similar)? What format (JSON, TOML, YAML)? What does the schema look like?
2. **Instruction files**: Does Pi read AGENTS.md? Does it have its own instruction file format? How does directory walking work? What is the precedence hierarchy?
3. **Model configuration**: Pi supports 10+ providers (Anthropic, OpenAI, Google, xAI, Groq, Cerebras, OpenRouter, Ollama, vLLM, LM Studio, and any OpenAI-compatible endpoint). How are custom providers configured via `~/.pi/agent/models.json`? How do cross-provider context handoffs work?
4. **Extension system**: Pi's extension system is its most distinctive feature. Extensions can register tools, define custom UI, store persistent state, hot-reload, and the agent can build its own extensions. Document: extension file format, registration API, available hooks, state persistence, the self-extension workflow.
5. **Skills and prompt templates**: How does Pi handle skills? Where are they stored? Format?
6. **MCP support**: Does Pi support MCP servers? If so, what transport types and configuration format?
7. **Session persistence**: Pi uses JSONL session files with cross-provider context handoff. How are sessions stored? How does the "signed blob" handling work for Anthropic↔OpenAI switches?

**Search for:** "pi coding agent configuration", "pi-mono settings.json", "pi coding agent extensions tutorial", "oh-my-pi configuration settings", "shittycodingagent AGENTS.md", "pi coding agent MCP support", "mariozechner pi-coding-agent docs"

### Cross-agent mapping table for Part 2:

| Concept | Claude Code | OpenCode | Codex | Gemini CLI | Pi | oh-my-pi |
|---------|-------------|----------|-------|------------|----|---------  |

Map every configuration concept from the January 2026 comparison to Pi's equivalent, noting gaps and unique features.

### Pi-only features with no equivalent:
- Extension hot-reload and self-extension
- Cross-provider session handoffs with signed blob conversion
- Pi-share-hf (session publishing to Hugging Face)
- Browser-compatible `pi-ai` (CORS support from Anthropic/xAI)
- The VSCode Language Model Provider extension (`tintinweb.vscode-pi-model-chat-provider`)

---

## Part 3: jai — Stanford's Lightweight Sandbox for AI Agents

jai (https://jai.scs.stanford.edu/, https://github.com/stanford-scs/jai) is a super-lightweight Linux sandbox from Stanford's Secure Computer Systems group, created by David Mazières. It shipped v0.2 on March 27, 2026, then v0.3 with quality-of-life improvements. It requires Linux kernel 6.13+ and is written in C++ with a security-over-portability philosophy.

### 3.1 jai Fundamentals
Document the three isolation modes with their security properties:
- **Casual** (default for unnamed jails): copy-on-write home, runs as your user, full CWD access, private /tmp, read-only filesystem. Protects integrity but NOT confidentiality.
- **Strict** (default for named jails): empty private home, runs as unprivileged `jai` user, id-mapped mount for granted directories, UID-based confidentiality.
- **Bare**: empty private home like strict, but runs as your user. For NFS home directories where id-mapped mounts don't work.

Document: named jails (`-j name`), configuration files (`$HOME/.jai/`, `.defaults`, `cmd.conf`, `name.jail`), directory grants (`-d`), read-only exports (`-r`, `--rdir`), init scripts (`--initjail`, `--script`), environment variable filtering, PID namespace isolation, and the v0.3 additions.

### 3.2 jai Integration with Each Coding Agent (Terminal CLI)

For each agent, provide the exact `jai` invocation, the recommended jail configuration, and any known issues:

1. **Claude Code**: `jai claude` or `jai -j claude claude`. Document the recipe from jai's man page: `cat <<EOF >$HOME/.jai/claude.conf` with `conf .defaults` and `dir .claude`. How does this interact with Claude Code's own sandboxing (Seatbelt on macOS, bubblewrap on Linux)? Can they be layered? Should they be?

2. **ChatGPT Codex**: `jai codex` or `jai -d ~/.codex codex`. Document the casual-mode recipe from jai's man page that grants `.codex` config directory access.

3. **OpenCode**: `jai -d ~/.config/opencode -d ~/.local/share/opencode opencode`. Document directory grants needed for OpenCode's config and data directories.

4. **Gemini CLI**: Determine the correct `jai` invocation. What directories does Gemini CLI need (likely `~/.gemini/`, Google auth tokens)?

5. **Aider**: Determine the correct `jai` invocation. Aider stores config in `~/.aider/` and may need git credentials.

6. **Pi**: Determine the correct `jai` invocation for Pi. What directories does Pi need (`~/.pi/`)?

7. **Amp**: Determine the correct `jai` invocation.

**Search for:** "jai sandbox claude code recipe", "jai sandbox codex configuration", "jai named jails coding agents", "jai v0.3 release notes", "jai configuration file format", "jai strict mode coding agent"

### 3.3 jai vs. Other Sandboxing Approaches

Compare jai to:
- **Claude Code's native sandboxing** (Seatbelt/bubblewrap, launched ~early 2026): Application-level, per-command, auto-allow mode, network proxy with domain allowlisting. The March 2026 bypass (Ona) where Claude used `/proc/self/root/` to circumvent path-based denylist.
- **Docker Sandboxes** (launched January 2026): Full microVM with private kernel and Docker daemon, `sbx run claude`, strongest isolation but heaviest. Requires Docker Desktop license for macOS/Windows.
- **bubblewrap** (bwrap): More flexible than jai but requires 15+ flags for equivalent setup. No overlay filesystem without fuse-overlayfs.
- **Lima** (~20k stars, CNCF): Full VM, open-source Docker Desktop alternative. More setup but full isolation.
- **Tart**: macOS-specific, best for CI.
- **Apple Containerization** (WWDC 2025/macOS 26): Per-container VM isolation, sub-second startup.

Produce a comparison matrix:

| Feature | jai | Claude Code Sandbox | Docker Sandbox | bubblewrap | Lima |
|---------|-----|-------------------|---------------|-----------|------|
| Setup complexity | | | | | |
| Filesystem isolation | | | | | |
| Network isolation | | | | | |
| Confidentiality | | | | | |
| Kernel requirement | | | | | |
| macOS support | | | | | |
| Can layer with other sandboxes | | | | | |

### 3.4 jai Integration with VSCode Extensions

This is the most speculative section — jai is a Linux-only CLI tool, so integration with VSCode extensions requires creative approaches. Research and document:

1. **Claude Code in VSCode** (the Claude agent via GitHub Copilot's third-party agent system, or the standalone Claude Code VSCode extension): Can the underlying Claude Code terminal process be wrapped with jai? How?
2. **Codex in VSCode** (OpenAI Codex extension): Same question.
3. **Gemini Code Assist in VSCode** (agent mode): Same question.
4. **Pi's VSCode extension** (`tintinweb.vscode-pi-model-chat-provider`): Same question.
5. **General pattern**: Can VSCode's integrated terminal be configured to run inside jai? Can tasks.json or launch.json invoke jai-wrapped commands? What about Remote-SSH + jai on a Linux server?

**Search for:** "jai sandbox VSCode integration", "VSCode integrated terminal sandbox", "VSCode tasks.json sandbox wrapper", "Claude Code VSCode extension sandboxing", "Remote-SSH jai sandbox"

---

## Part 4: AGENTS.md Specification and Ecosystem Maturation

### 4.1 AGENTS.md Specification Status
The AGENTS.md spec (https://agents.md/) is now stewarded by the **Agentic AI Foundation under the Linux Foundation**. Document:
- Current spec version and any normative changes since January 2026
- Governance structure under the Linux Foundation
- Which organizations are founding members
- Any formal schema or validation tooling
- The resolution mechanism: "The closest AGENTS.md to the edited file wins; explicit user chat prompts override everything"

### 4.2 Agent Support Matrix (April 2026)
Produce a comprehensive support matrix. The agents.md website lists supported agents including: Aider, Goose, OpenCode, Zed, Warp, VS Code, Devin (Cognition), Autopilot & Coded Agents (UiPath), Junie (JetBrains), Amp, Cursor, Roo Code, Gemini CLI (Google), Kilo Code, Phoenix, Semgrep, Coding Agent (GitHub Copilot), Ona, Windsurf (Cognition), Augment Code. For each, document: native AGENTS.md support (yes/no), fallback to CLAUDE.md or other files, directory walking behavior, max file size limits.

### 4.3 Cross-Agent Sync Tooling Update
Update the January 2026 inventory of sync tools:
- **vibe-rules** — Current star count, new supported agents, any breaking changes. Was at 425 stars in January.
- **rulesync** — Current status, new features.
- **skills** (Rust CLI) — Current status.
- **knowhub** — Current status.
- **Any new tools** that have emerged since January 2026.

**Search for:** "AGENTS.md specification 2026", "Agentic AI Foundation Linux Foundation", "AGENTS.md supported agents", "vibe-rules 2026 update", "rulesync 2026", "coding agent config sync tools 2026"

---

## Part 5: Updated Cross-Agent Configuration Package Design

Based on findings from Parts 1–4, produce a concrete specification for `ai-config-package_v2`. This is the actionable output.

### 5.1 Updated Directory Structure
Propose the new `~/.ai-config/` structure that adds support for Pi, Gemini CLI, Aider, Amp, jai sandbox configurations, and any new patterns. Show the full tree with annotations.

### 5.2 jai Configuration Integration
Design a `~/.ai-config/jai/` subdirectory that contains:
- A `.defaults` template with sensible blacklists for coding agents
- Per-agent `.conf` files (claude.conf, codex.conf, opencode.conf, gemini.conf, pi.conf, aider.conf, amp.conf)
- Per-agent `.jail` files for named jails with strict mode defaults
- An `--initjail` script that provisions named jails with the agent-specific dotfiles they need
- A wrapper script that detects the OS and falls back gracefully (jai on Linux, Claude Code sandbox on macOS, Docker Sandbox as universal fallback)

### 5.3 Updated Sync Script
Specify changes to `sync.sh` to handle:
- Pi configuration (`~/.pi/agent/`)
- Gemini CLI configuration (`~/.gemini/`)
- Aider configuration (`~/.aider/`)
- Amp configuration
- jai jail configs
- The new AGENTS.md spec compliance

### 5.4 Updated MCP Converter
Specify additions to `convert-mcp.js` to handle Pi's MCP format and Gemini CLI's MCP format, in addition to the existing Claude→OpenCode→Codex conversions.

### 5.5 Migration Guide from v1 to v2
List every breaking change, deprecated pattern, and new requirement. Provide a migration checklist a user can follow.

### 5.6 VSCode Integration Layer
Design a pattern for using these agents from VSCode with sandboxing:
- How to configure VSCode tasks.json to invoke agents through jai
- How to use the Remote-SSH extension with a jai-enabled Linux server
- How to configure each agent's VSCode extension (Claude, Codex, Gemini Code Assist, Pi Language Model Provider) with appropriate sandboxing
- A `.vscode/settings.json` template that configures all agent extensions with shared AGENTS.md and MCP servers

---

## Critical Reminders

1. **Be specific about versions and dates.** Every claim about a feature should include the version number or release date it shipped. Do not say "recently added" — say "added in Claude Code v2.1.85 (March 15, 2026)."

2. **Provide config snippets.** Every configuration format discussion should include a concrete code block showing the actual syntax. Do not describe formats abstractly.

3. **Search aggressively.** The ecosystem moves weekly. Search for the latest releases and changelogs for every agent. Search specifically for any changes shipped in March and April 2026.

4. **Flag what you could NOT verify.** If a feature's current status is uncertain, say so explicitly rather than guessing. Mark speculative content with "[UNVERIFIED]".

5. **Prioritize the jai + VSCode integration question.** This is the most novel and least-documented aspect of the research. Invest extra search effort here, and if documentation is thin, reason carefully from first principles about what would and wouldn't work.

6. **Do not repeat the January 2026 findings verbatim.** The reader already has those documents. Focus on what is NEW or CHANGED. Reference the prior work but do not reproduce it.

## APPENDIX: PROJECT CONTEXT AND REFERENCE MATERIALS

### A. Key URLs to Fetch and Analyze

- Pi coding agent docs: https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent
- Pi coding agent blog post: https://mariozechner.at/posts/2025-11-30-pi-coding-agent/
- oh-my-pi: https://github.com/can1357/oh-my-pi
- Armin Ronacher's Pi review: https://lucumr.pocoo.org/2026/1/31/pi/
- jai homepage: https://jai.scs.stanford.edu/
- jai GitHub: https://github.com/stanford-scs/jai
- jai man page: https://github.com/stanford-scs/jai/blob/master/jai.1.md
- jai quick start: https://jai.scs.stanford.edu/quick-start.html
- jai security model: https://jai.scs.stanford.edu/security.html
- jai comparison page: https://jai.scs.stanford.edu/comparison.html
- jai FAQ: https://jai.scs.stanford.edu/faq.html
- jai releases: https://github.com/stanford-scs/jai/releases
- AGENTS.md spec: https://agents.md/
- Claude Code docs (sandboxing): https://code.claude.com/docs/en/sandboxing
- Claude Code system prompts tracker: https://github.com/Piebald-AI/claude-code-system-prompts
- Docker Sandboxes for Claude Code: https://docs.docker.com/ai/sandboxes/agents/claude-code/
- VSCode third-party agents: https://code.visualstudio.com/docs/copilot/agents/third-party-agents
- Pi VSCode extension: https://marketplace.visualstudio.com/items?itemName=tintinweb.vscode-pi-model-chat-provider
- Gemini CLI: search for latest GitHub release
- Aider: https://github.com/Aider-AI/aider
- Amp: search for latest documentation
- vibe-rules: https://github.com/FutureExcited/vibe-rules

### B. Configuration Concepts from January 2026 (Map to New Agents)

These are the configuration concepts identified in the original comparison. For every new agent covered (Pi, Gemini CLI, Aider, Amp), find the equivalent:

| Concept | Claude Code | OpenCode | Codex | → Pi? | → Gemini CLI? | → Aider? | → Amp? |
|---------|-------------|----------|-------|-------|---------------|----------|--------|
| Primary config file | settings.json | opencode.json | config.toml | ? | ? | ? | ? |
| User config location | ~/.claude/ | ~/.config/opencode/ | ~/.codex/ | ? | ? | ? | ? |
| Project config location | .claude/ | opencode.json | .codex/ | ? | ? | ? | ? |
| Instruction file | CLAUDE.md | AGENTS.md | AGENTS.md | ? | ? | ? | ? |
| MCP config | .mcp.json | opencode.json | config.toml | ? | ? | ? | ? |
| Skills/commands | .claude/commands/ | .opencode/command/ | .codex/skills/ | ? | ? | ? | ? |
| Hooks/policies | JSON hooks | Plugin system | Starlark rules | ? | ? | ? | ? |
| Subagents | .claude/agents/ | N/A | N/A | ? | ? | ? | ? |
| Permission rules | settings.json | config permission | approval_policy | ? | ? | ? | ? |
| Enterprise/admin config | managed-settings.json | .well-known/opencode | requirements.toml | ? | ? | ? | ? |
| Sandbox config | /sandbox menu | N/A | N/A | ? | ? | ? | ? |

### C. Summary of the ai-config-package_v1 Structure (for v2 diff)

```
ai-config-package/
├── README.md
├── global-config/
│   ├── AGENTS.md
│   ├── skills/ (code-review, security-audit, api-design)
│   ├── hooks/ (command_filter.py, auto_format.py, log_activity.py, custom_rules.json)
│   ├── commands/ (review.md, test.md, deploy.md)
│   ├── agents/ (documentation-writer.md, code-reviewer.md, security-auditor.md)
│   ├── mcp/ (servers.json, convert-mcp.js)
│   └── settings/ (claude-settings.json, opencode-settings.json, codex-config.toml)
├── example-project/
│   ├── .ai-config/ (project-specific AGENTS.md, skills, hooks, commands)
│   ├── .claude/ (settings.json)
│   ├── .codex/ (config.toml, rules/project.rules)
│   ├── opencode.json
│   └── .github/workflows/sync-ai-configs.yml
└── scripts/ (sync.sh, install.sh, project-init.sh)
```

The v2 design should show a clear diff from this structure, adding support for Pi, Gemini CLI, Aider, Amp, jai, and VSCode integration while maintaining backward compatibility with v1 configurations.
