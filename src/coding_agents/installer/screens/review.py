"""Step 7: Review selections and execute installation."""
from __future__ import annotations

import shutil
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, RichLog, Static

from coding_agents.agents import AGENTS, agents_with_vscode_ext
from coding_agents.installer.state import InstallerState


class ReviewScreen(Screen):
    """Step 7 — Review all selections and execute the install."""

    def __init__(self, state: InstallerState) -> None:
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        s = self.state
        agents_str = ", ".join(AGENTS[a]["display_name"] for a in s.agents)
        tools_str = ", ".join(s.tools) if s.tools else "none"
        skills_str = ", ".join(s.skills) if s.skills else "none"
        hooks_str = ", ".join(s.hooks) if s.hooks else "none"
        exts = agents_with_vscode_ext(s.agents)
        ext_str = ", ".join(ext_id for _, ext_id in exts) if exts and s.vscode_extensions else "none"

        summary = (
            f"[bold]Installation Directory:[/bold] {s.install_dir}\n"
            f"[bold]Agents:[/bold] {agents_str}\n"
            f"[bold]VSCode Extensions:[/bold] {ext_str}\n"
            f"[bold]Tools:[/bold] {tools_str}\n"
            f"[bold]jai Sandbox:[/bold] {'yes' if s.jai_enabled else 'no'}\n"
            f"[bold]Skills:[/bold] {skills_str}\n"
            f"[bold]Hooks:[/bold] {hooks_str}\n"
        )

        with Vertical(id="step-container"):
            yield Label("Step 7 of 7 — Review & Install", classes="step-title")
            yield Static(summary, classes="step-description")
            yield Button("← Back", id="btn-back")
            yield Button("Install", variant="success", id="btn-install")
            yield RichLog(id="install-log", wrap=True, markup=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
        elif event.button.id == "btn-install":
            event.button.disabled = True
            self.run_worker(self._execute_install())

    async def _execute_install(self) -> None:
        """Run the full installation sequence."""
        log = self.query_one("#install-log", RichLog)
        state = self.state
        install_dir = Path(state.install_dir).expanduser()

        from coding_agents.installer.executor import execute_install

        try:
            await execute_install(state, log)
        except Exception as exc:
            log.write(f"\n[red]Installation failed: {exc}[/red]")
            return

        log.write("\n[green bold]Installation complete![/green bold]")
        log.write(f"Run [bold]source ~/.bashrc[/bold] to update your PATH.")
        log.write(f"Then try: [bold]coding-agents doctor[/bold]")
