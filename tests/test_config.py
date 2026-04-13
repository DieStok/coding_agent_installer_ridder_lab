"""Tests for config.py — JSON config read/write."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def test_default_config_structure():
    from coding_agents.config import DEFAULT_CONFIG

    assert "install_dir" in DEFAULT_CONFIG
    assert "agents" in DEFAULT_CONFIG
    assert "skills" in DEFAULT_CONFIG
    assert "hooks" in DEFAULT_CONFIG
    assert isinstance(DEFAULT_CONFIG["skills"], list)


def test_load_config_returns_defaults_when_missing():
    from coding_agents.config import load_config

    with patch("coding_agents.config.CONFIG_PATH", Path("/nonexistent/.coding-agents.json")):
        config = load_config()
        assert config["install_dir"] == ""
        assert isinstance(config["agents"], list)


def test_save_and_load_roundtrip():
    from coding_agents.config import load_config, save_config

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp = Path(f.name)

    try:
        with patch("coding_agents.config.CONFIG_PATH", tmp):
            test_config = {"install_dir": "/test/path", "agents": ["claude", "codex"]}
            save_config(test_config)
            loaded = load_config()
            assert loaded["install_dir"] == "/test/path"
            assert loaded["agents"] == ["claude", "codex"]
    finally:
        tmp.unlink(missing_ok=True)


def test_hook_scripts_mapping():
    from coding_agents.config import HOOK_SCRIPTS

    assert "agents_md_check" in HOOK_SCRIPTS
    assert HOOK_SCRIPTS["agents_md_check"] == "on_start_agents_md_check.py"
    assert "lint_runner" in HOOK_SCRIPTS
    assert HOOK_SCRIPTS["lint_runner"] == "on_stop_lint_runner.py"


def test_git_skills_urls():
    from coding_agents.config import GIT_SKILLS

    assert "compound-engineering" in GIT_SKILLS
    assert "autoresearch" in GIT_SKILLS
    assert "github.com" in GIT_SKILLS["compound-engineering"]
