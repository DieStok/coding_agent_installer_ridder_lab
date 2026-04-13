"""CLI entrypoint — Typer app with 6 subcommands."""
from __future__ import annotations

import atexit

import typer
from rich.console import Console

app = typer.Typer(
    name="coding-agents",
    no_args_is_help=True,
)
console = Console()


def _summary_atexit() -> None:
    """Emit the dry-run summary at process exit — covers both the sync
    command paths and the async TUI path without plumbing it through every
    subcommand."""
    from coding_agents.dry_run import emit_summary, is_dry_run

    if is_dry_run():
        emit_summary()


atexit.register(_summary_atexit)


@app.callback()
def main(
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable comprehensive debug logging to stderr and log file.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Walk through every step without making any changes. Implies --debug.",
    ),
) -> None:
    """Cross-agent configuration and installer for AI coding agents."""
    if not (debug or dry_run):
        return

    from coding_agents.config import load_config, get_install_dir
    from coding_agents.dry_run import set_dry_run
    from coding_agents.logging_setup import configure_logging

    config = load_config()
    log_dir = None
    if config.get("install_dir"):
        log_dir = get_install_dir(config) / "logs"
    log_file = configure_logging(debug=debug, log_dir=log_dir, dry_run=dry_run)
    if dry_run:
        set_dry_run(True)
    if log_file:
        tag = "Dry-run log" if dry_run else "Debug log"
        console.print(f"[dim]{tag}: {log_file}[/dim]")
    if dry_run:
        console.print(
            "[bold yellow]DRY-RUN MODE — NO CHANGES WILL BE MADE[/bold yellow]"
        )


@app.command()
def install(
    local: bool = typer.Option(False, "--local", help="Install for local Mac/Linux instead of HPC cluster."),
) -> None:
    """Interactive TUI installer for coding agents."""
    import sys

    if not sys.stdin.isatty():
        console.print("[red]Error:[/red] coding-agents install requires an interactive terminal.")
        raise typer.Exit(1)

    from coding_agents.installer.tui import CodingAgentsInstaller

    mode = "local" if local else "hpc"
    tui = CodingAgentsInstaller(mode=mode)
    tui.run()


@app.command()
def update() -> None:
    """Update all installed agents and tools to latest versions."""
    from coding_agents.commands.update import run_update

    run_update()


@app.command()
def sync() -> None:
    """Re-distribute shared config to all agent-native locations."""
    from coding_agents.commands.sync import run_sync

    run_sync()


@app.command()
def doctor() -> None:
    """Health check with color-coded pass/warn/fail and fix commands."""
    from coding_agents.commands.doctor import run_doctor

    raise typer.Exit(run_doctor())


@app.command(name="project-init")
def project_init(
    path: str = typer.Argument(".", help="Project directory to initialize"),
) -> None:
    """Bootstrap a project directory with AGENTS.md, hooks, and agent configs."""
    from coding_agents.commands.project_init import run_project_init

    run_project_init(path)


@app.command()
def uninstall() -> None:
    """Clean removal of all installed components."""
    from coding_agents.commands.uninstall import run_uninstall

    run_uninstall()
