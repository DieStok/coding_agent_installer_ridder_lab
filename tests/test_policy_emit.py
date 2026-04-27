"""Tests for installer/policy_emit.py — managed Claude settings + Codex TOML."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from coding_agents.installer.policy_emit import (
    merge_claude_settings,
    merge_codex_deny_paths,  # back-compat shim
    merge_codex_sandbox_config,
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


def test_merge_codex_sandbox_config_writes_workspace_write_schema():
    """Synthesis §3.7 / Sprint 1 Task 1.4: replace fictional [sandbox]
    deny_paths with the real sandbox_mode + [sandbox_workspace_write]."""
    out = merge_codex_sandbox_config({"model": "gpt-5", "approval_policy": "ask"})
    assert out["model"] == "gpt-5"
    assert out["approval_policy"] == "ask"
    assert out["sandbox_mode"] == "workspace-write"
    sws = out["sandbox_workspace_write"]
    assert sws["network_access"] is True
    assert sws["exclude_tmpdir_env_var"] is False
    assert sws["exclude_slash_tmp"] is False


def test_merge_codex_sandbox_config_drops_legacy_deny_paths():
    """If a user's config still has the fictional [sandbox] deny_paths
    key from the previous version, drop it cleanly."""
    existing = {
        "model": "gpt-5",
        "sandbox": {"deny_paths": ["./old", "~/.ssh"]},
    }
    out = merge_codex_sandbox_config(existing)
    # Empty [sandbox] table dropped entirely
    assert "sandbox" not in out
    assert "deny_paths" not in out.get("sandbox_workspace_write", {})
    assert out["sandbox_mode"] == "workspace-write"


def test_merge_codex_sandbox_config_preserves_other_sandbox_keys():
    """[sandbox] tables that have user-managed keys other than the legacy
    deny_paths are kept (only the bogus key is dropped)."""
    existing = {"sandbox": {"some_user_key": "preserved", "deny_paths": ["./old"]}}
    out = merge_codex_sandbox_config(existing)
    # deny_paths gone, but the user-managed key survives
    assert "deny_paths" not in out["sandbox"]
    assert out["sandbox"]["some_user_key"] == "preserved"


def test_merge_codex_sandbox_config_preserves_user_overrides():
    """If the user already set network_access = false, don't overwrite."""
    existing = {"sandbox_workspace_write": {"network_access": False}}
    out = merge_codex_sandbox_config(existing)
    assert out["sandbox_workspace_write"]["network_access"] is False


def test_back_compat_merge_codex_deny_paths_emits_new_schema():
    """The old merge_codex_deny_paths(existing, deny_paths) shim must still
    work and emit the new schema, ignoring its deny_paths argument."""
    out = merge_codex_deny_paths({"model": "gpt-5"}, ["./irrelevant", "~/.ssh"])
    assert out["sandbox_mode"] == "workspace-write"
    assert "deny_paths" not in out.get("sandbox_workspace_write", {})


def test_managed_settings_template_has_correct_nesting():
    """Security H2 / [CORRECTED] nesting — disableBypassPermissionsMode lives
    under permissions.* and is the string "disable"."""
    template_path = Path(__file__).resolve().parent.parent / "src" / "coding_agents" / "bundled" / "templates" / "managed-claude-settings.json"
    data = json.loads(template_path.read_text())
    assert data["allowManagedMcpServersOnly"] is True
    assert data["permissions"]["disableBypassPermissionsMode"] == "disable"
    assert data["sandbox"]["failIfUnavailable"] is True


def test_managed_settings_template_carries_schema_ref():
    """Sprint 1 Task 1.8 / synthesis §3.8: the template references the
    JSON Schema so the user's editor can validate the file. If the
    schema later requires disableBypassPermissionsMode to be boolean
    (true) instead of the string "disable", the lockstep update is to
    change both the template value and the assertion above."""
    template_path = Path(__file__).resolve().parent.parent / "src" / "coding_agents" / "bundled" / "templates" / "managed-claude-settings.json"
    data = json.loads(template_path.read_text())
    assert data.get("$schema") == "https://json.schemastore.org/claude-code-settings.json", (
        "managed-claude-settings.json should carry $schema for editor "
        "validation (Sprint 1 Task 1.8)."
    )


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


def test_deny_rules_no_longer_contains_fictional_codex_key():
    """Synthesis §3.7 / Sprint 1 Task 1.4: ``codex_config_toml_deny_paths``
    was the path-list payload for the fictional [sandbox] deny_paths key.
    The real Codex sandbox schema doesn't accept path-list denies; sandbox
    behaviour is gated via sandbox_mode + [sandbox_workspace_write] now,
    so this key is gone from deny_rules.json."""
    deny_rules_path = Path(__file__).resolve().parent.parent / "src" / "coding_agents" / "bundled" / "hooks" / "deny_rules.json"
    data = json.loads(deny_rules_path.read_text())
    assert "codex_config_toml_deny_paths" not in data, (
        "deny_rules.json should not contain the fictional Codex deny-paths "
        "key after Sprint 1 Task 1.4. Codex sandbox behaviour is now "
        "configured via sandbox_mode in policy_emit.merge_codex_sandbox_config."
    )
