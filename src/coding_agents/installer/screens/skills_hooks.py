"""Step 5: Skills & hooks selection."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, SelectionList, Static

from coding_agents.installer.screens.install_dir import TOTAL_STEPS
from coding_agents.installer.state import InstallerState

SKILL_OPTIONS = [
    ("compound-engineering — brainstorm/plan/work/review workflow", "compound-engineering"),
    ("scientific-agent-skills — research-oriented agent skills", "scientific-agent-skills"),
    ("autoresearch — autonomous improvement engine (10 commands)", "autoresearch"),
    ("hpc-cluster — UMC Utrecht HPC reference (HPC mode only)", "hpc-cluster"),
]

HOOK_OPTIONS = [
    ("AGENTS.md check (SessionStart) — create AGENTS.md if missing", "agents_md_check"),
    ("Cognitive offloading reminder (SessionStart)", "cognitive_reminder"),
    ("Git repo check for entire (SessionStart)", "git_check"),
    ("Lint runner (Stop) — ruff, vulture, pyright, yamllint, shellcheck", "lint_runner"),
    ("HPC structure validator (Stop) — validates directory conventions", "hpc_validator"),
]


class SkillsHooksScreen(Screen):
    """Step 5 — Select skills and hooks to install."""

    def __init__(self, state: InstallerState) -> None:
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        with Vertical(id="step-container"):
            yield Label(f"Step 5 of {TOTAL_STEPS} — Skills & Hooks", classes="step-title")

            yield Static("Skills (shared across agents via symlinks):", classes="section-heading")
            yield SelectionList[str](
                *[
                    (label, value, value in self.state.skills)
                    for label, value in SKILL_OPTIONS
                ],
                id="skills-list",
            )

            yield Static("Hooks (agent lifecycle scripts):", classes="section-heading")
            yield SelectionList[str](
                *[
                    (label, value, value in self.state.hooks)
                    for label, value in HOOK_OPTIONS
                ],
                id="hooks-list",
            )

            with Horizontal(classes="nav"):
                yield Button("← Back", id="btn-back")
                yield Button("Next →", variant="primary", id="btn-next")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
        elif event.button.id == "btn-next":
            self.state.skills = list(self.query_one("#skills-list", SelectionList).selected)
            self.state.hooks = list(self.query_one("#hooks-list", SelectionList).selected)
            from coding_agents.installer.screens.review import ReviewScreen

            self.app.push_screen(ReviewScreen(self.state))
