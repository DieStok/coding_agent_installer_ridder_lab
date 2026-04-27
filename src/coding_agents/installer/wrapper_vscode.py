"""Emit the per-extension VSCode stubs and the shared agent-vscode helper.

These bash stubs are bound to the extension's settings.json hook (or to the
PATH-prefix shim for OpenCode). Each stub is a 3-liner that ``exec``s the
shared Python helper. Keeping the stub thin means salloc/cache logic only
lives in one place — see ``runtime/agent_vscode.py``.

Phase 1 emits only the Pi stub. Phases 2–4 add Claude, Codex, OpenCode (and
the OpenCode path-shim symlink).
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

log = logging.getLogger("coding-agents")


# Bash stubs — keep ASCII-only, no argv quoting trickery. ``$@`` carries the
# extension's original argv unchanged; the Python helper then forwards that
# argv to ``agent-<n>`` after ``-- ``.
# `readlink -f` resolves symlinks so the OpenCode path-shim
# (bin/path-shim/opencode → ../agent-opencode-vscode) finds
# agent-vscode in bin/, not in path-shim/. The fallback to $0
# keeps the non-symlinked case (direct invocation via VSCode
# settings.json) working on systems without GNU readlink.
_STUB = (
    '#!/usr/bin/env bash\n'
    'SELF="$(readlink -f "$0" 2>/dev/null || echo "$0")"\n'
    'exec "$(dirname "$SELF")/agent-vscode" --agent {agent} -- "$@"\n'
)
EXTENSION_STUBS: dict[str, str] = {
    "pi": _STUB.format(agent="pi"),
    "claude": _STUB.format(agent="claude"),
    "codex": _STUB.format(agent="codex"),
    "opencode": _STUB.format(agent="opencode"),
}


def _stub_path(install_dir: Path, agent: str) -> Path:
    return install_dir / "bin" / f"agent-{agent}-vscode"


def emit_extension_stubs(install_dir: Path, agents: list[str] | None = None) -> list[Path]:
    """Write per-extension wrapper stubs under ``<install_dir>/bin/``.

    Returns the list of paths written. ``agents`` defaults to all four
    supported agents; pass a subset for phased rollouts.
    """
    if agents is None:
        agents = list(EXTENSION_STUBS.keys())

    bin_dir = install_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for agent in agents:
        if agent not in EXTENSION_STUBS:
            log.warning("emit_extension_stubs: unknown agent %r — skipping", agent)
            continue
        path = _stub_path(install_dir, agent)
        path.write_text(EXTENSION_STUBS[agent])
        path.chmod(0o755)
        written.append(path)
    return written


def emit_agent_vscode_helper(install_dir: Path) -> Path:
    """Copy the runtime ``agent_vscode.py`` to ``<install_dir>/bin/agent-vscode``.

    The shebang already points at ``/usr/bin/env python3`` so no rewrite is
    needed. Sets the executable bit so it runs without ``python3`` prefix.
    """
    from coding_agents.runtime import agent_vscode as _agent_vscode_mod

    src = Path(_agent_vscode_mod.__file__)
    dst = install_dir / "bin" / "agent-vscode"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    dst.chmod(0o755)
    return dst


def emit_path_shim(install_dir: Path) -> Path:
    """Create ``<install_dir>/bin/path-shim/opencode`` symlink.

    The shim dir contains exactly one entry — ``opencode`` → the OpenCode
    extension stub. Putting the shim dir at the front of ``$PATH`` is what
    makes ``child_process.spawn("opencode")`` from the OpenCode extension
    resolve to our wrapper.
    """
    shim_dir = install_dir / "bin" / "path-shim"
    shim_dir.mkdir(parents=True, exist_ok=True)
    target = shim_dir / "opencode"
    if target.is_symlink() or target.exists():
        target.unlink()
    relative = Path("..") / "agent-opencode-vscode"
    os.symlink(relative, target)
    return target
