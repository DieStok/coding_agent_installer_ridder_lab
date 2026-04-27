"""Phase 2: install no longer runs `npm install` for codex/opencode/pi.

The SIF has all three agents baked in; the wrapper template + NO_WRAP=1 path
both route through the SIF, so the host npm install was dead weight.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def fake_install_dir(tmp_path):
    p = tmp_path / "install"
    (p / "bin").mkdir(parents=True)
    return p


@pytest.mark.parametrize("agent_key", ["codex", "opencode", "pi"])
def test_install_agent_skips_npm_for_sif_baked_agents(agent_key, fake_install_dir, monkeypatch):
    """For npm-method agents, _install_agent must NOT call npm_install anymore."""
    import asyncio
    from coding_agents.installer import executor
    from coding_agents.agents import AGENTS

    # Spy on npm_install — it should never be called.
    npm_called = MagicMock()
    monkeypatch.setattr(executor, "npm_install", npm_called)

    log = MagicMock()
    log.write = MagicMock()

    asyncio.run(executor._install_agent(agent_key, AGENTS[agent_key], fake_install_dir, log))
    npm_called.assert_not_called()

    # The log line announcing the skip should be present.
    log_calls = " ".join(call.args[0] for call in log.write.call_args_list if call.args)
    assert "skipping host npm install" in log_calls.lower() or "from the SIF" in log_calls


def test_install_agent_skips_curl_for_claude_in_hpc_mode(fake_install_dir, monkeypatch):
    """Claude is also baked into the SIF — host curl install is dead weight
    in HPC mode for the same reasons codex/opencode/pi were. Verify the
    curl install does NOT run when mode is HPC (or default)."""
    import asyncio
    from coding_agents.installer import executor
    from coding_agents.agents import AGENTS

    run_called = MagicMock(return_value=None)
    monkeypatch.setattr(executor, "run", run_called)

    # statusbar still gets called for the settings.json bookkeeping.
    statusbar_calls: list[dict] = []

    async def _track(*a, **kw):
        statusbar_calls.append(kw)
    monkeypatch.setattr(executor, "_install_claude_statusbar", _track)

    log = MagicMock()
    log.write = MagicMock()

    # mode="hpc" (default) — no curl install.
    asyncio.run(executor._install_agent(
        "claude", AGENTS["claude"], fake_install_dir, log, mode="hpc"
    ))
    run_called.assert_not_called()
    log_calls = " ".join(c.args[0] for c in log.write.call_args_list if c.args)
    assert "skipping host curl install" in log_calls.lower() or "from the SIF" in log_calls
    # statusbar was still called (for settings.json), with mode hpc.
    assert any(kw.get("mode") == "hpc" for kw in statusbar_calls), (
        "_install_claude_statusbar should still run in HPC mode for "
        "settings.json bookkeeping (with mode=hpc to skip its npm install)"
    )


def test_install_agent_runs_curl_for_claude_in_local_mode(fake_install_dir, monkeypatch):
    """In --local mode there's no SIF, so claude curl install must still
    run as before."""
    import asyncio
    from coding_agents.installer import executor
    from coding_agents.agents import AGENTS

    run_called = MagicMock(return_value=None)
    monkeypatch.setattr(executor, "run", run_called)

    # Ensure Claude's binary is "found" so we don't hit the FileNotFoundError tail.
    fake_claude = fake_install_dir / "fake-claude"
    fake_claude.parent.mkdir(parents=True, exist_ok=True)
    fake_claude.write_text("#!/bin/sh\n")
    monkeypatch.setattr(
        Path, "home", staticmethod(lambda: fake_install_dir.parent)
    )
    (fake_install_dir.parent / ".claude" / "bin").mkdir(parents=True, exist_ok=True)
    (fake_install_dir.parent / ".claude" / "bin" / "claude").write_text("#!/bin/sh\n")

    async def _noop(*a, **kw):
        return None
    monkeypatch.setattr(executor, "_install_claude_statusbar", _noop)

    log = MagicMock()
    log.write = MagicMock()

    asyncio.run(executor._install_agent(
        "claude", AGENTS["claude"], fake_install_dir, log, mode="local"
    ))
    assert run_called.call_count >= 1


def test_install_claude_statusbar_skips_npm_in_hpc_mode(fake_install_dir, monkeypatch):
    """ccstatusline is baked into the SIF (bundled/sif/package.json) so
    the host npm install is dead weight in HPC mode. The settings.json
    write still happens because it's host-side bookkeeping."""
    import asyncio
    import json
    from coding_agents.installer import executor

    npm_called = MagicMock()
    monkeypatch.setattr(executor, "npm_install", npm_called)
    monkeypatch.setattr(
        Path, "home", staticmethod(lambda: fake_install_dir.parent)
    )

    log = MagicMock()
    log.write = MagicMock()

    asyncio.run(executor._install_claude_statusbar(
        log, install_dir=fake_install_dir, mode="hpc"
    ))
    npm_called.assert_not_called()

    # settings.json must still have the statusLine entry.
    settings = fake_install_dir.parent / ".claude" / "settings.json"
    assert settings.exists()
    parsed = json.loads(settings.read_text())
    assert parsed["statusLine"]["command"] == "ccstatusline"


def test_create_sandbox_wrappers_creates_bare_name_symlinks(fake_install_dir, monkeypatch, tmp_path):
    """Each agent-<key> wrapper gets a bare-name symlink <key> →
    agent-<key> in bin/. So `claude` / `codex` / `pi` / `opencode` on
    PATH all route through the SIF wrapper, not a host install (which
    no longer exists in HPC mode)."""
    import asyncio
    from coding_agents.installer import executor

    state = MagicMock()
    state.agents = ["claude", "codex", "opencode", "pi"]
    state.sandbox_sif_path = "/dummy/sif"

    log = MagicMock()
    log.write = MagicMock()

    asyncio.run(executor._create_sandbox_wrappers(state, fake_install_dir, log))

    bin_dir = fake_install_dir / "bin"
    for key in ("claude", "codex", "opencode", "pi"):
        wrapper = bin_dir / f"agent-{key}"
        bare = bin_dir / key
        assert wrapper.exists(), f"missing wrapper {wrapper}"
        assert bare.is_symlink(), f"missing bare-name symlink {bare}"
        # Relative target so install_dir rename still works.
        import os
        assert os.readlink(bare) == f"agent-{key}", (
            f"bare {bare} should symlink to relative `agent-{key}`, "
            f"got {os.readlink(bare)}"
        )
