"""Step 5: Skills & hooks.

Two render modes:
  - default        info-only summary of the lab default skill+hook set,
                   with clickable links to upstream projects. No toggles.
  - --developer    full SelectionList pickers so you can customize.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, SelectionList, Static

from coding_agents.installer.screens._links import HOOKS, SKILLS, render_list
from coding_agents.installer.screens.install_dir import TOTAL_STEPS
from coding_agents.installer.state import InstallerState

SKILL_OPTIONS = [(label, key) for key, label, _url in SKILLS]
HOOK_OPTIONS = [(label, key) for key, label, _url in HOOKS]


class SkillsHooksScreen(Screen):
    """Step 5 — Skills & hooks."""

    def __init__(self, state: InstallerState) -> None:
        super().__init__()
        self.state = state

    def _is_developer(self) -> bool:
        return bool(getattr(self.app, "developer", False))

    def compose(self) -> ComposeResult:
        with Vertical(id="step-container"):
            yield Label(
                f"Step 5 of {TOTAL_STEPS} — Skills & Hooks",
                classes="step-title",
            )

            if self._is_developer():
                yield Static(
                    "[dim]--developer mode: full pickers.[/dim]",
                    classes="step-description",
                )
                yield Static("Skills (shared across agents via symlinks):", classes="section-heading")
                yield SelectionList[str](
                    *[(label, value, value in self.state.skills) for label, value in SKILL_OPTIONS],
                    id="skills-list",
                )
                yield Static("Hooks (agent lifecycle scripts):", classes="section-heading")
                yield SelectionList[str](
                    *[(label, value, value in self.state.hooks) for label, value in HOOK_OPTIONS],
                    id="hooks-list",
                )
            else:
                yield Static(
                    "The installer will set up the lab default skills and hooks:",
                    classes="step-description",
                )
                yield Static("[bold]Skills[/bold]", classes="section-heading")
                yield Static(render_list(SKILLS, self.state.skills), classes="section-body")
                yield Static("[bold]Hooks[/bold]", classes="section-heading")
                yield Static(render_list(HOOKS, self.state.hooks), classes="section-body")
                yield Static(
                    "[dim]To customize per-install, re-run with "
                    "[bold]coding-agents install --developer[/bold].[/dim]",
                    classes="muted",
                )

            with Horizontal(classes="nav"):
                yield Button("← Back", id="btn-back")
                yield Button("Next →", variant="primary", id="btn-next")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
        elif event.button.id == "btn-next":
            if self._is_developer():
                self.state.skills = list(self.query_one("#skills-list", SelectionList).selected)
                self.state.hooks = list(self.query_one("#hooks-list", SelectionList).selected)
            from coding_agents.installer.screens.review import ReviewScreen

            self.app.push_screen(ReviewScreen(self.state))
