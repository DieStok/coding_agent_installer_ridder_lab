"""Textual TUI application for the coding-agents installer."""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header

from coding_agents.config import HPC_ONLY_HOOKS, HPC_ONLY_SKILLS, load_config
from coding_agents.installer.state import InstallerState


class CodingAgentsInstaller(App):
    """Multi-step installer TUI using Textual's screen stack."""

    TITLE = "coding-agents installer"
    CSS = """
    Screen {
        align: center middle;
    }
    #step-container {
        width: 80;
        max-height: 90%;
        border: round $primary;
        padding: 1 2;
    }
    .step-title {
        text-style: bold;
        color: $text;
        margin-bottom: 1;
    }
    .step-description {
        color: $text-muted;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(self, mode: str = "hpc") -> None:
        super().__init__()
        # Pre-populate from existing config if available
        existing = load_config()
        if existing.get("install_dir"):
            self.state = InstallerState.from_config(existing)
        else:
            self.state = InstallerState()

        # Apply mode
        self.state.mode = mode
        if mode == "local":
            # MVP: --local mode is deferred to v2 (bubblewrap fallback). The
            # TUI still loads but the executor's wrapper-creation step is
            # skipped (mode != "local" guard in execute_install).
            self.state.skills = [s for s in self.state.skills if s not in HPC_ONLY_SKILLS]
            self.state.hooks = [h for h in self.state.hooks if h not in HPC_ONLY_HOOKS]

        # Pre-flight scan for existing agent installations
        from coding_agents.detect_existing import scan_existing

        self.existing_inventory = scan_existing()

    def on_mount(self) -> None:
        from coding_agents.installer.screens.install_dir import InstallDirScreen

        self.push_screen(InstallDirScreen(self.state, self.existing_inventory))

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
