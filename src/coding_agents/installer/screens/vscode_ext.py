"""Step 3: VSCode extension recommendations.

On HPC mode the user runs the installer over SSH on the cluster. The `code`
CLI is never on the HPC's PATH (and shouldn't be — VSCode itself runs on the
user's laptop and connects via Remote-SSH). So instead of asking "install
extensions yes/no" we present the list as clickable links the user can open
on their laptop and we always write a `vscode-extensions.json` recommendation
file into the install dir for manual import.
"""
from __future__ import annotations

import shutil

from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, Static, Switch

from coding_agents.agents import agents_with_vscode_ext
from coding_agents.installer.screens.install_dir import TOTAL_STEPS
from coding_agents.installer.state import InstallerState


def _ext_links_text(extensions: list[tuple[str, str]]) -> Text:
    """Build a Rich Text object listing extensions with two clickable URLs each.

    Built via the Style(link=…) API — NOT via markup — so the URL never goes
    through Textual's markup parser. (Earlier versions used `[link="…"]`
    markup, but the quotes leaked into the OSC-8 escape and broke link
    detection in modern terminals. Programmatic Style construction emits a
    clean OSC-8 sequence: `\\x1b]8;;<URL>\\x1b\\<text>\\x1b]8;;\\x1b\\`.)

    Two URLs per extension:
      - vscode:extension/<id>           opens the extension page directly in
                                        the user's local VSCode (terminal
                                        must register the vscode: handler;
                                        iTerm2, kitty, modern gnome-terminal
                                        do this when VSCode is installed
                                        locally).
      - https://marketplace.visualstudio.com/items?itemName=<id>
                                        universal fallback that opens the
                                        marketplace web page; that page has
                                        an "Install" button that launches
                                        VSCode locally.

    To activate the link inside a Textual TUI, terminal emulators usually
    require a modifier key (Cmd-click on Mac, Ctrl-click on Linux) so the
    click event reaches the terminal instead of being consumed by Textual.
    """
    text = Text()
    if not extensions:
        text.append("No selected agents publish a VSCode extension.", style="dim italic")
        return text

    for i, (agent_key, ext_id) in enumerate(extensions):
        if i > 0:
            text.append("\n")
        marketplace = f"https://marketplace.visualstudio.com/items?itemName={ext_id}"
        vscode_uri = f"vscode:extension/{ext_id}"

        text.append("  • ")
        text.append(ext_id, style="bold")
        text.append(f"  ({agent_key})\n", style="dim")
        text.append("      ")
        text.append("Open in VSCode", style=Style(link=vscode_uri, underline=True, bold=True))
        text.append("   ·   ", style="dim")
        text.append("Marketplace page", style=Style(link=marketplace, underline=True, bold=True))
    return text


class VSCodeExtScreen(Screen):
    """Step 3 — VSCode extension recommendations."""

    def __init__(self, state: InstallerState) -> None:
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        exts = agents_with_vscode_ext(self.state.agents)
        is_hpc = self.state.mode != "local"
        code_available = shutil.which("code") is not None

        with Vertical(id="step-container"):
            yield Label(f"Step 3 of {TOTAL_STEPS} — VSCode Extensions", classes="step-title")

            if is_hpc:
                yield Static(
                    "[bold]Want to use these agents from a sidebar (like GitHub Copilot Chat)?[/bold]\n"
                    "Install the extensions below in your [italic]local[/italic] VSCode. "
                    "When you connect to this HPC over Remote-SSH, the extensions automatically "
                    "ride along — VSCode mirrors them into [dim]~/.vscode-server/extensions/[/dim] "
                    "on the cluster for you.",
                    classes="banner-info",
                )
            else:
                yield Static(
                    "Install the extensions below in VSCode for sidebar / inline-chat integration.",
                    classes="step-description",
                )

            yield Static("[bold]Recommended extensions:[/bold]", classes="section-heading")
            yield Static(_ext_links_text(exts), classes="section-body")

            if exts:
                yield Static(
                    "[dim]Tip: links above are real OSC-8 hyperlinks. To activate "
                    "them inside this TUI, hold [bold]Cmd[/bold] (Mac) or "
                    "[bold]Ctrl[/bold] (Linux) and click — that lets the click "
                    "reach your terminal instead of being captured by the TUI.[/dim]",
                    classes="muted",
                )
                yield Static(
                    "A copy of this list is also written to "
                    "[bold]<install_dir>/vscode-extensions.json[/bold] for manual "
                    "import via VSCode's command palette → "
                    "[italic]Extensions: Install from VSIX/JSON[/italic].",
                    classes="muted",
                )

            if not is_hpc:
                yield Static(
                    "Auto-install on this machine (only works when [bold]code[/bold] is on PATH):"
                    + ("" if code_available else "  [yellow](not detected)[/yellow]"),
                    classes="section-heading",
                )
                yield Switch(
                    value=self.state.vscode_extensions and code_available,
                    id="vscode-switch",
                    disabled=not code_available,
                )

            with Horizontal(classes="nav"):
                yield Button("← Back", id="btn-back")
                yield Button("Continue →", variant="primary", id="btn-next")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
        elif event.button.id == "btn-next":
            # On HPC the switch isn't even shown — the user manages extensions
            # locally; we always write the recommendation JSON regardless.
            if self.state.mode == "local":
                try:
                    self.state.vscode_extensions = self.query_one("#vscode-switch", Switch).value
                except Exception:
                    self.state.vscode_extensions = False
            else:
                self.state.vscode_extensions = False  # never run `code --install` on HPC

            from coding_agents.installer.screens.tools import ToolsScreen

            self.app.push_screen(ToolsScreen(self.state))
