"""Step 1: Installation directory selection."""
from __future__ import annotations

import os
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Static

from coding_agents.detect_existing import GlobalInventory
from coding_agents.installer.state import InstallerState


def _default_dir(mode: str = "hpc") -> str:
    if mode == "local":
        return str(Path.home() / "coding_agents")
    user = os.environ.get("USER", "user")
    hpc_path = f"/hpc/compgen/users/{user}/coding_agents"
    if Path("/hpc/compgen/users").exists():
        return hpc_path
    return str(Path.home() / "coding_agents")


class InstallDirScreen(Screen):
    """Step 1 — Choose installation directory."""

    def __init__(self, state: InstallerState, inventory: GlobalInventory | None = None) -> None:
        super().__init__()
        self.state = state
        self.inventory = inventory

    def compose(self) -> ComposeResult:
        default = self.state.install_dir or _default_dir(self.state.mode)
        with Vertical(id="step-container"):
            yield Label("Step 1 of 7 — Installation Directory", classes="step-title")

            # Info banner if existing installations detected
            if self.inventory and self.inventory.has_existing:
                existing = self.inventory.existing_agents
                names = ", ".join(a.display_name for a in existing)
                details = []
                for a in existing:
                    details.append(f"  {a.display_name}: {a.file_count} files ({a.human_size()}) in {a.config_dir}")
                detail_text = "\n".join(details)
                yield Static(
                    f"[yellow bold]Existing installations detected:[/yellow bold]\n"
                    f"{detail_text}\n\n"
                    f"[dim]These will be backed up to .tar.gz before any changes are made.\n"
                    f"Your existing settings (hooks, MCP, deny rules) will be preserved and merged.[/dim]",
                    id="existing-banner",
                )

            yield Static(
                "Where should coding-agents install agents, tools, and skills?\n"
                "This directory will contain all binaries, node_modules, and configs.",
                classes="step-description",
            )
            yield Input(value=default, placeholder="/path/to/coding_agents", id="dir-input")
            yield Label("", id="dir-error")
            yield Button("Next →", variant="primary", id="btn-next")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-next":
            self._validate_and_proceed()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._validate_and_proceed()

    def _validate_and_proceed(self) -> None:
        dir_input = self.query_one("#dir-input", Input)
        error_label = self.query_one("#dir-error", Label)
        path = Path(dir_input.value).expanduser()

        # Validate path length (shebang limit — HPC only)
        if self.state.mode == "hpc" and len(str(path)) > 100:
            error_label.update("[red]Path too long (>100 chars). Shebang limit on HPC.[/red]")
            return

        # Check parent is writable
        parent = path.parent
        if parent.exists() and not os.access(str(parent), os.W_OK):
            error_label.update(f"[red]Parent directory not writable: {parent}[/red]")
            return

        self.state.install_dir = str(path)
        from coding_agents.installer.screens.agent_select import AgentSelectScreen

        self.app.push_screen(AgentSelectScreen(self.state))
