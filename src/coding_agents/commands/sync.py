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


def run_sync(vscode_settings_path: str | None = None) -> None:
    """Re-distribute all shared config to agent-native locations.

    ``vscode_settings_path`` overrides the resolver chain when the user's
    VSCode-server lives at a non-standard remote.SSH.serverInstallPath.
    """
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
    if mode != "local":
        _sync_vscode_wrapper_settings(install_dir, agents, vscode_settings_path)

    console.print("\n[green bold]Sync complete.[/green bold]")


def _sync_vscode_wrapper_settings(
    install_dir: Path,
    agents: list[str],
    explicit_path: str | None = None,
) -> None:
    """Re-emit wrapper hooks into VSCode settings.json.

    VSCode rewrites settings.json on certain UI actions; a periodic re-emit
    via ``coding-agents sync`` keeps our wrapper keys present afterwards.
    Idempotent — byte-identical output when nothing has drifted.

    Resolution order for the target file:
      1. ``explicit_path`` (--vscode-settings) — robust override.
      2. ``$VSCODE_AGENT_FOLDER/data/User/settings.json``.
      3. Standard chain: ~/.cursor-server/, ~/.vscode-server/, etc.

    If none of the above match, print the JSONC block to paste manually
    (the user is most likely on a custom remote.SSH.serverInstallPath, OR
    has VSCode Settings Sync hiding the file from the cluster filesystem).
    """
    wrappable = {"claude", "codex", "opencode", "pi"}
    selected = sorted(set(agents) & wrappable)
    if not selected:
        return
    console.print("[bold]VSCode wrapper hooks:[/bold]")
    from coding_agents.installer.policy_emit import (
        _vscode_wrapper_keys,
        emit_managed_vscode_settings,
    )
    target_arg = Path(explicit_path).expanduser() if explicit_path else None
    target = emit_managed_vscode_settings(
        install_dir, selected, target_settings_path=target_arg
    )
    if target is not None:
        console.print(f"  [green]✓[/green] re-emitted to {target}")
        return

    console.print(
        "  [yellow]⚠ No VSCode settings.json found on this host.[/yellow]"
    )
    console.print(
        "    [dim]The resolver checks both User and Machine scopes under "
        "~/.vscode-server/, ~/.cursor-server/, etc., AND under "
        "$VSCODE_AGENT_FOLDER (with .vscode-server/ / .cursor-server/ "
        "subdirs). Two common reasons it still didn't find anything:[/dim]\n"
        "    [dim]1. Custom remote.SSH.serverInstallPath — locate the file "
        "with[/dim]\n"
        "       [bold]find <serverInstallPath> -name settings.json -not -path '*/extensions/*'[/bold]\n"
        "       [dim]then re-run sync against it (Machine settings is the "
        "right scope for our wrapper keys, since per the VSCode docs "
        "machine-scoped settings are deliberately not cloud-synced):[/dim]\n"
        "       [bold]coding-agents sync --vscode-settings "
        "/path/to/data/Machine/settings.json[/bold]\n"
        "    [dim]2. VSCode Settings Sync — User settings live in cloud "
        "sync, but machine-scoped wrapper keys (chatgpt.cliExecutable, "
        "pi-vscode.path, terminal.integrated.env.linux) are explicitly NOT "
        "synced (per VSCode docs). Open the Command Palette while connected "
        "to the remote → 'Preferences: Open Remote Settings (JSON)' and "
        "paste the block below:[/dim]"
    )
    keys = _vscode_wrapper_keys(install_dir, selected)
    snippet = json.dumps(keys, indent=2)
    indented = "\n".join("    " + line for line in snippet.splitlines())
    console.print(f"\n[bold cyan]{indented}[/bold cyan]\n")
    console.print(
        "    [dim]After pasting + saving, the four sidebars route through "
        "the SIF wrapper. Re-run `coding-agents sync` to verify.[/dim]"
    )


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
            _wire_codex_hooks(install_dir, hooks)


def _wire_codex_hooks(install_dir: Path, hooks: list[str]) -> None:
    """Emit ~/.codex/hooks.json + set [features] codex_hooks = true.

    The Codex hooks API is marked experimental upstream; if a hook script
    misbehaves under Codex's stdin protocol, set ``[features] codex_hooks
    = false`` in ~/.codex/config.toml to disable.
    """
    from coding_agents.installer.policy_emit import install_codex_hooks
    target = install_codex_hooks(install_dir, hooks)
    if target is None:
        console.print("  [dim]Codex hooks: no SessionStart/Stop scripts mapped[/dim]")
        return
    console.print(f"  [green]✓[/green] Codex hooks: {target}")
    console.print(
        "    [dim]Apptainer's bind-mounts already constrain blast radius "
        "to the SIF; hooks add prompt-time checks on top.[/dim]"
    )


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

        elif fmt == "codex_toml":
            _apply_codex_deny(canonical_rules)
            console.print(f"  [green]✓[/green] Codex sandbox config")

        elif fmt == "opencode":
            _apply_opencode_permissions(canonical_rules)
            console.print(f"  [green]✓[/green] OpenCode permissions")
            console.print(
                "    [dim]Apptainer enforces a small blast radius via "
                "bind-mounts; the permission rules add ask/deny prompts "
                "on top so the agent can't run lab-banned commands "
                "(e.g. `rm -rf`, `chmod -R`) without your explicit OK.[/dim]"
            )


def _apply_opencode_permissions(rules: list[str]) -> None:
    """Write the lab-deny patterns into ~/.config/opencode/opencode.json."""
    from coding_agents.installer.policy_emit import install_opencode_permissions
    install_opencode_permissions(rules)


def _apply_claude_deny(rules: list[str]) -> None:
    """Merge deny rules into ~/.claude/settings.json permissions.deny."""
    from coding_agents.merge_settings import merge_claude_deny_rules

    settings_path = Path.home() / ".claude" / "settings.json"
    r = merge_claude_deny_rules(settings_path, rules)
    if r.preserved_keys:
        console.print(f"    [dim]Preserved {len(r.preserved_keys)} existing deny rules[/dim]")


def _apply_codex_deny(_rules: list[str]) -> None:
    """Refresh Codex sandbox config in ~/.codex/config.toml.

    Routes through ``policy_emit.install_codex_deny_paths`` (the install path)
    so the install and sync paths produce byte-identical output. The
    canonical_rules argument is unused — the install function reads
    deny_rules.json directly to stay aligned with the registry.

    Pre-Sprint 1, this function emitted a Starlark file at
    ~/.codex/rules/deny.rules — but Codex never read that path
    (synthesis §3.6). The install path was already writing the real
    [sandbox_workspace_write] schema; this just makes sync match.
    """
    from coding_agents.installer.policy_emit import install_codex_deny_paths

    deny_rules_path = (
        Path(__file__).resolve().parent.parent
        / "bundled" / "hooks" / "deny_rules.json"
    )
    target = Path.home() / ".codex" / "config.toml"
    install_codex_deny_paths(deny_rules_path, target)


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


