"""Step 6: Review selections and execute installation."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, ProgressBar, RichLog, Static

from coding_agents.agents import AGENTS, agents_with_vscode_ext
from coding_agents.installer.observer import (
    InstallObserver,
    set_verbose_sink,
)
from coding_agents.installer.screens.install_dir import TOTAL_STEPS
from coding_agents.installer.state import InstallerState


class SelectableRichLog(RichLog):
    """RichLog with text selection enabled so the user can copy log lines."""

    ALLOW_SELECT = True


class ReviewScreen(Screen):
    """Step 6 — Review all selections and execute the install."""

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True, priority=True),
    ]

    def __init__(self, state: InstallerState) -> None:
        super().__init__()
        self.state = state
        self._install_done = False

    def compose(self) -> ComposeResult:
        s = self.state
        agents_str = ", ".join(AGENTS[a]["display_name"] for a in s.agents) or "[dim]none[/dim]"
        tools_str = ", ".join(s.tools) if s.tools else "[dim]none[/dim]"
        skills_str = ", ".join(s.skills) if s.skills else "[dim]none[/dim]"
        hooks_str = ", ".join(s.hooks) if s.hooks else "[dim]none[/dim]"
        exts = agents_with_vscode_ext(s.agents)
        if exts:
            ext_str = ", ".join(ext_id for _, ext_id in exts)
            ext_str += "  [dim](extensions.json will be written)[/dim]"
        else:
            ext_str = "[dim]none[/dim]"

        sandbox_str = (
            f"Apptainer (SIF: {s.sandbox_sif_path})"
            if s.mode != "local"
            else "[dim]none (local mode)[/dim]"
        )
        summary = (
            f"[bold]Installation Directory:[/bold] {s.install_dir}\n"
            f"[bold]Agents:[/bold] {agents_str}\n"
            f"[bold]VSCode Extensions:[/bold] {ext_str}\n"
            f"[bold]Tools:[/bold] {tools_str}\n"
            f"[bold]Sandbox:[/bold] {sandbox_str}\n"
            f"[bold]Skills:[/bold] {skills_str}\n"
            f"[bold]Hooks:[/bold] {hooks_str}"
        )

        with Vertical(id="step-container"):
            yield Label(f"Step 6 of {TOTAL_STEPS} — Review & Install", classes="step-title")
            yield Static(summary, classes="banner-info")
            yield ProgressBar(total=100, show_eta=False, id="install-progress")
            yield Static("[bold]Install log[/bold]", classes="section-heading")
            yield SelectableRichLog(id="install-log", wrap=True, markup=True)
            yield Static(
                "[bold]Verbose output[/bold] [dim](subprocess stdout/stderr)[/dim]",
                classes="section-heading",
            )
            yield SelectableRichLog(
                id="verbose-log", wrap=False, markup=False, max_lines=2000
            )
            yield Static(
                "[dim]To copy text: click-drag to select. If selection is "
                "fighting the TUI, hold [bold]Option[/bold] (Mac) / "
                "[bold]Shift[/bold] (Linux) and drag — that bypasses the "
                "TUI's mouse handler and uses your terminal's native "
                "selection.[/dim]",
                classes="muted",
            )

            with Horizontal(classes="nav"):
                yield Button("← Back", id="btn-back")
                yield Button("Install", variant="success", id="btn-install")
                yield Button("Done", variant="primary", id="btn-done", disabled=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            if self._install_done:
                self.notify("Install already completed — press Done to exit.", severity="information")
                return
            self.app.pop_screen()
        elif event.button.id == "btn-install":
            event.button.disabled = True
            self.query_one("#btn-back", Button).disabled = True
            self.run_worker(self._execute_install(), exclusive=True)
        elif event.button.id == "btn-done":
            self.app.exit()

    def action_quit(self) -> None:
        self.app.exit()

    async def _execute_install(self) -> None:
        """Run the full installation sequence."""
        log = self.query_one("#install-log", RichLog)
        verbose = self.query_one("#verbose-log", RichLog)
        progress = self.query_one("#install-progress", ProgressBar)

        observer = InstallObserver(log=log, verbose=verbose, progress=progress)

        # Route subprocess stdout/stderr from utils.run() into the verbose
        # pane via the module-level sink. Always cleared in `finally`.
        def _sink(text: str) -> None:
            self.app.call_from_thread(observer.verbose, text)

        set_verbose_sink(_sink)

        from coding_agents.installer.executor import execute_install

        try:
            await execute_install(self.state, observer)
        except Exception as exc:
            log.write(f"\n[red bold]Installation failed:[/red bold] {exc}")
            log.write("\n[dim]Press Done or 'q' to exit and inspect the log file.[/dim]")
            self._install_done = True
            done_btn = self.query_one("#btn-done", Button)
            done_btn.disabled = False
            done_btn.label = "Exit"
            done_btn.variant = "error"
            done_btn.focus()
            return
        finally:
            set_verbose_sink(None)

        log.write("\n[green bold]Installation complete![/green bold]")
        log.write("Run [bold]source ~/.bashrc[/bold] to update your PATH.")
        log.write("Then try: [bold]coding-agents doctor[/bold]")

        self._install_done = True
        done_btn = self.query_one("#btn-done", Button)
        done_btn.disabled = False
        done_btn.focus()
