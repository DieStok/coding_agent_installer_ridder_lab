"""Configuration management — read/write ~/.coding-agents.json."""
from __future__ import annotations

import copy
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("coding-agents")

CONFIG_PATH = Path.home() / ".coding-agents.json"

DEFAULT_CONFIG = {
    "install_dir": "",
    "agents": [],
    "skills": [
        "compound-engineering",
        "scientific-agent-skills",
        "autoresearch",
        "crawl4ai",
        "hpc-cluster",
    ],
    "hooks": [
        "agents_md_check",
        "cognitive_reminder",
        "git_check",
        "lint_runner",
        "hpc_validator",
    ],
    "tools": ["crawl4ai", "agent-browser", "linters", "entire"],
    "vscode_extensions": True,
    "jai_enabled": True,
    "mode": "hpc",
    "installed_at": "",
}

# Map hook short names to script filenames
HOOK_SCRIPTS = {
    "agents_md_check": "on_start_agents_md_check.py",
    "cognitive_reminder": "on_start_cognitive_reminder.py",
    "git_check": "on_start_git_check.py",
    "lint_runner": "on_stop_lint_runner.py",
    "hpc_validator": "on_stop_hpc_validator.py",
}

# Skills that are git-cloned vs bundled
GIT_SKILLS = {
    "compound-engineering": "https://github.com/EveryInc/compound-engineering-plugin",
    "scientific-agent-skills": "https://github.com/K-Dense-AI/scientific-agent-skills",
    "autoresearch": "https://github.com/uditgoenka/autoresearch",
}
BUNDLED_SKILLS = ["crawl4ai", "hpc-cluster"]

# Canonical default lists — single source of truth.
# state.py and TUI screens import these rather than defining their own copies.
DEFAULT_SKILLS = list(DEFAULT_CONFIG["skills"])
DEFAULT_HOOKS = list(DEFAULT_CONFIG["hooks"])
DEFAULT_TOOLS = list(DEFAULT_CONFIG["tools"])

# HPC-specific items (skipped in local mode)
HPC_ONLY_SKILLS = {"hpc-cluster"}
HPC_ONLY_HOOKS = {"hpc_validator"}


def build_hook_entries(install_dir: Path, hooks: list[str]) -> list[dict]:
    """Build Claude Code hook entry dicts from hook names.

    Shared by executor.py, sync.py, and project_init.py — single source
    of truth for the hook entry format.
    """
    entries = []
    for hook_name in hooks:
        script = HOOK_SCRIPTS.get(hook_name)
        if not script:
            continue
        hook_path = install_dir / "hooks" / script
        cmd = f"python3 {hook_path}"
        timeout = 30 if "on_stop_" in script else 10
        entries.append({
            "matcher": "",
            "hooks": [{"type": "command", "command": cmd, "timeout": timeout}],
        })
    return entries


def load_config() -> dict:
    """Load config from disk, returning defaults if missing."""
    if CONFIG_PATH.exists():
        try:
            config = json.loads(CONFIG_PATH.read_text())
            log.debug("load_config: loaded from %s (agents=%s, mode=%s)", CONFIG_PATH, config.get("agents"), config.get("mode"))
            return config
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Config file corrupted at %s, using defaults: %s", CONFIG_PATH, exc)
    return copy.deepcopy(DEFAULT_CONFIG)


def save_config(config: dict) -> None:
    """Write config to disk with restricted permissions (0o600)."""
    from coding_agents.dry_run import is_dry_run, would
    from coding_agents.utils import secure_write_text

    log.debug("save_config: writing to %s", CONFIG_PATH)
    if is_dry_run():
        would(
            "config_save",
            "save_config",
            path=CONFIG_PATH,
            keys=sorted(config.keys()),
        )
        return
    secure_write_text(CONFIG_PATH, json.dumps(config, indent=2) + "\n")


def get_install_dir(config: dict | None = None) -> Path:
    """Return the install directory from config."""
    if config is None:
        config = load_config()
    return Path(config["install_dir"]).expanduser()


def update_config(updates: dict) -> dict:
    """Load, merge, save, return."""
    config = load_config()
    config.update(updates)
    save_config(config)
    return config


def mark_installed(config: dict) -> dict:
    """Stamp the installed_at timestamp and save."""
    config["installed_at"] = datetime.now(timezone.utc).isoformat()
    save_config(config)
    return config
