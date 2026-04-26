"""Step 4: Tools & supporting software.

Two render modes:
  - default        info-only summary of what will be installed, with
                   clickable links to the upstream projects. No toggles.
  - --developer    full SelectionList picker so you can customize what
                   gets installed.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, SelectionList, Static

from coding_agents.installer.screens._links import TOOLS, render_list
from coding_agents.installer.screens.install_dir import TOTAL_STEPS
from coding_agents.installer.state import InstallerState

# Picker labels (developer mode) — keep in sync with the `key` column of
# screens._links.TOOLS.
TOOL_OPTIONS = [(label, key) for key, label, _url in TOOLS]


class ToolsScreen(Screen):
    """Step 4 — Tools and supporting software."""

    def __init__(self, state: InstallerState) -> None:
        super().__init__()
        self.state = state

    def _is_developer(self) -> bool:
        return bool(getattr(self.app, "developer", False))

    def compose(self) -> ComposeResult:
        with Vertical(id="step-container"):
            yield Label(
                f"Step 4 of {TOTAL_STEPS} — Tools & Supporting Software",
                classes="step-title",
            )

            if self._is_developer():
                yield Static(
                    "[dim]--developer mode: full picker.[/dim] "
                    "Select supporting tools to install. All tools share a Python "
                    "venv or live under tools/node_modules.",
                    classes="step-description",
                )
                yield SelectionList[str](
                    *[(label, value, value in self.state.tools) for label, value in TOOL_OPTIONS],
                    id="tools-list",
                )
            else:
                yield Static(
                    "The installer will set up the lab default tool set:",
                    classes="step-description",
                )
                yield Static(render_list(TOOLS, self.state.tools), classes="section-body")
                yield Static(
                    "[dim]To customize this list per-install, re-run with "
                    "[bold]coding-agents install --developer[/bold].[/dim]",
                    classes="muted",
                )
                if "pi" in self.state.agents:
                    yield Static(
                        "Pi extensions (pi-ask-user, pi-subagents) will be auto-installed "
                        "after Pi setup.",
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
                tools_list = self.query_one("#tools-list", SelectionList)
                self.state.tools = list(tools_list.selected)
            # In default mode state.tools keeps whatever it was (the lab
            # default loaded from config.DEFAULT_CONFIG via state.from_config).
            from coding_agents.installer.screens.skills_hooks import SkillsHooksScreen

            self.app.push_screen(SkillsHooksScreen(self.state))
