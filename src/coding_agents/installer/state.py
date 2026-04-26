"""Shared installer state passed through all TUI screens."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from coding_agents.agents import PRESETS
from coding_agents.config import (
    DEFAULT_HOOKS,
    DEFAULT_SANDBOX_SIF_PATH,
    DEFAULT_SKILLS,
    DEFAULT_SLURM_DEFAULTS,
    DEFAULT_TOOLS,
)


@dataclass
class InstallerState:
    """Mutable state shared across all installer screens."""

    install_dir: str = ""
    preset: str = "core"
    agents: list[str] = field(default_factory=lambda: list(PRESETS["core"]))
    vscode_extensions: bool = True
    tools: list[str] = field(default_factory=lambda: list(DEFAULT_TOOLS))
    skills: list[str] = field(default_factory=lambda: list(DEFAULT_SKILLS))
    hooks: list[str] = field(default_factory=lambda: list(DEFAULT_HOOKS))
    mode: str = "hpc"  # "hpc" or "local"

    # Real per-install sandbox state (the wrapper actually reads these)
    sandbox_sif_path: str = DEFAULT_SANDBOX_SIF_PATH
    sandbox_secrets_dir: str = ""  # filled in from $USER at install
    sandbox_logs_dir: str = ""  # filled in from $USER at install

    # SLURM submission defaults — TUI display + sbatch template only;
    # the wrapper itself never reads these.
    slurm_defaults: dict[str, Any] = field(
        default_factory=lambda: dict(DEFAULT_SLURM_DEFAULTS)
    )

    @property
    def install_path(self) -> Path:
        return Path(self.install_dir).expanduser()

    @property
    def sandbox_secrets_path(self) -> Path:
        return Path(self.sandbox_secrets_dir).expanduser()

    @property
    def sandbox_logs_path(self) -> Path:
        return Path(self.sandbox_logs_dir).expanduser()

    @property
    def sandbox_sif_path_p(self) -> Path:
        return Path(self.sandbox_sif_path).expanduser()

    def to_config_dict(self) -> dict:
        """Convert to the shape stored in ~/.coding-agents.json."""
        return {
            "install_dir": self.install_dir,
            "agents": self.agents,
            "skills": self.skills,
            "hooks": self.hooks,
            "tools": self.tools,
            "vscode_extensions": self.vscode_extensions,
            "mode": self.mode,
            "sandbox_sif_path": self.sandbox_sif_path,
            "sandbox_secrets_dir": self.sandbox_secrets_dir,
            "sandbox_logs_dir": self.sandbox_logs_dir,
            "slurm_defaults": dict(self.slurm_defaults),
        }

    @classmethod
    def from_config(cls, config: dict) -> InstallerState:
        """Create state from an existing config dict (for re-runs)."""
        return cls(
            install_dir=config.get("install_dir", ""),
            agents=config.get("agents", list(PRESETS["core"])),
            vscode_extensions=config.get("vscode_extensions", True),
            tools=config.get("tools", list(DEFAULT_TOOLS)),
            skills=config.get("skills", list(DEFAULT_SKILLS)),
            hooks=config.get("hooks", list(DEFAULT_HOOKS)),
            mode=config.get("mode", "hpc"),
            sandbox_sif_path=config.get("sandbox_sif_path", DEFAULT_SANDBOX_SIF_PATH),
            sandbox_secrets_dir=config.get("sandbox_secrets_dir", ""),
            sandbox_logs_dir=config.get("sandbox_logs_dir", ""),
            slurm_defaults=dict(config.get("slurm_defaults", DEFAULT_SLURM_DEFAULTS)),
        )
