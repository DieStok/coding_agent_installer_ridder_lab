"""Step 5: jai sandbox configuration."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, Static, Switch

from coding_agents.agents import AGENTS
from coding_agents.installer.state import InstallerState


class JaiConfigScreen(Screen):
    """Step 5 — Enable/disable jai sandbox configs."""

    def __init__(self, state: InstallerState) -> None:
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        agent_confs = [
            f"  • {AGENTS[a]['display_name']} → {AGENTS[a]['jai_conf']}"
            for a in self.state.agents
        ]
        with Vertical(id="step-container"):
            yield Label("Step 5 of 7 — jai Sandbox", classes="step-title")
            yield Static(
                "jai provides lightweight sandboxing for coding agents.\n"
                "It must be installed system-wide by an admin.\n"
                "Configs will be prepared but inactive until jai is available.\n\n"
                "Sandbox configs for selected agents:\n" + "\n".join(agent_confs),
                classes="step-description",
            )
            yield Label("Prepare jai sandbox configs?")
            yield Switch(value=self.state.jai_enabled, id="jai-switch")
            yield Button("← Back", id="btn-back")
            yield Button("Next →", variant="primary", id="btn-next")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
        elif event.button.id == "btn-next":
            self.state.jai_enabled = self.query_one("#jai-switch", Switch).value
            from coding_agents.installer.screens.skills_hooks import SkillsHooksScreen

            self.app.push_screen(SkillsHooksScreen(self.state))
