"""uninstall command — clean removal of all installed components."""
from __future__ import annotations

from pathlib import Path

from rich.console import Console

from coding_agents.agents import AGENTS
from coding_agents.config import CONFIG_PATH, load_config, get_install_dir
from coding_agents.dry_run import is_dry_run, would
from coding_agents.installer.fs_ops import dry_run_rmtree, dry_run_unlink
from coding_agents.utils import remove_shell_block

console = Console()


def run_uninstall() -> None:
    """Remove all coding-agents components, symlinks, and shell integration."""
    config = load_config()
    if not config.get("install_dir"):
        console.print("[yellow]No installation found (no ~/.coding-agents.json).[/yellow]")
        return

    install_dir = get_install_dir(config)
    agents = config.get("agents", [])
    home = Path.home()

    console.print("[bold]Uninstalling coding-agents...[/bold]\n")

    # 1. Remove symlinks from agent config dirs
    console.print("[bold]Removing agent config symlinks...[/bold]")
    for key in agents:
        agent = AGENTS.get(key)
        if not agent:
            continue

        config_dir = Path(agent["config_dir"]).expanduser()
        instr_file = config_dir / agent["instruction_file"]
        if instr_file.is_symlink():
            dry_run_unlink(instr_file)
            console.print(f"  [green]✓[/green] Removed {instr_file}")

        # Remove skill symlinks
        if agent.get("skills_dir"):
            skills_pattern = agent["skills_dir"]
            # Check for our symlinks in the skills dir
            skills_parent = Path(skills_pattern.split("{name}")[0]).expanduser()
            if skills_parent.exists():
                for item in skills_parent.iterdir():
                    if item.is_symlink() and str(install_dir) in str(item.resolve()):
                        dry_run_unlink(item)
                        console.print(f"  [green]✓[/green] Removed skill symlink {item}")

    # 2. Remove agent-* sandbox wrapper shims
    console.print("[bold]Removing agent-* sandbox wrappers...[/bold]")
    bin_dir = install_dir / "bin"
    if bin_dir.exists():
        for item in bin_dir.iterdir():
            if item.name.startswith("agent-") and item.is_file():
                dry_run_unlink(item)
                console.print(f"  [green]✓[/green] Removed {item}")

    # 3. Remove shell integration
    console.print("[bold]Removing shell integration...[/bold]")
    modified = remove_shell_block()
    for f in modified:
        console.print(f"  [green]✓[/green] Cleaned {f}")

    # 3b. VSCode wrapper hook cleanup — settings.json keys + jobid cache.
    # The user's settings.json keeps their non-managed keys; we set ours to
    # null so VSCode treats them as unset. The jobid cache + any live SLURM
    # session is cleared via the same path as `vscode-reset`.
    console.print("[bold]Removing VSCode wrapper hooks...[/bold]")
    try:
        from coding_agents.installer.policy_emit import unset_managed_vscode_settings
        from coding_agents.commands.vscode_reset import run_vscode_reset
        cleared = unset_managed_vscode_settings()
        if cleared is not None:
            console.print(f"  [green]✓[/green] Cleared wrapper keys in {cleared}")
        run_vscode_reset()
    except Exception as exc:
        console.print(f"  [yellow]⚠ VSCode wrapper cleanup partial: {exc}[/yellow]")

    # 4. Prompt to delete install dir (requires interactive terminal)
    import sys

    console.print(f"\n[bold yellow]Delete {install_dir}?[/bold yellow]")
    console.print("This removes all agents, tools, skills, and node_modules.")
    if is_dry_run():
        would(
            "prompt",
            "confirm_delete_install_dir",
            question="Type 'yes' to confirm",
            would_answer="no (dry-run default)",
        )
        answer = ""
    elif not sys.stdin.isatty():
        console.print("  [dim]Non-interactive — skipping install dir deletion[/dim]")
        answer = ""
    else:
        try:
            answer = input("Type 'yes' to confirm: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""

    if answer == "yes":
        console.print(f"Removing {install_dir} (this may take a moment for node_modules)...")
        try:
            dry_run_rmtree(install_dir)
            console.print(f"  [green]✓[/green] Deleted {install_dir}")
        except Exception as exc:
            console.print(f"  [red]✗ Failed to delete: {exc}[/red]")
    else:
        console.print(f"  [dim]Skipped — {install_dir} retained[/dim]")

    # 5. Remove config file
    if CONFIG_PATH.exists():
        dry_run_unlink(CONFIG_PATH)
        console.print(f"  [green]✓[/green] Removed {CONFIG_PATH}")

    console.print("\n[green bold]Uninstall complete.[/green bold]")
    console.print(
        "[dim]Note: Claude Code at ~/.claude/bin/ was not removed — "
        "run `claude uninstall` separately if needed.[/dim]"
    )
    console.print(
        "[dim]Project-level configs (.claude/settings.json in project dirs) "
        "were not removed — they may contain your customizations.[/dim]"
    )
