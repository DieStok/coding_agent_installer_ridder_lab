"""Phase 3: Codex-specific behaviour for the VSCode extension wrapping."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from coding_agents.commands import doctor_vscode
from coding_agents.installer.policy_emit import emit_managed_vscode_settings
from coding_agents.installer.wrapper_vscode import emit_extension_stubs
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
# Codex stub + settings keys
# --------------------------------------------------------------------------- #

def test_codex_stub_argv(install_dir):
    written = emit_extension_stubs(install_dir, ["codex"])
    content = written[0].read_text()
    assert "--agent codex" in content


def test_emit_includes_codex_keys(fake_home, install_dir):
    settings = fake_home / ".vscode-server" / "data" / "User" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{}")
    emit_managed_vscode_settings(install_dir, ["codex"])
    parsed = json.loads(settings.read_text())
    assert parsed["chatgpt.cliExecutable"] == str(install_dir / "bin" / "agent-codex-vscode")
    assert parsed["chatgpt.openOnStartup"] is False


# --------------------------------------------------------------------------- #
# Env passthrough
# --------------------------------------------------------------------------- #

def test_codex_env_passthrough_full_list():
    parent = {name: f"v-{name}" for name in agent_vscode.ENV_PASSTHROUGH["codex"]}
    overlay = agent_vscode.passthrough_env("codex", parent)
    for name in agent_vscode.ENV_PASSTHROUGH["codex"]:
        assert overlay[f"APPTAINERENV_{name}"] == f"v-{name}"


def test_codex_env_includes_codex_home():
    overlay = agent_vscode.passthrough_env("codex", {"CODEX_HOME": "/foo"})
    assert overlay == {"APPTAINERENV_CODEX_HOME": "/foo"}


# --------------------------------------------------------------------------- #
# Apptainer binds — codex needs ~/.codex rw + /tmp + /dev/shm + TLS/DNS
# --------------------------------------------------------------------------- #

def test_codex_binds_include_codex_dir(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    (fake_home / ".codex").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    binds = agent_vscode.build_apptainer_binds("codex")
    assert any(".codex:" in b and b.endswith(":rw") for b in binds)


def test_codex_binds_include_tmp_when_present(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    binds = agent_vscode.build_apptainer_binds("codex")
    # /tmp typically exists on the test host; we only check the rule is there
    # if so. If it doesn't exist (rare), skip — don't false-fail the suite.
    if Path("/tmp").exists():
        assert any(b.startswith("/tmp:/tmp:") for b in binds)


# --------------------------------------------------------------------------- #
# Codex protocol-drift doctor check
# --------------------------------------------------------------------------- #

def test_normalize_version_picks_major_minor():
    assert doctor_vscode._normalize_version("codex 26.422.30944") == "26.422"
    assert doctor_vscode._normalize_version("v0.1.1\n") == "0.1"


def test_normalize_version_returns_none_on_garbage():
    assert doctor_vscode._normalize_version("no digits here") is None


def test_codex_version_drift_pass(monkeypatch):
    monkeypatch.setattr(doctor_vscode, "_read_codex_extension_version", lambda: "26.422")
    monkeypatch.setattr(doctor_vscode, "_read_codex_sif_version", lambda p: "26.422")
    row = doctor_vscode.codex_version_drift_check(Path("/fake.sif"))
    assert row is not None
    name, status, fix = row
    assert status == "pass"
    assert "26.422" in fix


def test_codex_version_drift_warns_on_mismatch(monkeypatch):
    monkeypatch.setattr(doctor_vscode, "_read_codex_extension_version", lambda: "26.422")
    monkeypatch.setattr(doctor_vscode, "_read_codex_sif_version", lambda p: "1.99")
    row = doctor_vscode.codex_version_drift_check(Path("/fake.sif"))
    assert row is not None
    name, status, fix = row
    assert status == "warn"
    assert "26.422" in fix and "1.99" in fix


def test_codex_version_drift_returns_none_when_unreadable(monkeypatch):
    monkeypatch.setattr(doctor_vscode, "_read_codex_extension_version", lambda: None)
    monkeypatch.setattr(doctor_vscode, "_read_codex_sif_version", lambda p: "26.422")
    assert doctor_vscode.codex_version_drift_check(Path("/fake.sif")) is None


# --------------------------------------------------------------------------- #
# PTY off for codex (uses pipes, not PTY)
# --------------------------------------------------------------------------- #

def test_codex_srun_no_pty_when_isatty_false(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.delenv("CODING_AGENTS_NO_WRAP", raising=False)
    import os as _os
    monkeypatch.setattr(_os, "isatty", lambda fd: False)
    monkeypatch.setattr(agent_vscode, "squeue_job_alive", lambda jid: True)

    install_dir = tmp_path / "install"
    bin_dir = install_dir / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "agent-codex").write_text("#!/bin/sh\n")

    captured = []

    def fake_run(cmd, *a, **kw):
        captured.append(list(cmd))
        if cmd[0] == "salloc":
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="",
                stderr="salloc: Granted job allocation 5\n",
            )
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    rc = agent_vscode.run_with_lock("codex", [], install_dir, vscode_session="ppid:1")
    assert rc == 0
    srun_cmd = next(c for c in captured if c[0] == "srun")
    assert "--pty" not in srun_cmd, "codex extension uses pipes; --pty would break stdio"
