"""Interactive TUI for project-init when existing configs are detected.

Shows what already exists, what would be added, and lets the user
select which items to merge.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, SelectionList, Static

from coding_agents.detect_existing import scan_project_existing


class ProjectInitMergeItem:
    """Represents one config item that could be merged."""

    def __init__(
        self,
        key: str,
        label: str,
        description: str,
        existing_content: str | None,
        proposed_content: str,
        category: str,
    ):
        self.key = key
        self.label = label
        self.description = description
        self.existing_content = existing_content
        self.proposed_content = proposed_content
        self.category = category


class ProjectInitResult:
    """Result from the merge TUI."""

    def __init__(self):
        self.selected_keys: list[str] = []
        self.cancelled: bool = False


class ProjectInitMergeScreen(Screen):
    """Screen showing existing vs proposed configs, with selection."""

    def __init__(self, items: list[ProjectInitMergeItem], result: ProjectInitResult):
        super().__init__()
        self.items = items
        self.result = result

    def compose(self) -> ComposeResult:
        with Vertical(id="step-container"):
            yield Label("Project Init — Existing Configs Detected", classes="step-title")
            yield Static(
                "This directory already has agent configuration files.\n"
                "Select which items to add or merge. Existing files will be preserved.\n",
                classes="step-description",
            )

            # Show what exists
            existing = [i for i in self.items if i.existing_content is not None]
            if existing:
                yield Static("[yellow bold]Already exists:[/yellow bold]")
                for item in existing:
                    preview = item.existing_content[:200] if item.existing_content else ""
                    if len(item.existing_content or "") > 200:
                        preview += "..."
                    yield Static(
                        f"  [bold]{item.label}[/bold]: {item.description}\n"
                        f"  [dim]{preview}[/dim]"
                    )
                yield Static("")

            # Selection list for what to add/merge
            yield Static("[green bold]Available to add:[/green bold]")
            yield SelectionList[str](
                *[
                    (
                        f"{item.label} — {item.description}",
                        item.key,
                        item.existing_content is None,  # Pre-select items that don't exist yet
                    )
                    for item in self.items
                ],
                id="merge-list",
            )

            yield Static("")
            yield Button("Merge Selected", variant="success", id="btn-merge")
            yield Button("Merge Everything", variant="primary", id="btn-all")
            yield Button("Cancel", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-merge":
            merge_list = self.query_one("#merge-list", SelectionList)
            self.result.selected_keys = list(merge_list.selected)
            self.app.exit()
        elif event.button.id == "btn-all":
            self.result.selected_keys = [item.key for item in self.items]
            self.app.exit()
        elif event.button.id == "btn-cancel":
            self.result.cancelled = True
            self.app.exit()


class ProjectInitMergeApp(App):
    """Minimal TUI app for project-init merge decisions."""

    TITLE = "coding-agents project-init"
    CSS = """
    Screen {
        align: center middle;
    }
    #step-container {
        width: 90;
        max-height: 90%;
        border: round $primary;
        padding: 1 2;
    }
    .step-title {
        text-style: bold;
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

    def __init__(self, items: list[ProjectInitMergeItem]):
        super().__init__()
        self.items = items
        self.result = ProjectInitResult()

    def on_mount(self) -> None:
        self.push_screen(ProjectInitMergeScreen(self.items, self.result))

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()


def build_merge_items(
    project_path: Path,
    install_dir: Path,
    agents: list[str],
    hooks: list[str],
) -> list[ProjectInitMergeItem]:
    """Build the list of merge items for a project directory."""
    from coding_agents.agents import AGENTS
    from coding_agents.config import HOOK_SCRIPTS

    items: list[ProjectInitMergeItem] = []

    # AGENTS.md
    agents_md = project_path / "AGENTS.md"
    existing = agents_md.read_text() if agents_md.exists() else None
    items.append(ProjectInitMergeItem(
        key="agents_md",
        label="AGENTS.md",
        description="Project-level agent instructions from template",
        existing_content=existing,
        proposed_content="(generated from PROJECT_LOCAL_AGENTS_TEMPLATE.md)",
        category="instruction_files",
    ))

    # CLAUDE.md symlink
    claude_md = project_path / "CLAUDE.md"
    existing = "symlink → AGENTS.md" if claude_md.is_symlink() else (claude_md.read_text() if claude_md.exists() else None)
    items.append(ProjectInitMergeItem(
        key="claude_md_symlink",
        label="CLAUDE.md → AGENTS.md",
        description="Claude Code compatibility symlink",
        existing_content=existing,
        proposed_content="symlink → AGENTS.md",
        category="instruction_files",
    ))

    # GEMINI.md symlink
    gemini_md = project_path / "GEMINI.md"
    existing = "symlink → AGENTS.md" if gemini_md.is_symlink() else (gemini_md.read_text() if gemini_md.exists() else None)
    items.append(ProjectInitMergeItem(
        key="gemini_md_symlink",
        label="GEMINI.md → AGENTS.md",
        description="Gemini CLI compatibility symlink",
        existing_content=existing,
        proposed_content="symlink → AGENTS.md",
        category="instruction_files",
    ))

    # Claude project config with hooks
    if "claude" in agents:
        claude_settings = project_path / ".claude" / "settings.json"
        existing = claude_settings.read_text() if claude_settings.exists() else None
        hook_cmds = []
        for h in hooks:
            script = HOOK_SCRIPTS.get(h)
            if script:
                hook_cmds.append(f"python3 {install_dir}/hooks/{script}")
        proposed = f"Hooks: {', '.join(hook_cmds[:3])}" if hook_cmds else "Empty config"
        items.append(ProjectInitMergeItem(
            key="claude_settings",
            label=".claude/settings.json",
            description=f"Claude project config with {len(hook_cmds)} hooks",
            existing_content=existing,
            proposed_content=proposed,
            category="agent_configs",
        ))

    # Codex project config
    if "codex" in agents:
        codex_config = project_path / ".codex" / "config.toml"
        existing = codex_config.read_text() if codex_config.exists() else None
        items.append(ProjectInitMergeItem(
            key="codex_config",
            label=".codex/config.toml",
            description="Codex CLI project config stub",
            existing_content=existing,
            proposed_content="# Codex CLI project config",
            category="agent_configs",
        ))

    # Pi project config
    if "pi" in agents:
        pi_settings = project_path / ".pi" / "settings.json"
        existing = pi_settings.read_text() if pi_settings.exists() else None
        items.append(ProjectInitMergeItem(
            key="pi_settings",
            label=".pi/settings.json",
            description="Pi project config",
            existing_content=existing,
            proposed_content=json.dumps({"project": project_path.name}, indent=2),
            category="agent_configs",
        ))

    # OpenCode project config
    if "opencode" in agents:
        opencode_json = project_path / "opencode.json"
        existing = opencode_json.read_text() if opencode_json.exists() else None
        items.append(ProjectInitMergeItem(
            key="opencode_json",
            label="opencode.json",
            description="OpenCode project config",
            existing_content=existing,
            proposed_content=json.dumps({"project": project_path.name}, indent=2),
            category="agent_configs",
        ))

    # .gitignore entries
    gitignore = project_path / ".gitignore"
    existing = gitignore.read_text() if gitignore.exists() else None
    items.append(ProjectInitMergeItem(
        key="gitignore",
        label=".gitignore",
        description="Agent directory exclusions (.claude/, .codex/, etc.)",
        existing_content=existing,
        proposed_content=".claude/\n.codex/\n.pi/\n.opencode/\n.gemini/\n.entire/",
        category="other",
    ))

    # VSCode extensions.json
    ext_json = project_path / ".vscode" / "extensions.json"
    existing = ext_json.read_text() if ext_json.exists() else None
    items.append(ProjectInitMergeItem(
        key="vscode_extensions",
        label=".vscode/extensions.json",
        description="Recommended VSCode extensions for installed agents",
        existing_content=existing,
        proposed_content="(agent extension recommendations)",
        category="other",
    ))

    return items
