"""Step 7 — Post-install "next steps" screen.

Minimal one-line-per-step bullet list. The detailed instructions
(commands + clickable VSCode marketplace links) are printed to the host
terminal on Exit, so the screen stays scannable.
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
                "[bold]Press Exit to print the full step-by-step instructions "
                "(with runnable commands and clickable VSCode marketplace + "
                "extension-install links) to your terminal.[/bold]",
                classes="banner-info",
            )
            with VerticalScroll(id="next-steps-scroll"):
                for i, step in enumerate(self.steps, start=1):
                    yield Static(f"  {i}.  {step.title}", classes="section-body")
            yield Static(
                "[dim]The terminal output uses OSC-8 hyperlinks (Cmd-click / "
                "Ctrl-click in modern terminals — iTerm2, kitty, gnome-terminal, "
                "Windows Terminal, wezterm).[/dim]",
                classes="muted",
            )
            with Center(classes="nav"):
                yield Button("Exit", variant="primary", id="btn-exit")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-exit":
            self.app.exit()

    def action_quit(self) -> None:
        self.app.exit()
