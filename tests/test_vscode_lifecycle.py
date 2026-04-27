"""Tests for the VSCode-wrapping lifecycle integration: sync re-emit + uninstall cleanup.

Plan-fidelity reviewer flagged these as FAIL: sync/update should re-emit
wrapper settings (mitigates VSCode self-rewrites), uninstall should clear
both the wrapper keys and the cached jobid. Pinned by these tests.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from coding_agents.commands import sync as sync_module
from coding_agents.commands import uninstall as uninstall_module
from coding_agents.installer.policy_emit import emit_managed_vscode_settings
from coding_agents.runtime import agent_vscode


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
# sync re-emit
# --------------------------------------------------------------------------- #

def test_sync_reemits_wrapper_settings(fake_home, install_dir):
    """sync._sync_vscode_wrapper_settings should re-merge the wrapper hooks."""
    settings = fake_home / ".vscode-server" / "data" / "User" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"editor.fontSize": 14}))
    sync_module._sync_vscode_wrapper_settings(install_dir, ["claude", "pi"])
    parsed = json.loads(settings.read_text())
    assert parsed["editor.fontSize"] == 14
    assert parsed["claudeCode.claudeProcessWrapper"] == str(install_dir / "bin" / "agent-claude-vscode")
    assert parsed["pi-vscode.path"] == str(install_dir / "bin" / "agent-pi-vscode")


def test_sync_skips_when_no_wrappable_agents(fake_home, install_dir):
    settings = fake_home / ".vscode-server" / "data" / "User" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{}")
    sync_module._sync_vscode_wrapper_settings(install_dir, ["gemini"])
    # File untouched
    assert settings.read_text() == "{}"


# --------------------------------------------------------------------------- #
# uninstall cleanup
# --------------------------------------------------------------------------- #

def test_uninstall_clears_wrapper_keys_and_cache(fake_home, install_dir, monkeypatch):
    """unset_managed_vscode_settings + run_vscode_reset both fire from uninstall."""
    settings = fake_home / ".vscode-server" / "data" / "User" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({
        "editor.fontSize": 14,
        "pi-vscode.path": str(install_dir / "bin" / "agent-pi-vscode"),
        "claudeCode.useTerminal": False,
    }))

    # Pre-populate the jobid cache the way a live install would.
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(fake_home / "runtime"))
    cache_p = agent_vscode.cache_path()
    cache_p.parent.mkdir(parents=True, exist_ok=True)
    state = agent_vscode.initial_state(vscode_session="ppid:1")
    state["job_id"] = 9999
    agent_vscode.write_cache(cache_p, state)

    # Mock scancel so vscode_reset doesn't actually try.
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        ),
    )

    # Drive the uninstall snippet directly (the full run_uninstall is wired
    # to ~/.coding-agents.json and an interactive prompt; we exercise just
    # the wrapper-cleanup block via the same imports).
    from coding_agents.installer.policy_emit import unset_managed_vscode_settings
    from coding_agents.commands.vscode_reset import run_vscode_reset
    cleared = unset_managed_vscode_settings()
    run_vscode_reset()

    parsed = json.loads(settings.read_text())
    assert parsed["editor.fontSize"] == 14
    assert parsed["pi-vscode.path"] is None
    assert parsed["claudeCode.useTerminal"] is None
    assert cleared == settings
    assert not cache_p.exists()


def test_unset_keys_derived_from_emit_keys(install_dir, fake_home):
    """unset_managed_vscode_settings must null every key emit_managed_vscode_settings can write.

    Pinned because the previous hard-coded list could drift from
    _vscode_wrapper_keys when a new agent is added.
    """
    from coding_agents.installer.policy_emit import (
        _vscode_wrapper_keys,
        emit_managed_vscode_settings,
        unset_managed_vscode_settings,
    )

    settings = fake_home / ".vscode-server" / "data" / "User" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{}")
    emit_managed_vscode_settings(install_dir, ["claude", "codex", "opencode", "pi"])
    emitted_keys = set(_vscode_wrapper_keys(install_dir, ["claude", "codex", "opencode", "pi"]).keys())

    unset_managed_vscode_settings()
    parsed = json.loads(settings.read_text())
    for key in emitted_keys:
        assert parsed.get(key) is None, (
            f"unset() left {key} populated — drift from emit_managed_vscode_settings"
        )


# --------------------------------------------------------------------------- #
# Race-condition fix: cache written immediately after salloc
# --------------------------------------------------------------------------- #

def test_cache_written_before_srun(fake_home, install_dir, monkeypatch):
    """Plan + race-review HIGH#2: the cache must contain the jobid before
    srun runs, so a SIGKILL between salloc and srun doesn't orphan the job."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(fake_home / "runtime"))
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.delenv("CODING_AGENTS_NO_WRAP", raising=False)
    monkeypatch.setattr(agent_vscode, "squeue_job_alive", lambda jid: True)

    cache_p = agent_vscode.cache_path()
    captured_when_srun = {}

    def fake_run(cmd, *a, **kw):
        if cmd[0] == "salloc":
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="",
                stderr="salloc: Granted job allocation 7777\n",
            )
        if cmd[0] == "srun":
            # At this point the cache must already hold job_id 7777.
            captured_when_srun["cache"] = agent_vscode.read_cache(cache_p)
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    bin_dir = install_dir / "bin"
    (bin_dir / "agent-pi").write_text("#!/bin/sh\n")

    rc = agent_vscode.run_with_lock("pi", [], install_dir, vscode_session="ipc:test")
    assert rc == 0
    cache = captured_when_srun["cache"]
    assert cache is not None and cache["job_id"] == 7777


# --------------------------------------------------------------------------- #
# vscode_session_key heuristic
# --------------------------------------------------------------------------- #

def test_session_key_prefers_ipc_handle(monkeypatch):
    monkeypatch.setenv("VSCODE_GIT_IPC_HANDLE", "/tmp/sock-1")
    monkeypatch.setenv("VSCODE_PID", "1234")
    assert agent_vscode.vscode_session_key() == "ipc:/tmp/sock-1"


def test_session_key_falls_back_to_vscode_pid(monkeypatch):
    monkeypatch.delenv("VSCODE_GIT_IPC_HANDLE", raising=False)
    monkeypatch.setenv("VSCODE_PID", "1234")
    assert agent_vscode.vscode_session_key() == "pid:1234"


def test_session_key_last_resort_ppid(monkeypatch):
    monkeypatch.delenv("VSCODE_GIT_IPC_HANDLE", raising=False)
    monkeypatch.delenv("VSCODE_PID", raising=False)
    key = agent_vscode.vscode_session_key()
    assert key.startswith("ppid:")


# --------------------------------------------------------------------------- #
# _strip_block doesn't damage user blank-line spacing
# --------------------------------------------------------------------------- #

def test_strip_block_preserves_user_blank_lines_elsewhere(fake_home, install_dir):
    """A user with intentional double-blank-line spacing elsewhere in their
    .bashrc should NOT see those collapsed when our block is stripped."""
    from coding_agents.utils import (
        SHELL_MARKERS,
        _strip_block,
        inject_shell_block,
        remove_shell_block,
    )
    rc = fake_home / ".bashrc"
    rc.write_text(
        "alias foo=bar\n"
        "\n"
        "\n"
        "# user comment with intentional blank-line above\n"
    )
    inject_shell_block(install_dir, inject_path_shim=False)
    # Now strip — user's content should keep its blank-line spacing.
    remove_shell_block()
    content = rc.read_text()
    assert "alias foo=bar\n\n\n# user comment" in content
