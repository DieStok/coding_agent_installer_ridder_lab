"""URL metadata for items shown on the tools / skills / hooks summary screens.

Single source of truth for the upstream homepage of every external skill,
tool, and hook the installer can pull in. Used by the read-only summary
screens (default mode) to render clickable links via Rich's Style(link=…)
API.

Each item is `(key, label, sub_links)` where `sub_links` is a list of
`(sub_label, url)` tuples:
  - empty list      → renders as "(internal)" — used for in-repo hook scripts
                      and the lab-shared hpc-cluster skill
  - one entry       → URL renders inline next to the label
  - multiple entries → label on its own line + indented sub-bullets, used
                       for composite items like "linters" that bundle
                       several upstream tools
"""
from __future__ import annotations

from rich.style import Style
from rich.text import Text

# (key, label, [(sub_label, url), …]) — order is the display order.
SKILLS: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("compound-engineering",   "compound-engineering — brainstorm/plan/work/review",
        [("compound-engineering-plugin", "https://github.com/EveryInc/compound-engineering-plugin")]),
    ("scientific-agent-skills","scientific-agent-skills — research-oriented agent skills",
        [("scientific-agent-skills", "https://github.com/K-Dense-AI/scientific-agent-skills")]),
    ("autoresearch",           "autoresearch — autonomous improvement engine",
        [("autoresearch", "https://github.com/uditgoenka/autoresearch")]),
    ("hpc-cluster",            "hpc-cluster — UMC Utrecht HPC reference (HPC mode only)",
        []),  # lab-internal share — no public URL
]

HOOKS: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("agents_md_check",    "agents_md_check (SessionStart) — create AGENTS.md if missing", []),
    ("cognitive_reminder", "cognitive_reminder (SessionStart) — anti-cognitive-offload",   []),
    ("git_check",          "git_check (SessionStart) — recommend git for entire-recorded sessions", []),
    ("lint_runner",        "lint_runner (Stop) — runs the lint tool set on changed files", []),
    ("hpc_validator",      "hpc_validator (Stop) — validates HPC directory conventions",    []),
]

TOOLS: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("linters", "linters — Python, JS/TS, YAML and shell quality tools", [
        ("ruff",       "https://github.com/astral-sh/ruff"),
        ("vulture",    "https://github.com/jendrikseipp/vulture"),
        ("pyright",    "https://github.com/microsoft/pyright"),
        ("yamllint",   "https://github.com/adrienverge/yamllint"),
        ("biome",      "https://github.com/biomejs/biome"),
        ("shellcheck", "https://github.com/koalaman/shellcheck"),
    ]),
    ("entire", "entire CLI — session recording for agent runs", [
        ("entireio/cli", "https://github.com/entireio/cli"),
    ]),
]


def _link(label: str, url: str) -> Text:
    """One clickable hyperlink — underlined bold accent text, OSC-8 backed."""
    return Text(label, style=Style(link=url, underline=True, bold=True))


def _item(label: str, sub_links: list[tuple[str, str]]) -> Text:
    """Render one item:
        • <label>   <url>                  if 1 sub-link
        • <label>                          if 0 sub-links
              (internal)
        • <label>                          if 2+ sub-links
              <sub_label>: <url>
              <sub_label>: <url>
              …
    """
    out = Text("  • ")
    out.append(label, style="bold")
    if not sub_links:
        out.append("    (internal)", style="dim")
        return out
    if len(sub_links) == 1:
        sub_label, url = sub_links[0]
        out.append("    ")
        out.append(_link(url, url))  # show the URL itself for single-link items
        return out
    for sub_label, url in sub_links:
        out.append("\n      ")
        out.append(sub_label, style="bold")
        out.append(": ", style="dim")
        out.append(_link(url, url))
    return out


def render_list(
    items: list[tuple[str, str, list[tuple[str, str]]]],
    selected: list[str] | None = None,
) -> Text:
    """Render an item list as a Rich Text with one bullet (and possibly
    indented sub-bullets) per item.

    `selected` filters to a subset (matched by key); pass None to render all.
    """
    keys = set(selected) if selected is not None else None
    out = Text()
    first = True
    for key, label, sub_links in items:
        if keys is not None and key not in keys:
            continue
        if not first:
            out.append("\n")
        first = False
        out.append(_item(label, sub_links))
    if first:
        out.append("(none selected)", style="dim italic")
    return out
