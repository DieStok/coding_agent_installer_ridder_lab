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


def test_install_agent_runs_curl_for_claude(fake_install_dir, monkeypatch):
    """Claude (curl method) still installs as before — only npm method changed."""
    import asyncio
    from coding_agents.installer import executor
    from coding_agents.agents import AGENTS

    run_called = MagicMock(return_value=None)
    # Patch the run_in_thread → run path via the run import in executor.
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

    # Skip the statusline install — its details aren't relevant here.
    async def _noop(*a, **kw):
        return None
    monkeypatch.setattr(executor, "_install_claude_statusbar", _noop)

    log = MagicMock()
    log.write = MagicMock()

    asyncio.run(executor._install_agent("claude", AGENTS["claude"], fake_install_dir, log))
    # `run` should have been called at least once for the curl install.
    assert run_called.call_count >= 1
