"""``coding-agents vscode-reset`` — clear the cached VSCode SLURM session.

Reads the jobid cache written by ``runtime.agent_vscode``; best-effort
``scancel``s the job and removes the cache. Idempotent — no-op if there's
nothing to clear.
"""
from __future__ import annotations

import subprocess

from rich.console import Console

from coding_agents.runtime.agent_vscode import cache_path, read_cache

console = Console()


def run_vscode_reset() -> int:
    cache_p = cache_path()
    state = read_cache(cache_p)
    if state is None:
        console.print("[dim]No VSCode SLURM session cache found — nothing to do.[/dim]")
        return 0

    job_id = state.get("job_id")
    if job_id:
        try:
            result = subprocess.run(
                ["scancel", str(job_id)],
                capture_output=True, text=True, timeout=15, check=False,
            )
            if result.returncode == 0:
                console.print(f"[green]✓[/green] scancel {job_id}")
            else:
                console.print(
                    f"[yellow]⚠ scancel {job_id} rc={result.returncode}: "
                    f"{result.stderr.strip()}[/yellow]"
                )
        except (OSError, subprocess.TimeoutExpired) as exc:
            console.print(f"[yellow]⚠ scancel failed: {exc}[/yellow]")

    try:
        cache_p.unlink()
        console.print(f"[green]✓[/green] removed {cache_p}")
    except FileNotFoundError:
        pass
    except OSError as exc:
        console.print(f"[red]✗ could not remove {cache_p}: {exc}[/red]")
        return 1
    return 0
