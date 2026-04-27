"""Step 1: Installation directory selection."""
from __future__ import annotations

import os
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Static

from coding_agents.agents import AGENTS
from coding_agents.detect_existing import GlobalInventory
from coding_agents.installer.state import InstallerState

TOTAL_STEPS = 6


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

    BINDINGS = [
        Binding("enter", "next", "Next", show=False),
    ]

    def __init__(self, state: InstallerState, inventory: GlobalInventory | None = None) -> None:
        super().__init__()
        self.state = state
        self.inventory = inventory

    def compose(self) -> ComposeResult:
        default = self.state.install_dir or _default_dir(self.state.mode)
        with Vertical(id="step-container"):
            yield Label(f"Step 1 of {TOTAL_STEPS} — Installation Directory", classes="step-title")

            # --exclude awareness: show what was excluded via the CLI flag so
            # the user notices on the very first screen if it's wrong (and
            # tell them how to fix it without diving into help text).
            excluded = getattr(self.app, "excluded_agents", set()) or set()
            if excluded:
                ex_list = ", ".join(
                    f"{AGENTS[k]['display_name']} ({k})" if k in AGENTS else k
                    for k in sorted(excluded)
                )
                yield Static(
                    f"[bold]Excluded by --exclude flag:[/bold] {ex_list}\n"
                    f"These agents will [bold]not[/bold] be installed, configured, or "
                    f"wrapped — your existing install (if any) is left untouched.\n"
                    f"\n"
                    f"[dim]Wrong? Press [bold]q[/bold] to quit, then re-run with the "
                    f"correct flag, e.g.:\n"
                    f"    coding-agents install                        # install everything\n"
                    f"    coding-agents install --exclude claude       # exclude one agent\n"
                    f"    coding-agents install --exclude claude,codex # exclude several[/dim]",
                    classes="banner-warn",
                    id="exclude-banner",
                )

            if self.inventory and self.inventory.has_existing:
                existing = self.inventory.existing_agents
                details = "\n".join(
                    f"  • {a.display_name}: {a.file_count} files ({a.human_size()}) in {a.config_dir}"
                    for a in existing
                )
                yield Static(
                    f"[bold]Existing installations detected:[/bold]\n{details}\n\n"
                    f"[dim]These will be backed up to .tar.gz before any changes are made. "
                    f"Existing settings (hooks, MCP, deny rules) will be preserved and merged.[/dim]",
                    classes="banner-warn",
                    id="existing-banner",
                )

            yield Static(
                "Where should coding-agents install wrappers, tools, and skills?\n"
                "This directory holds the per-agent wrapper scripts in [bold]bin/[/bold], "
                "the linter/biome workspace in [bold]tools/[/bold], skills, hooks, and "
                "merged agent configs. Agents themselves run from the SIF — no host "
                "node_modules for codex/opencode/pi.",
                classes="step-description",
            )
            yield Input(value=default, placeholder="/path/to/coding_agents", id="dir-input")
            yield Label("", id="dir-error")

            with Horizontal(classes="nav"):
                yield Button("Next →", variant="primary", id="btn-next")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-next":
            self._validate_and_proceed()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._validate_and_proceed()

    def action_next(self) -> None:
        self._validate_and_proceed()

    def _validate_and_proceed(self) -> None:
        dir_input = self.query_one("#dir-input", Input)
        error_label = self.query_one("#dir-error", Label)
        path = Path(dir_input.value).expanduser()

        if self.state.mode == "hpc" and len(str(path)) > 100:
            error_label.update("[red]Path too long (>100 chars). Shebang limit on HPC.[/red]")
            return

        parent = path.parent
        if parent.exists() and not os.access(str(parent), os.W_OK):
            error_label.update(f"[red]Parent directory not writable: {parent}[/red]")
            return

        self.state.install_dir = str(path)
        from coding_agents.installer.screens.agent_select import AgentSelectScreen

        self.app.push_screen(AgentSelectScreen(self.state))
