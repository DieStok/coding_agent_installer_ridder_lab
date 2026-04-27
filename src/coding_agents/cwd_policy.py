"""Lab cwd-policy checks (de Ridder lab convention).

Runs both at CLI top-level (warn-only — see ``check_cwd_warn_only``) and
at wrapper-invocation time (refusal + warning — implemented as bash in
``bundled/templates/wrapper/agent.template.sh``). The two paths share
the same set of refusal / warning conditions, kept in lockstep here as
the single source of truth for the policy.

Refusal conditions (wrapper-side; CLI-side warns instead):
  - $PWD under ``/hpc/compgen/users/shared/`` — read-only shared lab
    infrastructure (the SIF lives there). Working agents inside this
    tree is almost always either an accident or a precursor to writing
    over the shared SIF.
  - $PWD == ``/hpc/compgen/projects`` (the bare projects root) — work
    belongs in a specific project subdir.
  - $PWD == ``/hpc/compgen/projects/<project>`` (project root with no
    deeper subdir) — same; cd into ``analysis/$USER/`` or a subproject.

Warning condition (both sides):
  - $PWD has no path component matching $USER — lab convention is that
    everyone works under their own subdir, e.g.
    ``/hpc/compgen/projects/<project>/<subproject>/analysis/$USER/``.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

# Public type for callers that want to differentiate the result.
PolicyVerdict = Literal["ok", "warn", "refuse"]

_SHARED_PREFIX = "/hpc/compgen/users/shared"
_PROJECTS_ROOT = "/hpc/compgen/projects"


def _under(path: str, prefix: str) -> bool:
    """True iff path equals prefix or is a strict subdirectory of it."""
    p = path.rstrip("/")
    pre = prefix.rstrip("/")
    return p == pre or p.startswith(pre + "/")


def evaluate(
    cwd: str | Path | None = None,
    user: str | None = None,
) -> tuple[PolicyVerdict, str]:
    """Return ``(verdict, message)`` for the given cwd / user.

    ``verdict``:
      - ``"refuse"`` — cwd is in a forbidden location.
      - ``"warn"``   — cwd is fine but worth flagging (no $USER component).
      - ``"ok"``     — cwd is fine.

    ``message`` is the human-readable explanation, empty when verdict is
    ``"ok"``.
    """
    cwd_str = str(Path(cwd).resolve()) if cwd is not None else os.getcwd()
    user_str = user if user is not None else os.environ.get("USER", "")

    # Shared lab infrastructure — refuse.
    if _under(cwd_str, _SHARED_PREFIX):
        return (
            "refuse",
            f"cwd '{cwd_str}' is under {_SHARED_PREFIX} (shared lab "
            f"infrastructure — the SIF lives here, not a user workspace). "
            f"Cd into your own analysis dir (e.g. "
            f"/hpc/compgen/projects/<project>/<subproject>/analysis/"
            f"{user_str or '$USER'}/) and retry.",
        )

    # Projects tree refusal: must be in a subdir of a specific project,
    # not at the bare projects root or a project root with no further
    # subdir.
    if cwd_str == _PROJECTS_ROOT or cwd_str == _PROJECTS_ROOT + "/":
        return (
            "refuse",
            f"cwd is the bare /hpc/compgen/projects root. Cd into a "
            f"specific project subdir (e.g. /hpc/compgen/projects/"
            f"<project>/<subproject>/analysis/{user_str or '$USER'}/) "
            f"and retry.",
        )
    if cwd_str.startswith(_PROJECTS_ROOT + "/"):
        # /hpc/compgen/projects/<project>/<more>... — count parts after
        # /hpc/compgen/projects/. Must be ≥ 2 (project + at least one
        # subdir under it).
        rest = cwd_str[len(_PROJECTS_ROOT) + 1 :]
        parts = [p for p in rest.split("/") if p]
        if len(parts) < 2:
            return (
                "refuse",
                f"cwd '{cwd_str}' is a project root with no subdir under "
                f"it. Work belongs in a subdir of the project (e.g. "
                f"analysis/{user_str or '$USER'}/, or a subproject). "
                f"Cd deeper and retry.",
            )

    # Soft warning: $USER not a path component of cwd.
    if user_str:
        components = {c for c in cwd_str.split("/") if c}
        if user_str not in components:
            return (
                "warn",
                f"cwd '{cwd_str}' has no path component '{user_str}'. "
                f"Lab convention: work in your own subdir, e.g. "
                f"/hpc/compgen/projects/<project>/<subproject>/analysis/"
                f"{user_str}/. Continuing anyway.",
            )

    return ("ok", "")


def check_cwd_warn_only() -> None:
    """CLI-side: never refuse — print a yellow warning to the user's
    console for both ``warn`` and ``refuse`` verdicts. The wrapper-side
    bash check (in ``bundled/templates/wrapper/agent.template.sh``)
    enforces the refusal at agent-invocation time.

    No-op when not running under the de Ridder lab HPC paths (e.g.
    local-mode installs on a developer's Mac).
    """
    from rich.console import Console

    cwd = os.getcwd()
    # Cheap guard: if we're not inside /hpc/compgen at all, the lab
    # policy doesn't apply. CLI runs on Macs / local Linux for testing
    # shouldn't bother the user.
    if not cwd.startswith("/hpc/compgen"):
        return

    verdict, message = evaluate(cwd=cwd)
    if verdict == "ok":
        return

    console = Console()
    if verdict == "refuse":
        console.print(
            f"[yellow]⚠ Lab cwd-policy:[/yellow] {message}\n"
            f"[dim]This is a CLI-side warning only — when you run an agent via "
            f"agent-<name> the wrapper will refuse outright (exit 12).[/dim]"
        )
    else:  # warn
        console.print(f"[yellow]⚠ Lab cwd-policy:[/yellow] {message}")
