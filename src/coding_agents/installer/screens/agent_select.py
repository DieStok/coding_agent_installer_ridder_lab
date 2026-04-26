"""Step 2: Agent selection (presets + custom)."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, RadioButton, RadioSet, SelectionList, Static

from coding_agents.agents import AGENTS, PRESETS
from coding_agents.installer.state import InstallerState


class AgentSelectScreen(Screen):
    """Step 2 — Select which agents to install."""

    def __init__(self, state: InstallerState) -> None:
        super().__init__()
        self.state = state

    def _excluded(self) -> set[str]:
        """Set of agents the user passed via --exclude (or empty)."""
        return getattr(self.app, "excluded_agents", set()) or set()

    def compose(self) -> ComposeResult:
        excluded = self._excluded()
        excluded_note = (
            f"\n[yellow]--exclude active:[/yellow] skipping {sorted(excluded)}"
            if excluded
            else ""
        )
        with Vertical(id="step-container"):
            yield Label("Step 2 of 7 — Agent Selection", classes="step-title")
            yield Static(
                "Choose a preset or customize your agent selection." + excluded_note,
                classes="step-description",
            )
            yield RadioSet(
                RadioButton("Core (Claude, Codex, OpenCode, Pi)", value=self.state.preset == "core", id="preset-core"),
                RadioButton("All (6 agents)", id="preset-all"),
                RadioButton("Custom", id="preset-custom"),
                id="preset-radio",
            )
            yield SelectionList[str](
                *[
                    (f"{info['display_name']} ({key})", key, key in self.state.agents)
                    for key, info in AGENTS.items()
                    if key not in excluded
                ],
                id="agent-list",
            )
            yield Button("← Back", id="btn-back")
            yield Button("Next →", variant="primary", id="btn-next")

    def on_mount(self) -> None:
        agent_list = self.query_one("#agent-list", SelectionList)
        agent_list.display = self.state.preset == "custom"

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        agent_list = self.query_one("#agent-list", SelectionList)
        excluded = self._excluded()
        idx = event.radio_set.pressed_index
        if idx == 0:
            self.state.preset = "core"
            self.state.agents = [a for a in PRESETS["core"] if a not in excluded]
            agent_list.display = False
        elif idx == 1:
            self.state.preset = "all"
            self.state.agents = [a for a in PRESETS["all"] if a not in excluded]
            agent_list.display = False
        else:
            self.state.preset = "custom"
            agent_list.display = True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
        elif event.button.id == "btn-next":
            if self.state.preset == "custom":
                agent_list = self.query_one("#agent-list", SelectionList)
                self.state.agents = list(agent_list.selected)
            if not self.state.agents:
                return  # Must select at least one
            from coding_agents.installer.screens.vscode_ext import VSCodeExtScreen

            self.app.push_screen(VSCodeExtScreen(self.state))
