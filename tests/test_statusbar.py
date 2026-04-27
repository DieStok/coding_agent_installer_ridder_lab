"""Tests for the ccstatusline statusline integration.

Replaces the prior claude-statusbar (`cs --hide-pet`) flow. ccstatusline is:
  - baked into the SIF via bundled/sif/package.json
  - additionally npm-installed into <install_dir>/node_modules at install time
    (local mode + HPC fallback for stale SIFs)
  - wired into ~/.claude/settings.json as the statusLine.command.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest


def test_sif_package_json_pins_ccstatusline():
    """Sprint 1.5+: ccstatusline must be in the SIF's pinned dependency
    list so the in-SIF /opt/agents/node_modules/.bin/ccstatusline resolves
    bare `ccstatusline` invocations from inside Claude Code."""
    pkg_path = (
        Path(__file__).resolve().parent.parent
        / "src" / "coding_agents" / "bundled" / "sif" / "package.json"
    )
    pkg = json.loads(pkg_path.read_text())
    assert "ccstatusline" in pkg["dependencies"], (
        "ccstatusline missing from bundled/sif/package.json — the SIF won't "
        "have the binary, and Claude's statusLine.command will silently fail "
        "inside SLURM jobs."
    )
    # Pinned exact, not floating, so SIF builds are reproducible.
    pinned = pkg["dependencies"]["ccstatusline"]
    assert pinned[0].isdigit(), (
        f"ccstatusline must be pinned to an exact version, got {pinned!r} "
        "(use `2.2.10`, not `^2.2.10` or `*`)."
    )


def test_sif_def_symlinks_ccstatusline():
    """The .def's `for bin in ...` loop must include ccstatusline so the
    binary is exposed in /usr/local/bin/ in addition to
    /opt/agents/node_modules/.bin/ — defence-in-depth for any
    PATH-restricted contexts inside the SIF."""
    def_path = (
        Path(__file__).resolve().parent.parent
        / "src" / "coding_agents" / "bundled" / "coding_agent_hpc.def"
    )
    text = def_path.read_text()
    # The symlink loop iterates a quoted bin list.
    assert "for bin in claude codex opencode pi ccstatusline" in text


def test_install_claude_statusbar_writes_correct_settings(tmp_path, monkeypatch):
    """The `_install_claude_statusbar` function should write a
    statusLine block into ~/.claude/settings.json with `command:
    "ccstatusline"` (bare binary lookup, NOT `cs --hide-pet` or
    `npx ccstatusline`)."""
    from coding_agents.installer import executor

    # Redirect HOME so the test doesn't touch the real ~/.claude/.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    # Stub the npm install call — we're testing the settings emission,
    # not the network call.
    async def _fake_run_in_thread(fn, *args, **kwargs):
        return None

    monkeypatch.setattr(executor, "_run_in_thread", _fake_run_in_thread)

    # Stub the RichLog so log.write() is a no-op.
    class _FakeLog:
        def write(self, *a, **kw):
            pass

    asyncio.run(
        executor._install_claude_statusbar(_FakeLog(), install_dir=tmp_path / "install")
    )

    settings_path = tmp_path / ".claude" / "settings.json"
    assert settings_path.exists(), (
        "_install_claude_statusbar must create ~/.claude/settings.json "
        "(or merge into existing)."
    )

    settings = json.loads(settings_path.read_text())
    sl = settings.get("statusLine")
    assert sl is not None, "statusLine block missing from emitted settings.json"
    assert sl["type"] == "command"
    assert sl["command"] == "ccstatusline", (
        f"statusLine.command should be the bare `ccstatusline` binary, got {sl['command']!r}. "
        "Pre-Sprint-1.5 used `cs --hide-pet` (claude-statusbar via uv) which silently "
        "failed inside the SIF since uv-installed binaries aren't on the SIF PATH."
    )
    assert sl.get("refreshInterval") == 10
    assert sl.get("padding") == 0


def test_install_claude_statusbar_calls_npm_install_with_pinned_version(tmp_path, monkeypatch):
    """Verify the function asks npm_install for the exact pinned ccstatusline
    version. If this fails because the version pin moved, update both the
    test and bundled/sif/package.json in lockstep."""
    from coding_agents.installer import executor

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    captured_calls = []

    async def _fake_run_in_thread(fn, *args, **kwargs):
        captured_calls.append((fn.__name__, args, kwargs))

    monkeypatch.setattr(executor, "_run_in_thread", _fake_run_in_thread)

    class _FakeLog:
        def write(self, *a, **kw):
            pass

    # Force --local mode so the npm install actually runs (HPC mode now
    # skips it because ccstatusline is baked into the SIF).
    asyncio.run(
        executor._install_claude_statusbar(
            _FakeLog(), install_dir=tmp_path / "install", mode="local"
        )
    )

    npm_calls = [c for c in captured_calls if c[0] == "npm_install"]
    assert npm_calls, "npm_install was never called for ccstatusline"
    # First positional after the install_dir is the package spec.
    args = npm_calls[0][1]
    assert len(args) >= 2
    package_spec = args[1]
    assert package_spec.startswith("ccstatusline@"), (
        f"npm_install called with {package_spec!r}; expected `ccstatusline@<version>`."
    )
    # Verify the pinned version matches the constant.
    assert package_spec == f"ccstatusline@{executor._CCSTATUSLINE_VERSION}"


def test_install_claude_statusbar_preserves_other_settings(tmp_path, monkeypatch):
    """If the user already has a settings.json with other keys (theme,
    permissions, MCP, etc.), the statusbar emit must NOT clobber them."""
    from coding_agents.installer import executor

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({
        "theme": "dark",
        "permissions": {"deny": ["Read(./.env)"]},
        "_user_pinned_setting": "preserved",
    }) + "\n")

    async def _fake_run_in_thread(fn, *args, **kwargs):
        return None

    monkeypatch.setattr(executor, "_run_in_thread", _fake_run_in_thread)

    class _FakeLog:
        def write(self, *a, **kw):
            pass

    asyncio.run(
        executor._install_claude_statusbar(_FakeLog(), install_dir=tmp_path / "install")
    )

    settings = json.loads(settings_path.read_text())
    assert settings["theme"] == "dark"
    assert settings["permissions"]["deny"] == ["Read(./.env)"]
    assert settings["_user_pinned_setting"] == "preserved"
    # And the new statusLine is added.
    assert settings["statusLine"]["command"] == "ccstatusline"
