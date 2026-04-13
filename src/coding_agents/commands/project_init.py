"""project-init command — bootstrap a project directory with agent configs."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from rich.console import Console

from coding_agents.agents import AGENTS, agents_with_vscode_ext
from coding_agents.config import HOOK_SCRIPTS, load_config, get_install_dir

console = Console()


def run_project_init(project_path: str = ".") -> None:
    """Bootstrap a project directory with AGENTS.md, hooks, and agent configs."""
    import sys

    config = load_config()
    if not config.get("install_dir"):
        console.print("[red]No installation found. Run `coding-agents install` first.[/red]")
        return

    install_dir = get_install_dir(config)
    project = Path(project_path).resolve()
    agents = config.get("agents", [])
    hooks = config.get("hooks", [])

    # Check for existing configs — if found and interactive, open merge TUI
    from coding_agents.detect_existing import scan_project_existing

    existing = scan_project_existing(project)
    has_existing = any(v for v in existing.values())

    if has_existing and sys.stdin.isatty():
        selected_keys = _run_merge_tui(project, install_dir, agents, hooks)
        if selected_keys is None:
            console.print("[dim]Cancelled.[/dim]")
            return
        # Only create items the user selected
        _apply_selected(selected_keys, install_dir, project, agents, hooks, config)
        return

    console.print(f"[bold]Initializing project: {project}[/bold]\n")

    # No existing configs or non-interactive — proceed normally
    # 1. Create AGENTS.md from template
    _create_agents_md(install_dir, project)

    # 2. Create instruction file symlinks
    _create_instruction_symlinks(project)

    # 3. Create per-agent project configs
    _create_agent_configs(install_dir, project, agents, hooks)

    # 4. Update .gitignore
    _update_gitignore(project)

    # 5. Offer git init + entire init if needed
    _check_git_entire(project, config)

    # 6. VSCode extensions.json
    if config.get("vscode_extensions"):
        _create_vscode_extensions(project, agents)

    console.print(f"\n[green bold]Project initialized at {project}[/green bold]")
    console.print("Run [bold]coding-agents doctor[/bold] to verify your setup.")


def _create_agents_md(install_dir: Path, project: Path) -> None:
    """Copy AGENTS.md template, substituting placeholders."""
    template_path = install_dir / "config" / "templates" / "PROJECT_LOCAL_AGENTS_TEMPLATE.md"
    agents_md = project / "AGENTS.md"

    if agents_md.exists():
        console.print("  [dim]AGENTS.md already exists, skipping[/dim]")
        return

    if not template_path.exists():
        console.print("  [yellow]Template not found, creating minimal AGENTS.md[/yellow]")
        agents_md.write_text(f"# Project: {project.name}\n\n> Edit this file to guide AI coding agents.\n")
        return

    content = template_path.read_text()
    content = content.replace("{PROJECT_NAME}", project.name)
    content = content.replace("{USERNAME}", os.environ.get("USER", "unknown"))
    agents_md.write_text(content)
    console.print("  [green]✓[/green] AGENTS.md created from template")


def _create_instruction_symlinks(project: Path) -> None:
    """Create CLAUDE.md and GEMINI.md symlinks pointing to AGENTS.md."""
    agents_md = project / "AGENTS.md"
    if not agents_md.exists():
        return

    for name in ["CLAUDE.md", "GEMINI.md"]:
        target = project / name
        if target.exists():
            continue
        try:
            target.symlink_to("AGENTS.md")
            console.print(f"  [green]✓[/green] {name} → AGENTS.md")
        except OSError:
            console.print(f"  [yellow]Could not create {name} symlink[/yellow]")


def _create_agent_configs(
    install_dir: Path, project: Path, agents: list[str], hooks: list[str]
) -> None:
    """Create per-agent project config stubs with absolute hook paths."""
    for key in agents:
        agent = AGENTS.get(key)
        if not agent:
            continue

        if key == "claude":
            _create_claude_project_config(install_dir, project, hooks)
        elif key == "codex":
            _create_codex_project_config(project)
        elif key == "pi":
            _create_pi_project_config(project)
        elif key == "opencode":
            _create_opencode_project_config(project)


def _create_claude_project_config(
    install_dir: Path, project: Path, hooks: list[str]
) -> None:
    """Create .claude/settings.json with hooks using absolute paths."""
    config_dir = project / ".claude"
    config_dir.mkdir(exist_ok=True)
    settings_path = config_dir / "settings.json"

    if settings_path.exists():
        console.print("  [dim].claude/settings.json already exists[/dim]")
        return

    # Build hooks with absolute paths, grouped by event
    from coding_agents.config import build_hook_entries

    all_entries = build_hook_entries(install_dir, hooks)
    hook_entries: dict[str, list] = {}
    for entry in all_entries:
        cmd = entry["hooks"][0]["command"]
        if "on_start_" in cmd:
            hook_entries.setdefault("SessionStart", []).append(entry)
        elif "on_stop_" in cmd:
            hook_entries.setdefault("Stop", []).append(entry)

    settings = {"hooks": hook_entries}
    from coding_agents.utils import secure_write_text
    secure_write_text(settings_path, json.dumps(settings, indent=2) + "\n")
    console.print("  [green]✓[/green] .claude/settings.json (with absolute hook paths)")


def _create_codex_project_config(project: Path) -> None:
    """Create .codex/config.toml stub."""
    config_dir = project / ".codex"
    config_dir.mkdir(exist_ok=True)
    config_path = config_dir / "config.toml"
    if config_path.exists():
        return
    config_path.write_text(
        "# Codex CLI project config\n"
        "# See: https://developers.openai.com/codex/config-reference\n"
    )
    console.print("  [green]✓[/green] .codex/config.toml")


def _create_pi_project_config(project: Path) -> None:
    """Create .pi/settings.json stub."""
    config_dir = project / ".pi"
    config_dir.mkdir(exist_ok=True)
    config_path = config_dir / "settings.json"
    if config_path.exists():
        return
    config_path.write_text(json.dumps({"project": project.name}, indent=2) + "\n")
    console.print("  [green]✓[/green] .pi/settings.json")


def _create_opencode_project_config(project: Path) -> None:
    """Create opencode.json stub."""
    config_path = project / "opencode.json"
    if config_path.exists():
        return
    config_path.write_text(json.dumps({"project": project.name}, indent=2) + "\n")
    console.print("  [green]✓[/green] opencode.json")


def _update_gitignore(project: Path) -> None:
    """Append agent directories to .gitignore."""
    gitignore = project / ".gitignore"
    entries = [
        ".claude/",
        ".codex/",
        ".pi/",
        ".opencode/",
        ".gemini/",
        ".entire/",
    ]

    existing = ""
    if gitignore.exists():
        existing = gitignore.read_text()

    new_entries = [e for e in entries if e not in existing]
    if not new_entries:
        return

    with open(gitignore, "a") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write("\n# Agent configuration directories\n")
        for entry in new_entries:
            f.write(entry + "\n")
    console.print("  [green]✓[/green] .gitignore updated")


def _check_git_entire(project: Path, config: dict) -> None:
    """If entire is installed and no .git/, suggest git init."""
    if (project / ".git").exists():
        return

    if "entire" not in config.get("tools", []):
        return

    console.print(
        "\n  [yellow]No .git/ found. `entire` session recording requires a git repo.[/yellow]"
    )
    console.print("  Run: git init && entire init")


def _create_vscode_extensions(project: Path, agents: list[str]) -> None:
    """Create .vscode/extensions.json with recommended extensions."""
    vscode_dir = project / ".vscode"
    vscode_dir.mkdir(exist_ok=True)
    ext_path = vscode_dir / "extensions.json"

    if ext_path.exists():
        console.print("  [dim].vscode/extensions.json already exists[/dim]")
        return

    exts = agents_with_vscode_ext(agents)
    recommendations = [ext_id for _, ext_id in exts]

    data = {"recommendations": recommendations}
    ext_path.write_text(json.dumps(data, indent=2) + "\n")
    console.print("  [green]✓[/green] .vscode/extensions.json")


def _run_merge_tui(
    project: Path, install_dir: Path, agents: list[str], hooks: list[str]
) -> list[str] | None:
    """Open the merge TUI and return selected keys, or None if cancelled."""
    from coding_agents.installer.project_init_tui import (
        ProjectInitMergeApp,
        build_merge_items,
    )

    items = build_merge_items(project, install_dir, agents, hooks)
    app = ProjectInitMergeApp(items)
    app.run()

    if app.result.cancelled:
        return None
    return app.result.selected_keys


def _apply_selected(
    selected_keys: list[str],
    install_dir: Path,
    project: Path,
    agents: list[str],
    hooks: list[str],
    config: dict,
) -> None:
    """Apply only the user-selected items from the merge TUI."""
    console.print(f"[bold]Applying selected items to {project}...[/bold]\n")

    if "agents_md" in selected_keys:
        _create_agents_md(install_dir, project)

    if "claude_md_symlink" in selected_keys:
        target = project / "CLAUDE.md"
        if not target.exists():
            try:
                target.symlink_to("AGENTS.md")
                console.print("  [green]✓[/green] CLAUDE.md → AGENTS.md")
            except OSError:
                pass

    if "gemini_md_symlink" in selected_keys:
        target = project / "GEMINI.md"
        if not target.exists():
            try:
                target.symlink_to("AGENTS.md")
                console.print("  [green]✓[/green] GEMINI.md → AGENTS.md")
            except OSError:
                pass

    if "claude_settings" in selected_keys and "claude" in agents:
        # Use merge_settings for smart merge
        from coding_agents.config import build_hook_entries
        from coding_agents.merge_settings import merge_claude_hooks

        settings_path = project / ".claude" / "settings.json"
        settings_path.parent.mkdir(exist_ok=True)
        hook_entries = build_hook_entries(install_dir, hooks)
        if hook_entries:
            results = merge_claude_hooks(settings_path, hook_entries)
            for r in results:
                console.print(f"  [green]✓[/green] .claude/settings.json {r.section}: {r.summary()}")

    if "codex_config" in selected_keys and "codex" in agents:
        _create_codex_project_config(project)

    if "pi_settings" in selected_keys and "pi" in agents:
        _create_pi_project_config(project)

    if "opencode_json" in selected_keys and "opencode" in agents:
        _create_opencode_project_config(project)

    if "gitignore" in selected_keys:
        _update_gitignore(project)

    if "vscode_extensions" in selected_keys:
        _create_vscode_extensions(project, agents)

    _check_git_entire(project, config)
    console.print(f"\n[green bold]Project initialized at {project}[/green bold]")


    # _build_hook_entries is now imported from config.py
