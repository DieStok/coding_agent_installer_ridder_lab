"""Phase 5: ``coding-agents vscode-reset`` clears the cached SLURM session."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from coding_agents.commands import vscode_reset
from coding_agents.runtime import agent_vscode


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    return tmp_path / "coding-agents"


def test_reset_noop_when_no_cache(isolated_cache, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("should not run"))
    assert vscode_reset.run_vscode_reset() == 0


def test_reset_removes_cache_and_calls_scancel(isolated_cache):
    cache_p = agent_vscode.cache_path()
    cache_p.parent.mkdir(parents=True, exist_ok=True)
    state = agent_vscode.initial_state(vscode_session="ppid:1")
    state["job_id"] = 4242
    agent_vscode.write_cache(cache_p, state)

    calls = []

    def fake_run(cmd, *a, **kw):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    import coding_agents.commands.vscode_reset as vr
    vr.subprocess.run = fake_run  # type: ignore[attr-defined]

    rc = vscode_reset.run_vscode_reset()
    assert rc == 0
    assert calls and calls[0] == ["scancel", "4242"]
    assert not cache_p.exists()


def test_reset_handles_scancel_failure_but_still_removes_cache(isolated_cache):
    cache_p = agent_vscode.cache_path()
    cache_p.parent.mkdir(parents=True, exist_ok=True)
    state = agent_vscode.initial_state(vscode_session="ppid:1")
    state["job_id"] = 4242
    agent_vscode.write_cache(cache_p, state)

    def fake_run(cmd, *a, **kw):
        return subprocess.CompletedProcess(
            args=cmd, returncode=1, stdout="", stderr="invalid jobid"
        )

    import coding_agents.commands.vscode_reset as vr
    vr.subprocess.run = fake_run  # type: ignore[attr-defined]

    rc = vscode_reset.run_vscode_reset()
    assert rc == 0
    assert not cache_p.exists()


def test_reset_skips_scancel_when_no_job_id(isolated_cache):
    cache_p = agent_vscode.cache_path()
    cache_p.parent.mkdir(parents=True, exist_ok=True)
    state = agent_vscode.initial_state(vscode_session="ppid:1")
    # job_id is None — no scancel needed
    agent_vscode.write_cache(cache_p, state)

    calls = []

    def fake_run(cmd, *a, **kw):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    import coding_agents.commands.vscode_reset as vr
    vr.subprocess.run = fake_run  # type: ignore[attr-defined]

    rc = vscode_reset.run_vscode_reset()
    assert rc == 0
    assert calls == []  # no scancel was attempted
    assert not cache_p.exists()
