"""Step 4: Tools & supporting software selection."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, SelectionList, Static

from coding_agents.installer.screens.install_dir import TOTAL_STEPS
from coding_agents.installer.state import InstallerState

TOOL_OPTIONS = [
    ("crawl4ai — web crawling & content extraction", "crawl4ai"),
    ("agent-browser — headless browser (bundles Chromium)", "agent-browser"),
    ("Linting tools (ruff, vulture, pyright, yamllint, biome, shellcheck)", "linters"),
    ("Entire CLI — session recording", "entire"),
]


class ToolsScreen(Screen):
    """Step 4 — Select tools and supporting software."""

    def __init__(self, state: InstallerState) -> None:
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        with Vertical(id="step-container"):
            yield Label(f"Step 4 of {TOTAL_STEPS} — Tools & Supporting Software", classes="step-title")
            yield Static(
                "Select supporting tools to install. All tools share a Python venv "
                "or live under tools/node_modules.",
                classes="step-description",
            )
            yield SelectionList[str](
                *[
                    (label, value, value in self.state.tools)
                    for label, value in TOOL_OPTIONS
                ],
                id="tools-list",
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
            tools_list = self.query_one("#tools-list", SelectionList)
            self.state.tools = list(tools_list.selected)
            from coding_agents.installer.screens.skills_hooks import SkillsHooksScreen

            self.app.push_screen(SkillsHooksScreen(self.state))
