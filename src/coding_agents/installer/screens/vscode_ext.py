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

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, Static, Switch

from coding_agents.agents import agents_with_vscode_ext
from coding_agents.installer.screens.install_dir import TOTAL_STEPS
from coding_agents.installer.state import InstallerState


def _ext_links_markup(extensions: list[tuple[str, str]]) -> str:
    """Render extensions as Rich-markup with clickable links.

    Two URLs per extension, both wrapped in OSC-8 hyperlinks via Rich's
    [link=...] markup:
      - vscode:extension/<id>           — opens the extension page directly
                                          in the user's local VSCode (works
                                          when the terminal honours custom
                                          URL schemes; iTerm2, kitty, modern
                                          gnome-terminal all do).
      - https://marketplace.visualstudio.com/items?itemName=<id>
                                        — universal fallback that opens the
                                          marketplace web page; the page has
                                          a big green "Install" button that
                                          launches VSCode locally.
    """
    if not extensions:
        return "[dim]No selected agents publish a VSCode extension.[/dim]"

    lines: list[str] = []
    for agent_key, ext_id in extensions:
        marketplace = f"https://marketplace.visualstudio.com/items?itemName={ext_id}"
        vscode_uri = f"vscode:extension/{ext_id}"
        # URLs are quoted so Textual's markup parser doesn't choke on the
        # 'vscode:' colon (which it would otherwise read as a markup separator).
        lines.append(
            f"  • [bold]{ext_id}[/bold]  ([italic]{agent_key}[/italic])\n"
            f'      [link="{vscode_uri}"]Open in VSCode[/link]'
            f'   ·   [link="{marketplace}"]Marketplace page[/link]'
        )
    return "\n".join(lines)


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
            yield Static(_ext_links_markup(exts), classes="section-body")

            if exts:
                yield Static(
                    "A copy of this list will be written to [bold]<install_dir>/vscode-extensions.json[/bold] "
                    "so you can import it later via VSCode's command palette → "
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
