"""Step 7 — Post-install "next steps" screen.

Shown after a successful install. Lists what the user needs to do next,
with copy-friendly commands and clickable doc links. The same step list
is printed to the host terminal on TUI exit so users can act on it
without having to scroll back through the install log.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Label, Static

from coding_agents.installer.next_steps import Step, build_next_steps
from coding_agents.installer.state import InstallerState


class NextStepsScreen(Screen):
    """Shown after the install runs cleanly. One Exit button, centered."""

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True, priority=True),
    ]

    def __init__(self, state: InstallerState) -> None:
        super().__init__()
        self.state = state
        self.steps: list[Step] = build_next_steps(state)

    def compose(self) -> ComposeResult:
        with Vertical(id="step-container"):
            yield Label("✓ Installation complete — Next steps", classes="step-title")
            yield Static(
                "Each step below has a runnable command or doc link. The "
                "full list will also be printed to your terminal when you "
                "press Exit, so you can copy-paste from there.",
                classes="step-description",
            )
            with VerticalScroll(id="next-steps-scroll"):
                for i, step in enumerate(self.steps, start=1):
                    yield Static(f"[bold]{i}. {step.title}[/bold]",
                                 classes="section-heading")
                    yield Static(step.body, classes="section-body")
                    if step.action is not None:
                        kind, payload = step.action
                        if kind == "cmd":
                            yield Static(
                                f"    [cyan]$ {payload}[/cyan]",
                                classes="section-body",
                            )
                        elif kind == "url":
                            yield Static(
                                f"    [dim]→ {payload}[/dim]",
                                classes="section-body",
                            )
            with Center(classes="nav"):
                yield Button("Exit", variant="primary", id="btn-exit")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-exit":
            self.app.exit()

    def action_quit(self) -> None:
        self.app.exit()
