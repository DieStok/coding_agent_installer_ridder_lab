"""URL metadata for items shown on the tools / skills / hooks summary screens.

Single source of truth for the upstream homepage of every external skill,
tool, and hook the installer can pull in. Used by the read-only summary
screens (default mode) to render clickable links via Rich's Style(link=…)
API. Internal-only items (lab-shared skills, in-repo hook scripts) carry an
empty URL — the renderer falls back to a plain "(internal)" label.
"""
from __future__ import annotations

from rich.style import Style
from rich.text import Text

# (key, label, url) tuples — order is the display order.
SKILLS: list[tuple[str, str, str]] = [
    ("compound-engineering",  "compound-engineering — brainstorm/plan/work/review",     "https://github.com/EveryInc/compound-engineering-plugin"),
    ("scientific-agent-skills","scientific-agent-skills — research-oriented agent skills","https://github.com/K-Dense-AI/scientific-agent-skills"),
    ("autoresearch",          "autoresearch — autonomous improvement engine",            "https://github.com/uditgoenka/autoresearch"),
    ("hpc-cluster",           "hpc-cluster — UMC Utrecht HPC reference (HPC mode only)", ""),  # lab-internal share
]

HOOKS: list[tuple[str, str, str]] = [
    ("agents_md_check",   "agents_md_check (SessionStart) — create AGENTS.md if missing", ""),
    ("cognitive_reminder","cognitive_reminder (SessionStart) — anti-cognitive-offload",   ""),
    ("git_check",         "git_check (SessionStart) — recommend git for entire-recorded sessions", ""),
    ("lint_runner",       "lint_runner (Stop) — ruff / vulture / pyright / yamllint / shellcheck", ""),
    ("hpc_validator",     "hpc_validator (Stop) — validates HPC directory conventions",    ""),
]

TOOLS: list[tuple[str, str, str]] = [
    ("linters", "linters — ruff, vulture, pyright, yamllint, biome, shellcheck", "https://github.com/astral-sh/ruff"),
    ("entire",  "entire CLI — session recording for agent runs",                  "https://github.com/entireio/cli"),
]


def _line(label: str, url: str) -> Text:
    """One bullet line — bold label, then a clickable URL on the same line."""
    text = Text("  • ")
    text.append(label, style="bold")
    if url:
        text.append("    ")
        text.append(url, style=Style(link=url, underline=True, bold=True))
    else:
        text.append("    (internal)", style="dim")
    return text


def render_list(items: list[tuple[str, str, str]], selected: list[str] | None = None) -> Text:
    """Render an item list as a Rich Text with one bullet line per item.

    `selected` filters to a subset (matched by key); pass None to render all.
    Lines are joined with newlines.
    """
    keys = set(selected) if selected is not None else None
    out = Text()
    first = True
    for key, label, url in items:
        if keys is not None and key not in keys:
            continue
        if not first:
            out.append("\n")
        first = False
        out.append(_line(label, url))
    if first:
        out.append("(none selected)", style="dim italic")
    return out
