"""Tests for the uninstall-side reverse-merge helpers."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from coding_agents.commands import uninstall


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """Redirect ``Path.home()`` so settings/backup writes land in tmp."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / ".claude").mkdir()
    return tmp_path


# ----------- _restore_oldest_settings_backup -----------

def test_restore_oldest_when_multiple_backups(fake_home):
    claude = fake_home / ".claude"
    (claude / "settings.backup-2026-04-26.json").write_text('{"original": true}')
    (claude / "settings.backup-2026-04-28.json").write_text('{"later": true}')
    (claude / "settings.json").write_text('{"current": true}')

    restored = uninstall._restore_oldest_settings_backup()
    assert restored is not None
    assert restored.name == "settings.backup-2026-04-26.json"
    assert json.loads((claude / "settings.json").read_text()) == {"original": True}
    # Oldest backup is consumed; the later one stays for inspection.
    assert not restored.exists()
    assert (claude / "settings.backup-2026-04-28.json").exists()


def test_restore_returns_none_when_no_backups(fake_home):
    (fake_home / ".claude" / "settings.json").write_text('{"x": 1}')
    assert uninstall._restore_oldest_settings_backup() is None
    # settings.json untouched
    assert json.loads((fake_home / ".claude" / "settings.json").read_text()) == {"x": 1}


# ----------- _strip_template_keys -----------

def test_strip_template_keys_removes_install_defaults(fake_home):
    settings = fake_home / ".claude" / "settings.json"
    settings.write_text(json.dumps({
        "$schema": "https://json.schemastore.org/claude-code-settings.json",
        "_comment": "Default Claude Code settings emitted by coding-agents installer ...",
        "allowManagedMcpServersOnly": True,
        "permissions": {
            "disableBypassPermissionsMode": "disable",
            "deny": ["Read(./.env)"],
        },
        "sandbox": {"failIfUnavailable": True},
        "userKey": "preserved",
    }))

    removed = uninstall._strip_template_keys(settings)
    assert removed == 4

    data = json.loads(settings.read_text())
    assert "_comment" not in data
    assert "allowManagedMcpServersOnly" not in data
    assert "disableBypassPermissionsMode" not in data["permissions"]
    assert "failIfUnavailable" not in data["sandbox"]
    # User's own keys + $schema (informational) preserved
    assert data["userKey"] == "preserved"
    assert "$schema" in data
    # permissions.deny untouched here — that's the unmerge step's job
    assert data["permissions"]["deny"] == ["Read(./.env)"]


def test_strip_template_keys_preserves_user_edits(fake_home):
    """If the user flipped disableBypassPermissionsMode, leave their value alone."""
    settings = fake_home / ".claude" / "settings.json"
    settings.write_text(json.dumps({
        "permissions": {"disableBypassPermissionsMode": "enable"},
        "allowManagedMcpServersOnly": False,
    }))

    removed = uninstall._strip_template_keys(settings)
    assert removed == 0

    data = json.loads(settings.read_text())
    # Both still present because their values diverged from install defaults.
    assert data["permissions"]["disableBypassPermissionsMode"] == "enable"
    assert data["allowManagedMcpServersOnly"] is False


def test_strip_template_keys_handles_missing_file(fake_home):
    assert uninstall._strip_template_keys(fake_home / ".claude" / "nope.json") == 0


def test_strip_template_keys_handles_malformed_json(fake_home):
    settings = fake_home / ".claude" / "settings.json"
    settings.write_text("{not valid json")
    assert uninstall._strip_template_keys(settings) == 0


# ----------- _unmerge_settings_json end-to-end -----------

def test_unmerge_prefers_backup_restore(fake_home, tmp_path):
    """When a dated backup exists, restore wins and skip marker/template strip."""
    claude = fake_home / ".claude"
    (claude / "settings.backup-2026-04-25.json").write_text(
        json.dumps({"userKey": "pristine"})
    )
    # Current settings.json has both marker-tagged and template-introduced keys.
    (claude / "settings.json").write_text(json.dumps({
        "_comment": "Default Claude Code settings emitted by coding-agents installer x",
        "allowManagedMcpServersOnly": True,
        "hooks": {
            "SessionStart": [
                {"matcher": "ours", "hooks": [], "_coding_agents_managed": True},
                {"matcher": "user", "hooks": []},
            ]
        },
        "permissions": {
            "disableBypassPermissionsMode": "disable",
            "deny": ["Read(./.env)"],
        },
    }))

    install_dir = tmp_path / "install"
    (install_dir / "hooks").mkdir(parents=True)
    (install_dir / "hooks" / "deny_rules.json").write_text(
        json.dumps({"deny": ["Read(./.env)"]})
    )

    uninstall._unmerge_settings_json(install_dir)

    # settings.json is now exactly the pristine backup content
    assert json.loads((claude / "settings.json").read_text()) == {"userKey": "pristine"}


def test_unmerge_falls_back_to_strip_when_no_backup(fake_home, tmp_path):
    """No backup → marker-strip AND template-key strip both run."""
    claude = fake_home / ".claude"
    (claude / "settings.json").write_text(json.dumps({
        "_comment": "Default Claude Code settings emitted by coding-agents installer x",
        "allowManagedMcpServersOnly": True,
        "hooks": {
            "SessionStart": [
                {"matcher": "ours", "hooks": [], "_coding_agents_managed": True},
                {"matcher": "user", "hooks": []},
            ]
        },
        "permissions": {
            "disableBypassPermissionsMode": "disable",
            "deny": ["Read(./.env)", "user-rule"],
        },
        "sandbox": {"failIfUnavailable": True},
    }))

    install_dir = tmp_path / "install"
    (install_dir / "hooks").mkdir(parents=True)
    (install_dir / "hooks" / "deny_rules.json").write_text(
        json.dumps({"deny": ["Read(./.env)"]})
    )

    uninstall._unmerge_settings_json(install_dir)

    data = json.loads((claude / "settings.json").read_text())
    # Template keys gone
    assert "_comment" not in data
    assert "allowManagedMcpServersOnly" not in data
    assert "disableBypassPermissionsMode" not in data["permissions"]
    assert "failIfUnavailable" not in data["sandbox"]
    # Marker-tagged hook entry gone, user's hook preserved
    assert len(data["hooks"]["SessionStart"]) == 1
    assert data["hooks"]["SessionStart"][0]["matcher"] == "user"
    # Our deny rule stripped, user's preserved
    assert data["permissions"]["deny"] == ["user-rule"]


def test_unmerge_always_strips_mcp_json(fake_home, tmp_path):
    """~/.mcp.json gets the marker-strip whether or not settings backup exists."""
    (fake_home / ".mcp.json").write_text(json.dumps({
        "mcpServers": {
            "ours": {"command": "x", "_coding_agents_managed": True},
            "user": {"command": "y"},
        }
    }))
    # No claude/settings backup, no settings.json — exercises the mcp path alone
    install_dir = tmp_path / "install"
    install_dir.mkdir()

    uninstall._unmerge_settings_json(install_dir)

    data = json.loads((fake_home / ".mcp.json").read_text())
    assert "ours" not in data["mcpServers"]
    assert data["mcpServers"]["user"] == {"command": "y"}
