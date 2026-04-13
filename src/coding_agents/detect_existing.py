"""Pre-flight scanner for existing agent installations.

Scans all 6 agent config directories for existing files, creates an inventory,
and provides backup functionality (.tar.gz archives next to source).
"""
from __future__ import annotations

import logging
import os
import tarfile
from dataclasses import dataclass, field

_log = logging.getLogger("coding-agents")
from datetime import date
from pathlib import Path

from coding_agents.agents import AGENTS


@dataclass
class AgentInventory:
    """What we found for a single agent's existing installation."""

    agent_key: str
    display_name: str
    config_dir: Path
    exists: bool = False
    files: list[str] = field(default_factory=list)
    total_size: int = 0
    backup_path: Path | None = None

    @property
    def file_count(self) -> int:
        return len(self.files)

    def human_size(self) -> str:
        """Format total_size as human-readable."""
        if self.total_size < 1024:
            return f"{self.total_size} B"
        elif self.total_size < 1024 * 1024:
            return f"{self.total_size / 1024:.1f} KB"
        else:
            return f"{self.total_size / (1024 * 1024):.1f} MB"

    def tree_display(self, max_files: int = 20) -> str:
        """Human-readable file tree."""
        if not self.files:
            return f"  (empty)"
        lines = []
        for i, f in enumerate(sorted(self.files)):
            if i >= max_files:
                remaining = len(self.files) - max_files
                lines.append(f"  ... and {remaining} more files")
                break
            lines.append(f"  {f}")
        return "\n".join(lines)


@dataclass
class GlobalInventory:
    """What we found across all agents + global config files."""

    agents: list[AgentInventory] = field(default_factory=list)
    global_files: dict[str, bool] = field(default_factory=dict)  # path -> exists

    @property
    def has_existing(self) -> bool:
        return any(a.exists for a in self.agents) or any(self.global_files.values())

    @property
    def existing_agents(self) -> list[AgentInventory]:
        return [a for a in self.agents if a.exists]


def scan_existing() -> GlobalInventory:
    """Scan for all existing agent installations and global configs.

    Checks all 6 agent config directories regardless of which agents
    the user plans to install. Also checks global config files.
    """
    _log.debug("scan_existing: scanning all 6 agent config directories")
    inventory = GlobalInventory()

    # Scan each agent's config directory
    for key, agent in AGENTS.items():
        config_dir = Path(agent["config_dir"]).expanduser()
        inv = AgentInventory(
            agent_key=key,
            display_name=agent["display_name"],
            config_dir=config_dir,
        )

        if config_dir.exists() and any(config_dir.iterdir()):
            inv.exists = True
            # Walk the directory, collecting relative file paths
            for root, dirs, files in os.walk(config_dir):
                # Skip very large dirs (node_modules, .git)
                dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "__pycache__")]
                for f in files:
                    full = Path(root) / f
                    rel = full.relative_to(config_dir)
                    inv.files.append(str(rel))
                    try:
                        inv.total_size += full.stat().st_size
                    except OSError:
                        pass

        if inv.exists:
            _log.debug("scan_existing: %s exists=%s files=%d size=%s",
                        key, inv.exists, inv.file_count, inv.human_size())
        inventory.agents.append(inv)

    # Check global config files
    home = Path.home()
    globals_to_check = {
        str(home / ".mcp.json"): (home / ".mcp.json").exists(),
        str(home / ".jai"): (home / ".jai").exists(),
        str(home / ".coding-agents.json"): (home / ".coding-agents.json").exists(),
    }
    inventory.global_files = globals_to_check

    return inventory


def backup_agent_dir(inv: AgentInventory) -> Path | None:
    """Create a .tar.gz backup of an agent's config directory.

    Backup is stored next to the source: e.g., ~/.claude.backup-2026-04-11.tar.gz

    Returns the backup path, or None if no backup was needed/possible.
    """
    _log.debug("backup_agent_dir: %s (exists=%s, dir=%s)", inv.agent_key, inv.exists, inv.config_dir)
    if not inv.exists or not inv.config_dir.exists():
        return None

    today = date.today().isoformat()
    backup_name = f"{inv.config_dir.name}.backup-{today}.tar.gz"
    backup_path = inv.config_dir.parent / backup_name

    # Don't overwrite existing backup from today
    if backup_path.exists():
        # Add a sequence number
        for seq in range(1, 100):
            alt = inv.config_dir.parent / f"{inv.config_dir.name}.backup-{today}-{seq}.tar.gz"
            if not alt.exists():
                backup_path = alt
                break

    try:
        with tarfile.open(str(backup_path), "w:gz") as tar:
            tar.add(
                str(inv.config_dir),
                arcname=inv.config_dir.name,
                filter=_tar_filter,
            )
        inv.backup_path = backup_path
        return backup_path
    except (OSError, tarfile.TarError):
        return None


def _tar_filter(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
    """Filter for tar: skip node_modules, .git, __pycache__, and symlinks."""
    # Reject symlinks and hardlinks to prevent information leakage
    if tarinfo.issym() or tarinfo.islnk():
        return None
    skip_dirs = ("node_modules", ".git", "__pycache__")
    for skip in skip_dirs:
        if f"/{skip}/" in tarinfo.name or tarinfo.name.endswith(f"/{skip}"):
            return None
    return tarinfo


def scan_project_existing(project_path: Path) -> dict[str, list[str]]:
    """Scan a project directory for existing agent configs.

    Returns dict mapping category to list of found paths:
      {"agent_configs": [...], "instruction_files": [...], "other": [...]}
    """
    found: dict[str, list[str]] = {
        "agent_configs": [],
        "instruction_files": [],
        "other": [],
    }

    # Agent config dirs in project
    agent_dirs = [".claude", ".codex", ".pi", ".opencode", ".gemini"]
    for d in agent_dirs:
        path = project_path / d
        if path.exists():
            found["agent_configs"].append(d)

    # Instruction files
    instruction_files = ["AGENTS.md", "CLAUDE.md", "GEMINI.md", "agents.md", "opencode.json"]
    for f in instruction_files:
        path = project_path / f
        if path.exists():
            found["instruction_files"].append(f)

    # Other relevant files
    other_files = [".gitignore", ".vscode/extensions.json"]
    for f in other_files:
        path = project_path / f
        if path.exists():
            found["other"].append(f)

    return found
