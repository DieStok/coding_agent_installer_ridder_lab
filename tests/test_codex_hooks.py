"""Tests for Codex hooks emission (replaces the previous "manual setup" skip)."""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from coding_agents.installer.policy_emit import (
    build_codex_hooks_config,
    install_codex_hooks,
)


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    return tmp_path


@pytest.fixture
def install_dir(tmp_path):
    p = tmp_path / "install"
    (p / "hooks").mkdir(parents=True)
    return p


# --------------------------------------------------------------------------- #
# build_codex_hooks_config — pure function
# --------------------------------------------------------------------------- #

def test_routes_on_start_to_session_start(install_dir):
    out = build_codex_hooks_config(install_dir, ["agents_md_check"])
    assert "SessionStart" in out["hooks"]
    entry = out["hooks"]["SessionStart"][0]
    assert entry["matcher"] == "startup|resume"
    assert entry["hooks"][0]["type"] == "command"
    assert "on_start_agents_md_check.py" in entry["hooks"][0]["command"]
    assert entry["hooks"][0]["timeout"] == 10


def test_routes_on_stop_to_stop_event(install_dir):
    out = build_codex_hooks_config(install_dir, ["lint_runner"])
    assert "Stop" in out["hooks"]
    entry = out["hooks"]["Stop"][0]
    assert "matcher" not in entry  # Stop event takes no matcher
    assert "on_stop_lint_runner.py" in entry["hooks"][0]["command"]
    assert entry["hooks"][0]["timeout"] == 30  # longer for on_stop_*


def test_groups_multiple_hooks_under_same_event(install_dir):
    out = build_codex_hooks_config(
        install_dir,
        ["agents_md_check", "git_check", "cognitive_reminder"],
    )
    assert len(out["hooks"]["SessionStart"]) == 3


def test_unknown_hook_skipped(install_dir):
    out = build_codex_hooks_config(install_dir, ["bogus"])
    assert out == {}


def test_empty_input_returns_empty_dict(install_dir):
    assert build_codex_hooks_config(install_dir, []) == {}


# --------------------------------------------------------------------------- #
# install_codex_hooks — file emission
# --------------------------------------------------------------------------- #

def test_install_writes_hooks_json(fake_home, install_dir):
    target = install_codex_hooks(install_dir, ["agents_md_check", "lint_runner"])
    assert target == fake_home / ".codex" / "hooks.json"
    parsed = json.loads(target.read_text())
    assert "SessionStart" in parsed["hooks"]
    assert "Stop" in parsed["hooks"]


def test_install_idempotent(fake_home, install_dir):
    install_codex_hooks(install_dir, ["agents_md_check"])
    first = (fake_home / ".codex" / "hooks.json").read_text()
    install_codex_hooks(install_dir, ["agents_md_check"])
    second = (fake_home / ".codex" / "hooks.json").read_text()
    assert first == second


def test_install_sets_feature_flag(fake_home, install_dir):
    install_codex_hooks(install_dir, ["agents_md_check"])
    config_toml = fake_home / ".codex" / "config.toml"
    parsed = tomllib.loads(config_toml.read_text())
    assert parsed["features"]["codex_hooks"] is True


def test_install_preserves_existing_config_toml(fake_home, install_dir):
    """The feature-flag set must not clobber the sandbox config."""
    config_toml = fake_home / ".codex" / "config.toml"
    config_toml.parent.mkdir(parents=True)
    config_toml.write_text(
        'sandbox_mode = "workspace-write"\n'
        '[sandbox_workspace_write]\n'
        'network_access = true\n'
    )
    install_codex_hooks(install_dir, ["agents_md_check"])
    parsed = tomllib.loads(config_toml.read_text())
    assert parsed["sandbox_mode"] == "workspace-write"
    assert parsed["sandbox_workspace_write"]["network_access"] is True
    assert parsed["features"]["codex_hooks"] is True


def test_install_returns_none_when_no_hooks_map(fake_home, install_dir):
    assert install_codex_hooks(install_dir, ["bogus"]) is None
    # No hooks.json should have been written
    assert not (fake_home / ".codex" / "hooks.json").exists()
