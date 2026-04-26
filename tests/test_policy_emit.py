"""Tests for installer/policy_emit.py — managed Claude settings + Codex TOML."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from coding_agents.installer.policy_emit import (
    merge_claude_settings,
    merge_codex_deny_paths,
)


def test_merge_claude_settings_appends_deny_entries():
    template = {
        "_comment": "should be stripped",
        "allowManagedMcpServersOnly": True,
        "permissions": {"disableBypassPermissionsMode": "disable", "deny": ["Read(./pre-existing)"]},
    }
    deny_rules = {"claude_code_permissions": {"deny": ["Read(./.env)", "Read(~/.ssh/**)"]}}
    out = merge_claude_settings(template, deny_rules)
    assert "_comment" not in out
    assert out["allowManagedMcpServersOnly"] is True
    assert "Read(./pre-existing)" in out["permissions"]["deny"]
    assert "Read(./.env)" in out["permissions"]["deny"]
    assert "Read(~/.ssh/**)" in out["permissions"]["deny"]


def test_merge_claude_settings_dedupes():
    template = {"permissions": {"deny": ["Read(./.env)"]}}
    deny_rules = {"claude_code_permissions": {"deny": ["Read(./.env)", "Read(./.env.*)"]}}
    out = merge_claude_settings(template, deny_rules)
    # ./.env appears once, not twice
    assert out["permissions"]["deny"].count("Read(./.env)") == 1


def test_merge_codex_deny_paths_preserves_other_keys():
    existing = {
        "model": "gpt-5",
        "approval_policy": "ask",
        "sandbox": {"existing_key": "preserved", "deny_paths": ["./old"]},
    }
    deny_paths = ["./.env", "~/.ssh"]
    out = merge_codex_deny_paths(existing, deny_paths)
    assert out["model"] == "gpt-5"
    assert out["approval_policy"] == "ask"
    assert out["sandbox"]["existing_key"] == "preserved"
    assert out["sandbox"]["deny_paths"] == ["./old", "./.env", "~/.ssh"]


def test_merge_codex_deny_paths_empty_existing():
    out = merge_codex_deny_paths({}, ["./.env"])
    assert out == {"sandbox": {"deny_paths": ["./.env"]}}


def test_merge_codex_deny_paths_dedupes():
    existing = {"sandbox": {"deny_paths": ["./.env"]}}
    out = merge_codex_deny_paths(existing, ["./.env", "~/.ssh"])
    assert out["sandbox"]["deny_paths"] == ["./.env", "~/.ssh"]


def test_managed_settings_template_has_correct_nesting():
    """Security H2 / [CORRECTED] nesting — disableBypassPermissionsMode lives
    under permissions.* and is the string "disable"."""
    template_path = Path(__file__).resolve().parent.parent / "src" / "coding_agents" / "bundled" / "templates" / "managed-claude-settings.json"
    data = json.loads(template_path.read_text())
    assert data["allowManagedMcpServersOnly"] is True
    assert data["permissions"]["disableBypassPermissionsMode"] == "disable"
    assert data["sandbox"]["failIfUnavailable"] is True


def test_deny_rules_covers_security_critical_paths():
    """Expanded deny list (security-sentinel) — must cover the home-dir
    secrets that the cwd-only sandbox doesn't bind anyway, as defence-
    in-depth for any future $HOME bind regression."""
    deny_rules_path = Path(__file__).resolve().parent.parent / "src" / "coding_agents" / "bundled" / "hooks" / "deny_rules.json"
    data = json.loads(deny_rules_path.read_text())
    deny = data["claude_code_permissions"]["deny"]
    for needed in ("Read(~/.ssh/**)", "Read(~/.gnupg/**)", "Read(~/.aws/**)", "Read(~/.kube/**)", "Read(~/.netrc)"):
        assert needed in deny, f"deny_rules missing critical path: {needed}"
    # Fixed: ./build → ./build/**
    assert "Read(./build/**)" in deny
    assert "Read(./build)" not in deny


def test_install_managed_claude_settings_dry_run_writes_nothing(tmp_path):
    """Dry-run gap fix: policy emit must not touch disk in dry-run."""
    from coding_agents.dry_run import set_dry_run
    from coding_agents.installer.policy_emit import install_managed_claude_settings

    template_path = Path(__file__).resolve().parent.parent / "src" / "coding_agents" / "bundled" / "templates" / "managed-claude-settings.json"
    deny_rules_path = Path(__file__).resolve().parent.parent / "src" / "coding_agents" / "bundled" / "hooks" / "deny_rules.json"
    target = tmp_path / "claude" / "settings.json"

    # Pre-existing target with different content (would trigger backup)
    target.parent.mkdir()
    target.write_text('{"old": true}\n')
    target_mtime_before = target.stat().st_mtime
    backup_glob = list(target.parent.glob("*.backup-*"))
    assert backup_glob == []

    set_dry_run(True)
    try:
        install_managed_claude_settings(template_path, deny_rules_path, target)
    finally:
        set_dry_run(False)

    # Target file content unchanged + no backup created
    assert target.read_text() == '{"old": true}\n'
    assert target.stat().st_mtime == target_mtime_before
    assert list(target.parent.glob("*.backup-*")) == []


def test_install_codex_deny_paths_dry_run_writes_nothing(tmp_path):
    """Same gap for codex TOML emit."""
    from coding_agents.dry_run import set_dry_run
    from coding_agents.installer.policy_emit import install_codex_deny_paths

    deny_rules_path = Path(__file__).resolve().parent.parent / "src" / "coding_agents" / "bundled" / "hooks" / "deny_rules.json"
    target = tmp_path / "codex" / "config.toml"
    target.parent.mkdir()
    target.write_text('model = "gpt-4"\n')
    target_mtime_before = target.stat().st_mtime

    set_dry_run(True)
    try:
        install_codex_deny_paths(deny_rules_path, target)
    finally:
        set_dry_run(False)

    assert target.read_text() == 'model = "gpt-4"\n'
    assert target.stat().st_mtime == target_mtime_before
    assert list(target.parent.glob("*.backup-*")) == []


def test_deny_rules_codex_paths_match_claude():
    """Single source of truth — Codex toml deny_paths should mirror the
    Claude deny set (modulo formatting)."""
    deny_rules_path = Path(__file__).resolve().parent.parent / "src" / "coding_agents" / "bundled" / "hooks" / "deny_rules.json"
    data = json.loads(deny_rules_path.read_text())
    codex = data["codex_config_toml_deny_paths"]
    # Spot-check the security-critical ones
    assert "~/.ssh" in codex
    assert "~/.gnupg" in codex
    assert "~/.aws" in codex
    assert "./.env" in codex
