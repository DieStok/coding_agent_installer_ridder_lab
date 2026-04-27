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
    # Note: the lab cwd-policy is enforced only at agent-invocation time
    # by the wrapper's bash check (bundled/templates/wrapper/agent.template.sh).
    # We deliberately do NOT warn here — `coding-agents install` and the
    # other subcommands are admin/setup operations, not agent runs, so
    # the directory convention doesn't apply.

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
    exclude: str = typer.Option(
        "",
        "--exclude",
        help=(
            "Comma-separated list of agents to skip entirely (no install_cmd, no wrapper, "
            "no agent-specific managed-settings emit). Example: --exclude claude,codex. "
            "Useful when developing this installer against your own working agent install."
        ),
    ),
    developer: bool = typer.Option(
        False,
        "--developer",
        help=(
            "Show the full skills/hooks/tools pickers so you can customize what gets "
            "installed. Without this flag the TUI is a one-stop-shop and just shows "
            "you the lab default lists with links, with no per-item toggles."
        ),
    ),
) -> None:
    """Interactive TUI installer for coding agents."""
    import sys

    # Validate --exclude FIRST so scripted callers get the right error message.
    excluded = {a.strip() for a in exclude.split(",") if a.strip()}
    if excluded:
        from coding_agents.agents import AGENTS
        unknown = excluded - set(AGENTS.keys())
        if unknown:
            console.print(f"[red]Error:[/red] unknown agent(s) in --exclude: {sorted(unknown)}")
            console.print(f"Known agents: {sorted(AGENTS.keys())}")
            raise typer.Exit(2)
        console.print(f"[yellow]Excluding agents from install:[/yellow] {sorted(excluded)}")

    if developer:
        console.print("[yellow]Developer mode:[/yellow] full skills/hooks/tools pickers enabled.")

    if not sys.stdin.isatty():
        console.print("[red]Error:[/red] coding-agents install requires an interactive terminal.")
        raise typer.Exit(1)

    from coding_agents.installer.tui import CodingAgentsInstaller

    mode = "local" if local else "hpc"
    tui = CodingAgentsInstaller(mode=mode, excluded_agents=excluded, developer=developer)
    tui.run()

    # Print the next-steps list to the host terminal after the TUI tears
    # down — same content the user just saw in the NextStepsScreen, so they
    # can copy commands and click links from their normal terminal.
    if getattr(tui, "install_succeeded", False):
        from coding_agents.installer.next_steps import build_next_steps, render_terminal
        steps = build_next_steps(tui.state)
        print(render_terminal(steps))


@app.command()
def update() -> None:
    """Update all installed agents and tools to latest versions."""
    from coding_agents.commands.update import run_update

    run_update()


@app.command()
def sync(
    vscode_settings: str = typer.Option(
        "",
        "--vscode-settings",
        help=(
            "Explicit path to your VSCode/Cursor user settings.json. Use "
            "this when remote.SSH.serverInstallPath puts your VSCode-server "
            "outside the standard ~/.vscode-server/ location. Alternatively "
            "set $VSCODE_AGENT_FOLDER to the dir whose data/User/settings.json "
            "should be used."
        ),
    ),
) -> None:
    """Re-distribute shared config to all agent-native locations."""
    from coding_agents.commands.sync import run_sync

    run_sync(vscode_settings_path=vscode_settings or None)


@app.command()
def doctor(
    scan_cron: bool = typer.Option(
        False,
        "--scan-cron",
        help="Scan the user's crontab for bare CLI invocations (claude/codex/...)."
    ),
    scan_systemd: bool = typer.Option(
        False,
        "--scan-systemd",
        help="Scan systemd-user units for bare CLI invocations.",
    ),
) -> None:
    """Health check with color-coded pass/warn/fail and fix commands."""
    from coding_agents.commands.doctor import run_doctor

    raise typer.Exit(run_doctor(scan_cron=scan_cron, scan_systemd=scan_systemd))


@app.command(name="vscode-reset")
def vscode_reset() -> None:
    """Clear the cached VSCode SLURM session jobid (best-effort scancel)."""
    from coding_agents.commands.vscode_reset import run_vscode_reset

    raise typer.Exit(run_vscode_reset())


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
