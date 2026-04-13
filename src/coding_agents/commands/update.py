"""update command — update all installed agents and tools to latest versions."""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

_log = logging.getLogger("coding-agents")

from rich.console import Console
from rich.table import Table

from coding_agents.agents import AGENTS
from coding_agents.config import GIT_SKILLS, load_config, get_install_dir
from coding_agents.utils import npm_install, run, uv_pip_install

console = Console()


def run_update() -> None:
    """Update all installed agents and tools, then re-run sync."""
    config = load_config()
    if not config.get("install_dir"):
        console.print("[red]No installation found. Run `coding-agents install` first.[/red]")
        return

    install_dir = get_install_dir(config)
    agents = config.get("agents", [])
    tools = config.get("tools", [])
    skills = config.get("skills", [])

    _log.info("run_update: install_dir=%s, agents=%s, tools=%s", install_dir, agents, tools)
    console.print("[bold]Updating coding-agents components...[/bold]\n")

    versions: list[tuple[str, str, str]] = []

    # --- Update agents ---
    for key in agents:
        agent = AGENTS.get(key)
        if not agent:
            continue

        before = _get_version(agent)
        try:
            _update_agent(key, agent, install_dir)
        except Exception as exc:
            console.print(f"  [red]✗ {agent['display_name']}: {exc}[/red]")
            versions.append((agent["display_name"], before, f"ERROR: {exc}"))
            continue
        after = _get_version(agent)
        versions.append((agent["display_name"], before, after))
        console.print(f"  [green]✓[/green] {agent['display_name']}")

    # --- Update tools ---
    venv_path = install_dir / "tools" / ".venv"
    if "linters" in tools and venv_path.exists():
        console.print("\n[bold]Updating linters...[/bold]")
        try:
            uv_pip_install(
                venv_path, ["ruff", "vulture", "pyright", "yamllint"], upgrade=True
            )
            console.print("  [green]✓[/green] Python linters updated")
        except Exception as exc:
            console.print(f"  [red]✗ Linters: {exc}[/red]")

    if "crawl4ai" in tools and venv_path.exists():
        console.print("[bold]Updating crawl4ai...[/bold]")
        try:
            uv_pip_install(venv_path, ["crawl4ai"], upgrade=True)
            console.print("  [green]✓[/green] crawl4ai updated")
        except Exception as exc:
            console.print(f"  [red]✗ crawl4ai: {exc}[/red]")

    if "agent-browser" in tools:
        console.print("[bold]Updating agent-browser...[/bold]")
        try:
            tools_dir = install_dir / "tools"
            npm_install(tools_dir, "agent-browser@latest")
            console.print("  [green]✓[/green] agent-browser updated")
        except Exception as exc:
            console.print(f"  [red]✗ agent-browser: {exc}[/red]")

    if "entire" in tools:
        entire_bin = shutil.which("entire")
        if entire_bin:
            console.print("[bold]Updating entire...[/bold]")
            try:
                run(["entire", "update"], check=False)
                console.print("  [green]✓[/green] entire updated")
            except Exception:
                console.print("  [dim]entire update not supported, skipping[/dim]")

    # --- Update skills (git pull) ---
    console.print("\n[bold]Updating skills...[/bold]")
    for skill in skills:
        if skill in GIT_SKILLS:
            skill_dir = install_dir / "skills" / skill
            if skill_dir.exists() and (skill_dir / ".git").exists():
                try:
                    run(
                        ["git", "-C", str(skill_dir), "pull", "--ff-only"],
                        check=False,
                    )
                    console.print(f"  [green]✓[/green] {skill}")
                except Exception as exc:
                    console.print(f"  [yellow]{skill}: {exc}[/yellow]")
            else:
                console.print(f"  [dim]{skill} not installed, skipping[/dim]")

    # --- Show version diff ---
    if versions:
        console.print()
        table = Table(title="Version Changes")
        table.add_column("Agent")
        table.add_column("Before")
        table.add_column("After")
        for name, before, after in versions:
            changed = before != after
            style = "green" if changed else "dim"
            table.add_row(name, before, f"[{style}]{after}[/{style}]")
        console.print(table)

    # --- Re-run sync ---
    console.print("\n[bold]Running sync...[/bold]")
    from coding_agents.commands.sync import run_sync

    run_sync()

    console.print("\n[green bold]Update complete.[/green bold]")


def _get_version(agent: dict) -> str:
    """Get current version string for an agent."""
    try:
        result = subprocess.run(
            agent["version_cmd"], capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip().split("\n")[0][:40]
    except Exception:
        return "unknown"


def _update_agent(key: str, agent: dict, install_dir: Path) -> None:
    """Update a single agent to latest."""
    method = agent["method"]

    if method == "npm":
        npm_install(install_dir, f"{agent['package']}@latest")

    elif method == "curl" and key == "claude":
        # Claude Code has its own update mechanism
        update_cmd = agent.get("update_cmd")
        if update_cmd:
            run(update_cmd, check=False)
        else:
            # Re-run install script
            run(
                ["bash", "-c", agent["install_cmd"]],
                check=False,
            )
