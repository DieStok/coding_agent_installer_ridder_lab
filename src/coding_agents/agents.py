"""Agent registry — single source of truth for all supported coding agents.

All subcommands iterate this dict generically. No per-agent logic outside
this file except for the three install functions at the bottom.
"""
from __future__ import annotations

AGENTS: dict[str, dict] = {
    "claude": {
        "display_name": "Claude Code",
        "method": "curl",
        "install_cmd": "curl -fsSL https://claude.ai/install.sh | bash",
        "binary": "claude",
        "version_cmd": ["claude", "--version"],
        "update_cmd": ["claude", "update"],
        "config_dir": "~/.claude",
        "instruction_file": "CLAUDE.md",
        "skills_dir": "~/.claude/skills/{name}/SKILL.md",
        "hooks_support": True,
        "deny_rules_format": "claude",
        "mcp_format": "claude",
        "vscode_extension": "anthropic.claude-code",
        "jai_conf": "claude.conf",
        "jai_env_keys": ["ANTHROPIC_API_KEY"],
    },
    "codex": {
        "display_name": "Codex CLI",
        "method": "npm",
        "package": "@openai/codex",
        "binary": "codex",
        "version_cmd": ["codex", "--version"],
        "config_dir": "~/.codex",
        "instruction_file": "AGENTS.md",
        "skills_dir": "~/.codex/skills/{name}/SKILL.md",
        "hooks_support": "experimental",
        "deny_rules_format": "starlark",
        "mcp_format": "codex",
        "vscode_extension": "openai.chatgpt",
        "jai_conf": "codex.conf",
        "jai_env_keys": ["OPENAI_API_KEY", "CODEX_API_KEY"],
    },
    "opencode": {
        "display_name": "OpenCode",
        "method": "npm",
        "package": "opencode",
        "binary": "opencode",
        "version_cmd": ["opencode", "--version"],
        "config_dir": "~/.config/opencode",
        "instruction_file": "AGENTS.md",
        "skills_dir": "~/.config/opencode/skills/{name}/SKILL.md",
        "hooks_support": False,
        "deny_rules_format": "opencode",
        "mcp_format": "opencode",
        "vscode_extension": "sst-dev.opencode",
        "jai_conf": "opencode.conf",
        "jai_env_keys": [],
    },
    "pi": {
        "display_name": "Pi",
        "method": "npm",
        "package": "@mariozechner/pi-coding-agent",
        "binary": "pi",
        "version_cmd": ["pi", "--version"],
        "config_dir": "~/.pi/agent",
        "instruction_file": "AGENTS.md",
        "skills_dir": "~/.pi/agent/skills/{name}/SKILL.md",
        "hooks_support": False,
        "deny_rules_format": None,
        "mcp_format": "pi",
        "vscode_extension": "pi0.pi-vscode",
        "jai_conf": "pi.conf",
        "jai_env_keys": ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"],
        "post_install": ["pi install npm:pi-ask-user", "pi install npm:pi-subagents"],
    },
    "gemini": {
        "display_name": "Gemini CLI",
        "method": "npm",
        "package": "@google/gemini-cli",
        "binary": "gemini",
        "version_cmd": ["gemini", "--version"],
        "config_dir": "~/.gemini",
        "instruction_file": "GEMINI.md",
        "skills_dir": None,
        "hooks_support": False,
        "deny_rules_format": None,
        "mcp_format": "gemini",
        "vscode_extension": None,
        "jai_conf": "gemini.conf",
        "jai_env_keys": ["GOOGLE_API_KEY"],
    },
    "amp": {
        "display_name": "Amp",
        "method": "npm",
        "package": "@sourcegraph/amp",
        "binary": "amp",
        "version_cmd": ["amp", "--version"],
        "config_dir": "~/.config/amp",
        "instruction_file": "AGENTS.md",
        "skills_dir": "~/.config/amp/skills/{name}/SKILL.md",
        "hooks_support": False,
        "deny_rules_format": None,
        "mcp_format": "amp",
        "vscode_extension": None,
        "jai_conf": "amp.conf",
        "jai_env_keys": ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"],
    },
}

PRESETS: dict[str, list[str]] = {
    "core": ["claude", "codex", "opencode", "pi"],
    "all": list(AGENTS.keys()),
}


def agents_with_vscode_ext(agent_keys: list[str]) -> list[tuple[str, str]]:
    """Return (agent_key, extension_id) pairs for agents that have VSCode extensions."""
    return [
        (k, AGENTS[k]["vscode_extension"])
        for k in agent_keys
        if AGENTS[k].get("vscode_extension")
    ]
