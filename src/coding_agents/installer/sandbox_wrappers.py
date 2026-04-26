"""Sandbox wrapper renderer.

Pure-function module separated from `executor.py` so the rendering logic
is unit-testable without spinning up the TUI or the install loop.

The wrapper template lives at
``bundled/templates/wrapper/agent.template.sh`` and is interpolated via
explicit ``str.replace`` over a pinned variable list (``WRAPPER_VARS``).
A drift-detect test (``tests/test_wrappers.py``) asserts that the set of
``{{VAR}}`` placeholders in the template matches ``WRAPPER_VARS``
exactly — adding a new placeholder without updating the constant fails
the test.
"""
from __future__ import annotations

import re
from pathlib import Path

# Pinned set of template variables. Adding/removing here requires the same
# change in `agent.template.sh` and is enforced by test_wrappers.
WRAPPER_VARS: tuple[str, ...] = (
    "AGENT_DISPLAY_NAME",
    "AGENT_KEY",
    "AGENT_BINARY",
    "DEFAULT_SIF_PATH",
)

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


def _bundled_template_path() -> Path:
    """Resolve the bundled template path relative to this package."""
    return Path(__file__).resolve().parent.parent / "bundled" / "templates" / "wrapper" / "agent.template.sh"


def load_template() -> str:
    """Return the wrapper template source as text."""
    return _bundled_template_path().read_text()


def template_placeholders(template: str) -> set[str]:
    """Return the set of ``{{VAR}}`` placeholders found in the template."""
    return set(_PLACEHOLDER_RE.findall(template))


def render_wrapper(
    template: str,
    *,
    agent_key: str,
    agent_display_name: str,
    agent_binary: str,
    default_sif_path: str,
) -> str:
    """Interpolate the template with explicit, ordered substitutions.

    Uses ``str.replace`` rather than ``.format`` to avoid accidental
    formatting on stray ``{}`` characters in the bash source. Order is
    deterministic for byte-identical idempotent re-renders.
    """
    values: dict[str, str] = {
        "AGENT_DISPLAY_NAME": agent_display_name,
        "AGENT_KEY": agent_key,
        "AGENT_BINARY": agent_binary,
        "DEFAULT_SIF_PATH": default_sif_path,
    }
    # Drift guard: refuse to render if a known var is missing a value.
    missing = set(WRAPPER_VARS) - values.keys()
    if missing:
        raise ValueError(f"render_wrapper missing values for: {sorted(missing)}")
    out = template
    for name in WRAPPER_VARS:
        out = out.replace("{{" + name + "}}", values[name])
    return out
