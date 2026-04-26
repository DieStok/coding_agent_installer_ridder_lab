"""sync command — distribute shared config to all agent-native locations."""
from __future__ import annotations

import json
import logging
import shutil

_log = logging.getLogger("coding-agents")
from pathlib import Path

from rich.console import Console

from coding_agents.agents import AGENTS
from coding_agents.config import HOOK_SCRIPTS, load_config, get_install_dir
from coding_agents.convert_mcp import convert_mcp
from coding_agents.utils import safe_symlink

console = Console()


def run_sync() -> None:
    """Re-distribute all shared config to agent-native locations."""
    config = load_config()
    if not config.get("install_dir"):
        console.print("[red]No installation found. Run `coding-agents install` first.[/red]")
        return

    install_dir = get_install_dir(config)
    agents = config.get("agents", [])
    mode = config.get("mode", "hpc")
    home = Path.home()

    _log.info("run_sync: mode=%s, install_dir=%s, agents=%s", mode, install_dir, agents)
    console.print(f"[bold]Syncing configuration ({mode} mode)...[/bold]\n")

    _sync_agents_md(install_dir, agents, home)
    _sync_skills(install_dir, agents, config.get("skills", []))
    _sync_hooks(install_dir, agents, config.get("hooks", []))
    _sync_deny_rules(install_dir, agents)
    _sync_mcp(install_dir, agents)

    console.print("\n[green bold]Sync complete.[/green bold]")


def _sync_agents_md(install_dir: Path, agents: list[str], home: Path) -> None:
    """Symlink shared AGENTS.md to each agent's config dir."""
    console.print("[bold]AGENTS.md distribution:[/bold]")
    source = install_dir / "config" / "AGENTS.md"
    if not source.exists():
        console.print("  [yellow]AGENTS.md not found in install dir[/yellow]")
        return

    for key in agents:
        agent = AGENTS.get(key)
        if not agent:
            continue
        config_dir = Path(agent["config_dir"]).expanduser()
        config_dir.mkdir(parents=True, exist_ok=True)
        target = config_dir / agent["instruction_file"]
        safe_symlink(source, target)
        console.print(f"  [green]✓[/green] {target}")


def _sync_skills(install_dir: Path, agents: list[str], skills: list[str]) -> None:
    """Symlink skills to each agent's native skill directory."""
    console.print("[bold]Skills distribution:[/bold]")
    skills_dir = install_dir / "skills"

    for key in agents:
        agent = AGENTS.get(key)
        if not agent or not agent.get("skills_dir"):
            continue
        for skill_name in skills:
            skill_src = skills_dir / skill_name
            if not skill_src.exists():
                continue

            # Find the SKILL.md file — check common locations
            skill_md = None
            for candidate in [
                skill_src / "SKILL.md",
                skill_src / f".claude/skills/{skill_name}/SKILL.md",
                skill_src / f".agents/skills/{skill_name}/SKILL.md",
            ]:
                if candidate.exists():
                    skill_md = candidate
                    break

            if not skill_md:
                continue

            # Expand the target path template
            target_pattern = agent["skills_dir"]
            target = Path(target_pattern.replace("{name}", skill_name)).expanduser()
            target.parent.mkdir(parents=True, exist_ok=True)
            safe_symlink(skill_md, target)
            console.print(f"  [green]✓[/green] {key}: {skill_name}")


def _sync_hooks(install_dir: Path, agents: list[str], hooks: list[str]) -> None:
    """Wire hooks into agents that support them, using marker-based merge."""
    console.print("[bold]Hooks wiring:[/bold]")

    for key in agents:
        agent = AGENTS.get(key)
        if not agent:
            continue

        if agent["hooks_support"] is True and key == "claude":
            _wire_claude_hooks(install_dir, hooks)
        elif agent["hooks_support"] == "experimental" and key == "codex":
            console.print(f"  [dim]Codex hooks: experimental, manual setup recommended[/dim]")


def _wire_claude_hooks(install_dir: Path, hooks: list[str]) -> None:
    """Merge hook definitions into ~/.claude/settings.json using merge_settings."""
    from coding_agents.config import build_hook_entries
    from coding_agents.merge_settings import merge_claude_hooks

    settings_path = Path.home() / ".claude" / "settings.json"
    hook_entries = build_hook_entries(install_dir, hooks)

    if not hook_entries:
        return

    results = merge_claude_hooks(settings_path, hook_entries)
    for r in results:
        console.print(f"  [green]✓[/green] Claude {r.section}: {r.summary()}")
        if r.preserved_keys:
            console.print(f"    [dim]Preserved {len(r.preserved_keys)} existing user hooks[/dim]")


def _sync_deny_rules(install_dir: Path, agents: list[str]) -> None:
    """Apply deny rules per agent's format."""
    console.print("[bold]Deny rules:[/bold]")
    deny_path = install_dir / "hooks" / "deny_rules.json"
    if not deny_path.exists():
        console.print("  [yellow]deny_rules.json not found[/yellow]")
        return

    deny_data = json.loads(deny_path.read_text())
    canonical_rules = deny_data.get("deny", [])

    for key in agents:
        agent = AGENTS.get(key)
        if not agent or not agent.get("deny_rules_format"):
            continue

        fmt = agent["deny_rules_format"]

        if fmt == "claude":
            _apply_claude_deny(canonical_rules)
            console.print(f"  [green]✓[/green] Claude Code deny rules")

        elif fmt == "starlark":
            _apply_codex_deny(canonical_rules)
            console.print(f"  [green]✓[/green] Codex Starlark deny rules")

        elif fmt == "opencode":
            console.print(f"  [dim]OpenCode deny rules: manual config recommended[/dim]")


def _apply_claude_deny(rules: list[str]) -> None:
    """Merge deny rules into ~/.claude/settings.json permissions.deny."""
    from coding_agents.merge_settings import merge_claude_deny_rules

    settings_path = Path.home() / ".claude" / "settings.json"
    r = merge_claude_deny_rules(settings_path, rules)
    if r.preserved_keys:
        console.print(f"    [dim]Preserved {len(r.preserved_keys)} existing deny rules[/dim]")


def _apply_codex_deny(rules: list[str]) -> None:
    """Generate Starlark deny rules from canonical list."""
    rules_dir = Path.home() / ".codex" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    rules_file = rules_dir / "deny.rules"

    lines = ["# Auto-generated deny rules for Codex CLI (coding-agents sync)"]
    for rule in rules:
        # Parse "Read(./path)" format
        if rule.startswith("Read(") and rule.endswith(")"):
            pattern = rule[5:-1]  # strip Read( and )
            lines.append(f'prefix_rule(')
            lines.append(f'    pattern = ["cat", "{pattern}"],')
            lines.append(f'    decision = "forbidden",')
            lines.append(f'    justification = "Reading {pattern} is denied by policy"')
            lines.append(f')')

    rules_file.write_text("\n".join(lines) + "\n")


def _sync_mcp(install_dir: Path, agents: list[str]) -> None:
    """Distribute MCP server configs."""
    console.print("[bold]MCP distribution:[/bold]")
    servers_json = install_dir / "config" / "mcp" / "servers.json"
    if not servers_json.exists():
        console.print("  [dim]No servers.json found — skipping MCP[/dim]")
        return

    written = convert_mcp(servers_json, agents)
    for path in written:
        console.print(f"  [green]✓[/green] {path}")

    if not written:
        console.print("  [dim]No MCP servers defined[/dim]")


