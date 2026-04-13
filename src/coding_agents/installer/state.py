"""Shared installer state passed through all TUI screens."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from coding_agents.agents import PRESETS
from coding_agents.config import DEFAULT_HOOKS, DEFAULT_SKILLS, DEFAULT_TOOLS


@dataclass
class InstallerState:
    """Mutable state shared across all installer screens."""

    install_dir: str = ""
    preset: str = "core"
    agents: list[str] = field(default_factory=lambda: list(PRESETS["core"]))
    vscode_extensions: bool = True
    tools: list[str] = field(default_factory=lambda: list(DEFAULT_TOOLS))
    jai_enabled: bool = True
    skills: list[str] = field(default_factory=lambda: list(DEFAULT_SKILLS))
    hooks: list[str] = field(default_factory=lambda: list(DEFAULT_HOOKS))
    mode: str = "hpc"  # "hpc" or "local"

    @property
    def install_path(self) -> Path:
        return Path(self.install_dir).expanduser()

    def to_config_dict(self) -> dict:
        """Convert to the shape stored in ~/.coding-agents.json."""
        return {
            "install_dir": self.install_dir,
            "agents": self.agents,
            "skills": self.skills,
            "hooks": self.hooks,
            "tools": self.tools,
            "vscode_extensions": self.vscode_extensions,
            "jai_enabled": self.jai_enabled,
            "mode": self.mode,
        }

    @classmethod
    def from_config(cls, config: dict) -> InstallerState:
        """Create state from an existing config dict (for re-runs)."""
        return cls(
            install_dir=config.get("install_dir", ""),
            agents=config.get("agents", list(PRESETS["core"])),
            vscode_extensions=config.get("vscode_extensions", True),
            tools=config.get("tools", list(DEFAULT_TOOLS)),
            jai_enabled=config.get("jai_enabled", True),
            skills=config.get("skills", list(DEFAULT_SKILLS)),
            hooks=config.get("hooks", list(DEFAULT_HOOKS)),
            mode=config.get("mode", "hpc"),
        )
