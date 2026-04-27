"""Tests for convert_mcp — per-agent MCP config writers.

Sprint 1 Tasks 1.5 (OpenCode shape fix) and 1.6 (Pi imports + toolPrefix).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Pi: Sprint 1 Task 1.6 — imports directive + toolPrefix fix
# ---------------------------------------------------------------------------


def test_pi_emits_imports_directive_not_mcp_servers(tmp_path):
    """Synthesis §3.10/§4.16/§5.21 / Sprint 1 Task 1.6: Pi inherits MCP
    from Claude's managed ~/.mcp.json via pi-mcp-adapter's `imports`
    magic name. No duplicated mcpServers dict.
    """
    from coding_agents.convert_mcp import _write_pi

    fake_home = tmp_path
    servers = {
        "filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        }
    }
    _write_pi(servers, fake_home)

    written = json.loads((fake_home / ".pi" / "agent" / "mcp.json").read_text())
    assert written["imports"] == ["claude-code"]
    # No duplicated mcpServers dict — they live in ~/.mcp.json now.
    assert "mcpServers" not in written


def test_pi_toolprefix_in_enum(tmp_path):
    """Synthesis §3.10 part 1: pi-mcp-adapter's toolPrefix enum is
    {"server", "none", "short"}. The previous value "mcp" was a bug
    that pi-mcp-adapter silently rejected.
    """
    from coding_agents.convert_mcp import _write_pi

    _write_pi({}, tmp_path)
    written = json.loads((tmp_path / ".pi" / "agent" / "mcp.json").read_text())

    assert written["toolPrefix"] == "short"
    # Defence-in-depth: assert the value is in the enum, so a future typo
    # ("Short", "MCP") trips this test.
    assert written["toolPrefix"] in {"server", "none", "short"}


def test_pi_preserves_settings_idle_timeout(tmp_path):
    """The ``settings`` block is consumed by pi-coding-agent itself (not
    pi-mcp-adapter). Keep idleTimeout there so we don't regress that
    behaviour while moving toolPrefix to top-level.
    """
    from coding_agents.convert_mcp import _write_pi

    _write_pi({}, tmp_path)
    written = json.loads((tmp_path / ".pi" / "agent" / "mcp.json").read_text())
    assert written["settings"]["idleTimeout"] == 10


def test_pi_existing_mcp_json_backed_up_before_overwrite(tmp_path):
    """Synthesis §4.16: Pi MCP overwrite without backup destroyed user
    customisations on every sync. Folded into Task 1.6 — back up
    pre-existing differing content before re-emit.
    """
    from coding_agents.convert_mcp import _write_pi

    pi_dir = tmp_path / ".pi" / "agent"
    pi_dir.mkdir(parents=True)
    target = pi_dir / "mcp.json"
    target.write_text('{"mcpServers": {"old": {"command": "x"}}}\n')

    _write_pi({}, tmp_path)

    backups = list(pi_dir.glob("mcp.backup-*.json"))
    assert backups, (
        "Pi mcp.json overwrite must back up the pre-existing differing "
        "content (synthesis §4.16). No .backup-* file found."
    )
    # The backup contains the old content, the live file contains the new.
    assert "mcpServers" in backups[0].read_text()
    assert "imports" in target.read_text()
    assert "mcpServers" not in target.read_text()


def test_pi_mcp_json_no_backup_when_unchanged(tmp_path):
    """Drift backup is content-aware: re-emit with identical content
    must not create a .backup-* file (idempotent)."""
    from coding_agents.convert_mcp import _write_pi

    _write_pi({}, tmp_path)
    backups_before = list((tmp_path / ".pi" / "agent").glob("mcp.backup-*.json"))

    # Re-emit with the same servers — content identical
    _write_pi({}, tmp_path)
    backups_after = list((tmp_path / ".pi" / "agent").glob("mcp.backup-*.json"))

    assert backups_before == backups_after, (
        "Idempotent re-emit must not create new backups."
    )


# ---------------------------------------------------------------------------
# OpenCode: Sprint 1 Task 1.5 — Effect Schema-correct shape
# ---------------------------------------------------------------------------


def test_opencode_emits_local_with_command_array_and_environment(tmp_path):
    """Synthesis §3.9 / Sprint 1 Task 1.5: OpenCode's Effect Schema
    requires the discriminated-union shape. Three things must be right:
    type literal, command as array, environment (not env).
    """
    from coding_agents.convert_mcp import _write_opencode

    servers = {
        "filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            "env": {"FOO": "bar"},
        }
    }
    _write_opencode(servers, tmp_path)
    written = json.loads(
        (tmp_path / ".config" / "opencode" / "opencode.json").read_text()
    )

    fs = written["mcp"]["filesystem"]
    assert fs["type"] == "local"
    # command is an array of strings, [cmd, *args]
    assert fs["command"] == ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    # env → environment (Effect Schema renames it)
    assert "env" not in fs
    assert fs["environment"] == {"FOO": "bar"}
    assert fs["enabled"] is True


def test_opencode_emits_remote_with_url_and_optional_headers(tmp_path):
    """Remote MCP entries get type: "remote" + url + optional headers."""
    from coding_agents.convert_mcp import _write_opencode

    servers = {
        "remote-svc": {
            "url": "https://mcp.example.com/v1",
            "headers": {"Authorization": "Bearer xxx"},
        }
    }
    _write_opencode(servers, tmp_path)
    written = json.loads(
        (tmp_path / ".config" / "opencode" / "opencode.json").read_text()
    )

    svc = written["mcp"]["remote-svc"]
    assert svc["type"] == "remote"
    assert svc["url"] == "https://mcp.example.com/v1"
    assert svc["headers"] == {"Authorization": "Bearer xxx"}
    assert svc["enabled"] is True


def test_opencode_skips_entry_without_command_or_url(tmp_path, caplog):
    """Defensive: an entry with neither command nor url is skipped with a
    warning rather than emitted with a missing required field (which
    Effect Schema would reject for the whole config)."""
    from coding_agents.convert_mcp import _write_opencode

    servers = {"borked": {"args": ["nope"]}}
    _write_opencode(servers, tmp_path)
    written = json.loads(
        (tmp_path / ".config" / "opencode" / "opencode.json").read_text()
    )
    assert "borked" not in written["mcp"]


def test_opencode_writer_no_longer_uses_generic_lambda(tmp_path):
    """Regression guard for synthesis §3.9: ensure the dispatch table
    routes 'opencode' to the dedicated _write_opencode, not the
    generic _write_json_mcp lambda that produced the wrong shape."""
    from coding_agents import convert_mcp

    # Read the source to confirm the dispatch table change.
    src_path = (
        Path(convert_mcp.__file__).resolve()
    )
    src = src_path.read_text()
    # The buggy lambda had this exact substring; it must not be in the
    # opencode dispatch any more.
    assert (
        '"opencode": lambda s, h: _write_json_mcp(s, h, h / ".config/opencode/opencode.json"'
        not in src
    ), (
        "OpenCode dispatch is back on the generic _write_json_mcp lambda "
        "that emits the wrong Effect Schema shape (synthesis §3.9). Use "
        "the dedicated _write_opencode writer."
    )


def test_opencode_merges_into_existing_config(tmp_path):
    """If ~/.config/opencode/opencode.json already has user-managed keys
    other than `mcp`, they must be preserved across the merge."""
    from coding_agents.convert_mcp import _write_opencode

    config_dir = tmp_path / ".config" / "opencode"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "opencode.json"
    config_path.write_text(json.dumps({"theme": "tokyonight", "model": "claude-sonnet-4-6"}) + "\n")

    _write_opencode(
        {"fs": {"command": "npx", "args": ["fs"]}},
        tmp_path,
    )

    written = json.loads(config_path.read_text())
    assert written["theme"] == "tokyonight"
    assert written["model"] == "claude-sonnet-4-6"
    assert written["mcp"]["fs"]["type"] == "local"
