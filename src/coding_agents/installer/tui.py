"""Textual TUI application for the coding-agents installer."""
from __future__ import annotations

import os
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header

from coding_agents.config import HPC_ONLY_HOOKS, HPC_ONLY_SKILLS, load_config
from coding_agents.installer.state import InstallerState

# nord = calm blue/gray palette; less visually noisy than the default
# "textual-dark" theme. Override with the env var if you prefer another
# built-in theme (catppuccin-mocha, gruvbox, tokyo-night, dracula, ...).
DEFAULT_THEME = os.environ.get("CODING_AGENTS_THEME", "nord")


class CodingAgentsInstaller(App):
    """Multi-step installer TUI using Textual's screen stack."""

    TITLE = "coding-agents installer"
    SUB_TITLE = "de Ridder lab — sandboxed Claude Code / Codex / OpenCode / Pi"
    CSS_PATH = str(Path(__file__).parent / "installer.tcss")

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True, priority=True),
        Binding("ctrl+c", "quit", "Quit", show=False, priority=True),
    ]

    def __init__(self, mode: str = "hpc", excluded_agents: set[str] | None = None) -> None:
        super().__init__()
        existing = load_config()
        if existing.get("install_dir"):
            self.state = InstallerState.from_config(existing)
        else:
            self.state = InstallerState()

        self.state.mode = mode
        if mode == "local":
            self.state.skills = [s for s in self.state.skills if s not in HPC_ONLY_SKILLS]
            self.state.hooks = [h for h in self.state.hooks if h not in HPC_ONLY_HOOKS]

        self.excluded_agents: set[str] = set(excluded_agents or set())
        if self.excluded_agents:
            self.state.agents = [a for a in self.state.agents if a not in self.excluded_agents]

        from coding_agents.detect_existing import scan_existing

        self.existing_inventory = scan_existing()

    def on_mount(self) -> None:
        # Apply the theme on mount; older Textual versions silently ignore it.
        try:
            self.theme = DEFAULT_THEME
        except Exception:
            pass

        from coding_agents.installer.screens.install_dir import InstallDirScreen

        self.push_screen(InstallDirScreen(self.state, self.existing_inventory))

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Footer()

    def action_quit(self) -> None:
        self.exit()
