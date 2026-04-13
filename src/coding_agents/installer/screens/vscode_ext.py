"""Step 3: VSCode extensions toggle."""
from __future__ import annotations

import shutil

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, Static, Switch

from coding_agents.agents import agents_with_vscode_ext
from coding_agents.installer.state import InstallerState


class VSCodeExtScreen(Screen):
    """Step 3 — VSCode extension installation."""

    def __init__(self, state: InstallerState) -> None:
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        exts = agents_with_vscode_ext(self.state.agents)
        code_available = shutil.which("code") is not None

        with Vertical(id="step-container"):
            yield Label("Step 3 of 7 — VSCode Extensions", classes="step-title")
            if exts:
                ext_list = "\n".join(f"  • {ext_id} ({agent})" for agent, ext_id in exts)
                yield Static(
                    f"Extensions to install:\n{ext_list}",
                    classes="step-description",
                )
            else:
                yield Static(
                    "No selected agents have VSCode extensions.",
                    classes="step-description",
                )

            if not code_available:
                yield Static(
                    "[yellow]`code` not found on PATH. Extensions will be written to "
                    "extensions.json for manual install via Remote-SSH.[/yellow]"
                )

            yield Label("Install VSCode extensions?")
            yield Switch(value=self.state.vscode_extensions, id="vscode-switch")
            yield Button("← Back", id="btn-back")
            yield Button("Next →", variant="primary", id="btn-next")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
        elif event.button.id == "btn-next":
            self.state.vscode_extensions = self.query_one("#vscode-switch", Switch).value
            from coding_agents.installer.screens.tools import ToolsScreen

            self.app.push_screen(ToolsScreen(self.state))
