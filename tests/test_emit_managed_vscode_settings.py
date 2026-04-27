"""Tests for emitting VSCode wrapper hooks into settings.json (Phase 1+)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from coding_agents.installer.policy_emit import (
    _resolve_vscode_settings_path,
    _vscode_wrapper_keys,
    emit_managed_vscode_settings,
    unset_managed_vscode_settings,
)


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.delenv("VSCODE_AGENT_FOLDER", raising=False)
    return tmp_path


@pytest.fixture
def install_dir(tmp_path):
    p = tmp_path / "install"
    (p / "bin").mkdir(parents=True)
    return p


# --------------------------------------------------------------------------- #
# Settings path resolution chain (decision 6)
# --------------------------------------------------------------------------- #

def test_resolve_returns_none_when_no_candidate_exists(fake_home):
    assert _resolve_vscode_settings_path() is None


def test_resolve_finds_cursor_server(fake_home):
    target = fake_home / ".cursor-server" / "data" / "User" / "settings.json"
    target.parent.mkdir(parents=True)
    target.write_text("{}")
    assert _resolve_vscode_settings_path() == target


def test_resolve_finds_vscode_server(fake_home):
    target = fake_home / ".vscode-server" / "data" / "User" / "settings.json"
    target.parent.mkdir(parents=True)
    target.write_text("{}")
    assert _resolve_vscode_settings_path() == target


def test_resolve_env_var_wins(fake_home, monkeypatch):
    cursor = fake_home / ".cursor-server" / "data" / "User" / "settings.json"
    cursor.parent.mkdir(parents=True)
    cursor.write_text("{}")

    custom = fake_home / "custom-vscode" / "data" / "User" / "settings.json"
    custom.parent.mkdir(parents=True)
    custom.write_text("{}")
    monkeypatch.setenv("VSCODE_AGENT_FOLDER", str(custom.parents[2]))
    assert _resolve_vscode_settings_path() == custom


def test_resolve_caller_arg_wins(fake_home, tmp_path):
    # Even with a candidate present, an explicit override is honoured.
    cursor = fake_home / ".cursor-server" / "data" / "User" / "settings.json"
    cursor.parent.mkdir(parents=True)
    cursor.write_text("{}")
    explicit = tmp_path / "explicit.json"
    assert _resolve_vscode_settings_path(explicit) == explicit


# --------------------------------------------------------------------------- #
# Wrapper key construction (per-phase gating)
# --------------------------------------------------------------------------- #

def test_wrapper_keys_pi_only(install_dir):
    keys = _vscode_wrapper_keys(install_dir, ["pi"])
    assert keys == {"pi-vscode.path": str(install_dir / "bin" / "agent-pi-vscode")}


def test_wrapper_keys_claude_includes_useTerminal_false(install_dir):
    keys = _vscode_wrapper_keys(install_dir, ["claude"])
    assert keys["claudeCode.claudeProcessWrapper"] == str(install_dir / "bin" / "agent-claude-vscode")
    assert keys["claudeCode.useTerminal"] is False
    assert keys["claudeCode.disableLoginPrompt"] is True
    assert keys["claudeCode.initialPermissionMode"] == "acceptEdits"
    assert keys["claudeCode.environmentVariables"] == [
        {"name": "CLAUDE_CODE_ENTRYPOINT", "value": "claude-vscode"}
    ]


def test_wrapper_keys_codex(install_dir):
    keys = _vscode_wrapper_keys(install_dir, ["codex"])
    assert keys["chatgpt.cliExecutable"] == str(install_dir / "bin" / "agent-codex-vscode")
    assert keys["chatgpt.openOnStartup"] is False


def test_wrapper_keys_opencode_terminal_path(install_dir):
    keys = _vscode_wrapper_keys(install_dir, ["opencode"])
    term = keys["terminal.integrated.env.linux"]
    assert term["PATH"].startswith(str(install_dir / "bin" / "path-shim"))
    assert "${env:PATH}" in term["PATH"]


def test_wrapper_keys_all_four(install_dir):
    keys = _vscode_wrapper_keys(install_dir, ["pi", "claude", "codex", "opencode"])
    expected_keys = {
        "pi-vscode.path",
        "claudeCode.claudeProcessWrapper",
        "claudeCode.useTerminal",
        "claudeCode.disableLoginPrompt",
        "claudeCode.initialPermissionMode",
        "claudeCode.environmentVariables",
        "chatgpt.cliExecutable",
        "chatgpt.openOnStartup",
        "terminal.integrated.env.linux",
    }
    assert set(keys.keys()) == expected_keys


# --------------------------------------------------------------------------- #
# emit_managed_vscode_settings — end-to-end
# --------------------------------------------------------------------------- #

def test_emit_pi_into_existing_settings(fake_home, install_dir):
    settings = fake_home / ".vscode-server" / "data" / "User" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"editor.fontSize": 14}))

    result = emit_managed_vscode_settings(install_dir, ["pi"])
    assert result == settings
    parsed = json.loads(settings.read_text())
    assert parsed["editor.fontSize"] == 14
    assert parsed["pi-vscode.path"] == str(install_dir / "bin" / "agent-pi-vscode")


def test_emit_creates_bak(fake_home, install_dir):
    settings = fake_home / ".vscode-server" / "data" / "User" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"editor.fontSize": 14}))
    emit_managed_vscode_settings(install_dir, ["pi"])
    bak = settings.with_name(settings.name + ".bak")
    assert bak.exists()


def test_emit_returns_none_when_no_settings_anywhere(fake_home, install_dir):
    assert emit_managed_vscode_settings(install_dir, ["pi"]) is None


def test_emit_idempotent(fake_home, install_dir):
    settings = fake_home / ".vscode-server" / "data" / "User" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{}")
    emit_managed_vscode_settings(install_dir, ["pi"])
    first = settings.read_text()
    emit_managed_vscode_settings(install_dir, ["pi"])
    second = settings.read_text()
    assert first == second


def test_emit_preserves_jsonc_comments_in_input(fake_home, install_dir):
    settings = fake_home / ".vscode-server" / "data" / "User" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        '{\n  // user comment\n  "editor.tabSize": 2,\n}\n'
    )
    emit_managed_vscode_settings(install_dir, ["pi"])
    parsed = json.loads(settings.read_text())
    assert parsed["editor.tabSize"] == 2
    assert parsed["pi-vscode.path"] == str(install_dir / "bin" / "agent-pi-vscode")


def test_unset_writes_null_for_our_keys(fake_home, install_dir):
    settings = fake_home / ".vscode-server" / "data" / "User" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({
        "editor.fontSize": 14,
        "pi-vscode.path": str(install_dir / "bin" / "agent-pi-vscode"),
        "claudeCode.useTerminal": False,
    }))
    unset_managed_vscode_settings()
    parsed = json.loads(settings.read_text())
    assert parsed["editor.fontSize"] == 14
    assert parsed["pi-vscode.path"] is None
    assert parsed["claudeCode.useTerminal"] is None


def test_unset_noop_when_no_settings(fake_home):
    assert unset_managed_vscode_settings() is None
