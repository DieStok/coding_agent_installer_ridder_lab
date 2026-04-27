"""Phase 2: Claude-specific behaviour for the VSCode extension wrapping."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from coding_agents.installer.policy_emit import (
    _vscode_wrapper_keys,
    emit_managed_vscode_settings,
)
from coding_agents.installer.wrapper_vscode import (
    EXTENSION_STUBS,
    emit_extension_stubs,
)
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
# Claude stub + settings keys
# --------------------------------------------------------------------------- #

def test_claude_stub_argv(install_dir):
    written = emit_extension_stubs(install_dir, ["claude"])
    content = written[0].read_text()
    assert "--agent claude" in content
    assert "exec " in content


def test_emit_includes_all_claude_keys(fake_home, install_dir):
    settings = fake_home / ".vscode-server" / "data" / "User" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{}")
    emit_managed_vscode_settings(install_dir, ["claude"])
    parsed = json.loads(settings.read_text())
    assert parsed["claudeCode.claudeProcessWrapper"] == str(install_dir / "bin" / "agent-claude-vscode")
    assert parsed["claudeCode.useTerminal"] is False
    assert parsed["claudeCode.disableLoginPrompt"] is True
    assert parsed["claudeCode.initialPermissionMode"] == "acceptEdits"
    assert parsed["claudeCode.environmentVariables"] == [
        {"name": "CLAUDE_CODE_ENTRYPOINT", "value": "claude-vscode"}
    ]


def test_useTerminal_explicitly_false(install_dir):
    """Defends against the wrapper-bypass-when-true gotcha (deep-research §5.5)."""
    keys = _vscode_wrapper_keys(install_dir, ["claude"])
    assert keys["claudeCode.useTerminal"] is False, (
        "useTerminal=True would bypass our wrapper by routing claude through "
        "the integrated terminal — must stay False."
    )


# --------------------------------------------------------------------------- #
# Env passthrough — claude has the largest list
# --------------------------------------------------------------------------- #

def test_claude_env_passthrough_full_list():
    parent = {name: f"value-{name}" for name in agent_vscode.ENV_PASSTHROUGH["claude"]}
    overlay = agent_vscode.passthrough_env("claude", parent)
    for name in agent_vscode.ENV_PASSTHROUGH["claude"]:
        assert overlay[f"APPTAINERENV_{name}"] == f"value-{name}"


def test_claude_env_passthrough_includes_sse_port():
    overlay = agent_vscode.passthrough_env("claude", {"CLAUDE_CODE_SSE_PORT": "37386"})
    assert overlay == {"APPTAINERENV_CLAUDE_CODE_SSE_PORT": "37386"}


def test_claude_env_passthrough_includes_anthropic_keys():
    overlay = agent_vscode.passthrough_env(
        "claude",
        {
            "ANTHROPIC_API_KEY": "sk-ant-x",
            "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
            "ANTHROPIC_CONFIG_DIR": "/foo",
        },
    )
    assert overlay["APPTAINERENV_ANTHROPIC_API_KEY"] == "sk-ant-x"
    assert overlay["APPTAINERENV_ANTHROPIC_BASE_URL"] == "https://api.anthropic.com"
    assert overlay["APPTAINERENV_ANTHROPIC_CONFIG_DIR"] == "/foo"


# --------------------------------------------------------------------------- #
# Apptainer binds — claude needs ~/.claude rw + cache/bun ro + TLS/DNS
# --------------------------------------------------------------------------- #

def test_claude_binds_include_claude_dir(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)
    (fake_home / ".claude.json").write_text("{}")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    binds = agent_vscode.build_apptainer_binds("claude")
    # Match by host:target:mode shape
    assert any(b.endswith(":rw") and ".claude:" in b for b in binds)


def test_claude_binds_include_claude_json_separately(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / ".claude.json").write_text("{}")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    binds = agent_vscode.build_apptainer_binds("claude")
    assert any("/.claude.json:" in b and b.endswith(":rw") for b in binds)


def test_claude_binds_skip_missing_paths(tmp_path, monkeypatch):
    fake_home = tmp_path / "empty"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    binds = agent_vscode.build_apptainer_binds("claude")
    # Nothing should reference the empty fake home dir
    for b in binds:
        assert not b.startswith(str(fake_home / ".claude"))


# --------------------------------------------------------------------------- #
# srun env carries APPTAINER_BIND with our claude binds
# --------------------------------------------------------------------------- #

def test_claude_srun_appends_apptainer_bind(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.delenv("CODING_AGENTS_NO_WRAP", raising=False)
    monkeypatch.setenv("APPTAINER_BIND", "/scratch:/scratch")
    monkeypatch.setattr(agent_vscode, "squeue_job_alive", lambda jid: True)

    install_dir = tmp_path / "install"
    bin_dir = install_dir / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "agent-claude").write_text("#!/bin/sh\n")

    captured_env: dict = {}

    def fake_run(cmd, *a, **kw):
        if cmd[0] == "salloc":
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="",
                stderr="salloc: Granted job allocation 1\n",
            )
        if cmd[0] == "srun":
            captured_env.update(kw.get("env") or {})
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    rc = agent_vscode.run_with_lock("claude", [], install_dir, cursor_pid=1)
    assert rc == 0
    bind = captured_env["APPTAINER_BIND"]
    assert "/scratch:/scratch" in bind  # pre-existing preserved
    assert str(fake_home / ".claude") in bind
