"""Tests for the OpenCode permissions emitter (v1.1.1+ unified schema)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from coding_agents.installer.policy_emit import (
    build_opencode_permissions,
    install_opencode_permissions,
)


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    return tmp_path


# --------------------------------------------------------------------------- #
# build_opencode_permissions — pure function
# --------------------------------------------------------------------------- #

def test_default_actions_set():
    perm = build_opencode_permissions([])
    assert perm["*"] == "ask"
    assert perm["edit"] == "ask"
    assert perm["webfetch"] == "ask"


def test_read_block_excludes_env_files():
    perm = build_opencode_permissions([])
    assert perm["read"]["*"] == "allow"
    assert perm["read"]["*.env"] == "deny"
    assert perm["read"]["*.env.example"] == "allow"


def test_lab_deny_rules_become_bash_deny_patterns():
    rules = ["rm -rf *", "chmod -R *"]
    perm = build_opencode_permissions(rules)
    assert perm["bash"]["rm -rf *"] == "deny"
    assert perm["bash"]["chmod -R *"] == "deny"


def test_safe_prefixes_get_allow():
    perm = build_opencode_permissions([])
    for safe in ("git *", "ls *", "cat *", "grep *", "rg *", "find *", "pwd"):
        assert perm["bash"][safe] == "allow"


def test_bash_default_is_ask():
    perm = build_opencode_permissions([])
    assert perm["bash"]["*"] == "ask"


def test_user_deny_overrides_safe_allow_when_listed_first():
    """Lab rules are inserted before safe-allows; OpenCode applies last-match
    so user-supplied rules don't accidentally override safe defaults unless
    the user explicitly lists them."""
    perm = build_opencode_permissions(["git push *"])
    # Both keys present; OpenCode resolves by last-match in the wire dict
    assert perm["bash"]["git push *"] == "deny"
    assert perm["bash"]["git *"] == "allow"


# --------------------------------------------------------------------------- #
# install_opencode_permissions — file emission
# --------------------------------------------------------------------------- #

def test_install_writes_opencode_json(fake_home):
    target = install_opencode_permissions(["rm -rf *"])
    assert target == fake_home / ".config" / "opencode" / "opencode.json"
    parsed = json.loads(target.read_text())
    assert parsed["$schema"] == "https://opencode.ai/config.json"
    assert parsed["permission"]["bash"]["rm -rf *"] == "deny"


def test_install_preserves_user_keys(fake_home):
    target = fake_home / ".config" / "opencode" / "opencode.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"theme": "dark", "model": "claude-3.5"}))
    install_opencode_permissions([])
    parsed = json.loads(target.read_text())
    assert parsed["theme"] == "dark"
    assert parsed["model"] == "claude-3.5"
    assert "permission" in parsed


def test_install_idempotent(fake_home):
    install_opencode_permissions(["rm -rf *"])
    first = (fake_home / ".config" / "opencode" / "opencode.json").read_text()
    install_opencode_permissions(["rm -rf *"])
    second = (fake_home / ".config" / "opencode" / "opencode.json").read_text()
    assert first == second


def test_install_overwrites_old_permission_key(fake_home):
    """Re-running install replaces our managed permission block but keeps user keys."""
    target = fake_home / ".config" / "opencode" / "opencode.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({
        "theme": "dark",
        "permission": {"bash": "allow"},  # old user setting
    }))
    install_opencode_permissions(["rm -rf *"])
    parsed = json.loads(target.read_text())
    assert parsed["theme"] == "dark"
    # New permission block has structure, not the old "allow" string
    assert isinstance(parsed["permission"]["bash"], dict)
    assert parsed["permission"]["bash"]["rm -rf *"] == "deny"


def test_install_handles_malformed_json(fake_home):
    target = fake_home / ".config" / "opencode" / "opencode.json"
    target.parent.mkdir(parents=True)
    target.write_text("{not json")
    # Should backup + write fresh, not crash
    result = install_opencode_permissions(["rm -rf *"])
    assert result == target
    parsed = json.loads(target.read_text())
    assert "permission" in parsed
