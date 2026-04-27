"""Tests for the SLURM session helper used by VSCode extension wrappers."""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from coding_agents.runtime import agent_vscode


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """Redirect cache_dir() to a tmp path and clear SLURM env."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.delenv("CODING_AGENTS_NO_WRAP", raising=False)
    return tmp_path / "coding-agents"


@pytest.fixture
def install_dir(tmp_path):
    bin_dir = tmp_path / "install" / "bin"
    bin_dir.mkdir(parents=True)
    for agent in agent_vscode.VALID_AGENTS:
        (bin_dir / f"agent-{agent}").write_text("#!/bin/sh\necho stub\n")
    return tmp_path / "install"


# --------------------------------------------------------------------------- #
# Argv parsing
# --------------------------------------------------------------------------- #

def test_parse_args_basic():
    agent, argv = agent_vscode.parse_args(["--agent", "claude", "--", "--print", "hi"])
    assert agent == "claude"
    assert argv == ["--print", "hi"]


def test_parse_args_no_forward():
    agent, argv = agent_vscode.parse_args(["--agent", "pi"])
    assert agent == "pi"
    assert argv == []


def test_parse_args_invalid_agent():
    with pytest.raises(SystemExit):
        agent_vscode.parse_args(["--agent", "bogus"])


# --------------------------------------------------------------------------- #
# Cache I/O
# --------------------------------------------------------------------------- #

def test_cache_dir_uses_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert agent_vscode.cache_dir() == tmp_path / "coding-agents"


def test_cache_dir_falls_back_to_home(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    assert agent_vscode.cache_dir() == tmp_path / ".coding-agents"


def test_read_cache_missing_returns_none(tmp_path):
    assert agent_vscode.read_cache(tmp_path / "nope.json") is None


def test_read_cache_invalid_json_returns_none(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("not json")
    assert agent_vscode.read_cache(p) is None


def test_read_cache_wrong_schema_returns_none(tmp_path):
    p = tmp_path / "old.json"
    p.write_text(json.dumps({"schema_version": 99, "job_id": 1}))
    assert agent_vscode.read_cache(p) is None


def test_write_then_read_roundtrip(tmp_path):
    p = tmp_path / "session.json"
    state = agent_vscode.initial_state(vscode_session=42)
    state["job_id"] = 12345
    agent_vscode.write_cache(p, state)
    assert agent_vscode.read_cache(p) == state
    # File written with 0o600
    assert (p.stat().st_mode & 0o777) == 0o600


# --------------------------------------------------------------------------- #
# Failure-budget logic
# --------------------------------------------------------------------------- #

def _stamp_seconds_ago(seconds: float) -> str:
    when = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=seconds)
    return when.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def test_refuse_zero_count_never():
    state = {"failure_count": 0, "last_failure_at": None}
    assert not agent_vscode.should_refuse_persistent_failure(state)


def test_refuse_count1_within_cooldown():
    state = {"failure_count": 1, "last_failure_at": _stamp_seconds_ago(5)}
    assert agent_vscode.should_refuse_persistent_failure(state) is True


def test_allow_count1_after_cooldown():
    state = {"failure_count": 1, "last_failure_at": _stamp_seconds_ago(60)}
    assert agent_vscode.should_refuse_persistent_failure(state) is False


def test_refuse_count2_unconditionally_within_age_out():
    state = {"failure_count": 2, "last_failure_at": _stamp_seconds_ago(60)}
    assert agent_vscode.should_refuse_persistent_failure(state) is True


def test_age_out_4h_resets():
    state = {"failure_count": 5, "last_failure_at": _stamp_seconds_ago(5 * 3600)}
    assert agent_vscode.should_refuse_persistent_failure(state) is False


# --------------------------------------------------------------------------- #
# squeue / salloc parsing
# --------------------------------------------------------------------------- #

def test_squeue_alive_when_returncode_zero_and_stdout(monkeypatch):
    fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="12345\n", stderr="")
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fake)
    assert agent_vscode.squeue_job_alive(12345) is True


def test_squeue_dead_when_empty(monkeypatch):
    fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fake)
    assert agent_vscode.squeue_job_alive(12345) is False


def test_squeue_dead_when_missing(monkeypatch):
    def boom(*a, **kw):
        raise FileNotFoundError(2, "no squeue")
    monkeypatch.setattr(subprocess, "run", boom)
    assert agent_vscode.squeue_job_alive(12345) is False


def test_allocate_via_salloc_parses_stderr(monkeypatch):
    fake = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="",
        stderr="salloc: Granted job allocation 7654321\n",
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fake)
    job_id, cmd, err = agent_vscode.allocate_via_salloc(vscode_session=999)
    assert job_id == 7654321
    assert "--no-shell" in cmd
    assert err == ""


def test_allocate_via_salloc_failure(monkeypatch):
    fake = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="salloc: error: invalid account\n"
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fake)
    job_id, cmd, err = agent_vscode.allocate_via_salloc(vscode_session=1)
    assert job_id is None
    assert "invalid account" in err


def test_allocate_via_salloc_command_not_found(monkeypatch):
    def boom(*a, **kw):
        raise FileNotFoundError(2, "no salloc")
    monkeypatch.setattr(subprocess, "run", boom)
    job_id, cmd, err = agent_vscode.allocate_via_salloc(vscode_session=1)
    assert job_id is None
    assert "FileNotFoundError" in err


# --------------------------------------------------------------------------- #
# Bind expansion + env passthrough
# --------------------------------------------------------------------------- #

def test_passthrough_env_only_set_vars():
    parent = {
        "CLAUDE_CODE_SSE_PORT": "9000",
        "ANTHROPIC_API_KEY": "sk-...",
        "UNRELATED": "x",
    }
    overlay = agent_vscode.passthrough_env("claude", parent)
    assert overlay["APPTAINERENV_CLAUDE_CODE_SSE_PORT"] == "9000"
    assert overlay["APPTAINERENV_ANTHROPIC_API_KEY"] == "sk-..."
    assert "APPTAINERENV_UNRELATED" not in overlay


def test_passthrough_env_skips_missing():
    overlay = agent_vscode.passthrough_env("codex", {})
    assert overlay == {}


def test_build_apptainer_binds_skips_missing(tmp_path, monkeypatch):
    # Pretend home is empty so all ~/ binds are missing; only /etc/* may match.
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    binds = agent_vscode.build_apptainer_binds("claude")
    # No ~/.claude exists in tmp_path, so it shouldn't appear; /etc/ssl/certs
    # exists on most Linux/mac dev hosts but not all — assert on absence rather
    # than presence.
    for bind in binds:
        assert not bind.startswith(str(tmp_path) + "/.claude")


def test_build_apptainer_binds_includes_existing(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    binds = agent_vscode.build_apptainer_binds("claude")
    assert any(b.startswith(str(fake_home / ".claude") + ":") for b in binds)


def test_build_apptainer_binds_pi_extension(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    ext_dir = fake_home / ".vscode-server" / "extensions" / "pi0.pi-vscode-1.2.3"
    ext_dir.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    binds = agent_vscode.build_apptainer_binds("pi", install_dir=tmp_path / "install")
    assert any(str(ext_dir) in b and b.endswith(":ro") for b in binds)


# --------------------------------------------------------------------------- #
# Top-level main() flow
# --------------------------------------------------------------------------- #

def test_main_no_wrap_execs_npm_bin(isolated_cache, install_dir, monkeypatch):
    monkeypatch.setenv("CODING_AGENTS_NO_WRAP", "1")
    npm_bin = install_dir / "node_modules" / ".bin" / "claude"
    npm_bin.parent.mkdir(parents=True)
    npm_bin.write_text("#!/bin/sh\necho npm\n")
    monkeypatch.setattr(sys, "argv", [str(install_dir / "bin" / "agent-vscode")])
    captured: dict = {}

    def fake_execv(path, argv):
        captured["path"] = path
        captured["argv"] = argv
        raise SystemExit(0)

    monkeypatch.setattr(os, "execv", fake_execv)
    with pytest.raises(SystemExit):
        agent_vscode.main(["--agent", "claude", "--", "--version"])
    assert captured["path"] == str(npm_bin)
    assert captured["argv"][1:] == ["--version"]


def test_main_slurm_set_execs_inner_wrapper(isolated_cache, install_dir, monkeypatch):
    monkeypatch.setenv("SLURM_JOB_ID", "42")
    monkeypatch.setattr(sys, "argv", [str(install_dir / "bin" / "agent-vscode")])
    captured: dict = {}

    def fake_execv(path, argv):
        captured["path"] = path
        captured["argv"] = argv
        raise SystemExit(0)

    monkeypatch.setattr(os, "execv", fake_execv)
    with pytest.raises(SystemExit):
        agent_vscode.main(["--agent", "pi", "--", "help"])
    assert captured["path"] == str(install_dir / "bin" / "agent-pi")
    assert captured["argv"][1:] == ["help"]


def test_main_no_cache_allocates_then_srun(isolated_cache, install_dir, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(install_dir / "bin" / "agent-vscode")])
    monkeypatch.setattr(agent_vscode, "squeue_job_alive", lambda jid: True)

    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        if cmd[0] == "salloc":
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="",
                stderr="salloc: Granted job allocation 99\n",
            )
        if cmd[0] == "srun":
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
        raise AssertionError(f"unexpected cmd {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_run)
    rc = agent_vscode.main(["--agent", "pi", "--", "--version"])
    assert rc == 0
    assert calls[0][0] == "salloc"
    assert calls[1][0] == "srun"
    assert "--jobid=99" in calls[1]
    cache = agent_vscode.read_cache(agent_vscode.cache_path())
    assert cache and cache["job_id"] == 99


def test_main_cache_hit_skips_salloc(isolated_cache, install_dir, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(install_dir / "bin" / "agent-vscode")])
    cache_p = agent_vscode.cache_path()
    cache_p.parent.mkdir(parents=True, exist_ok=True)
    state = agent_vscode.initial_state(agent_vscode.vscode_session_key())
    state["job_id"] = 555
    agent_vscode.write_cache(cache_p, state)
    monkeypatch.setattr(agent_vscode, "squeue_job_alive", lambda jid: True)

    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    rc = agent_vscode.main(["--agent", "pi"])
    assert rc == 0
    assert all(cmd[0] != "salloc" for cmd in calls)
    assert any(cmd[0] == "srun" and "--jobid=555" in cmd for cmd in calls)


def test_main_cache_dead_job_reallocates(isolated_cache, install_dir, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(install_dir / "bin" / "agent-vscode")])
    cache_p = agent_vscode.cache_path()
    cache_p.parent.mkdir(parents=True, exist_ok=True)
    state = agent_vscode.initial_state(agent_vscode.vscode_session_key())
    state["job_id"] = 100
    agent_vscode.write_cache(cache_p, state)

    monkeypatch.setattr(agent_vscode, "squeue_job_alive", lambda jid: False)

    def fake_run(cmd, *args, **kwargs):
        if cmd[0] == "salloc":
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="",
                stderr="salloc: Granted job allocation 200\n",
            )
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    rc = agent_vscode.main(["--agent", "pi"])
    assert rc == 0
    cache = agent_vscode.read_cache(cache_p)
    assert cache and cache["job_id"] == 200


def test_main_first_salloc_failure_writes_failure_state(isolated_cache, install_dir, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(install_dir / "bin" / "agent-vscode")])

    def fake_run(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(
            args=cmd, returncode=1, stdout="",
            stderr="salloc: error: queue full\n",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    rc = agent_vscode.main(["--agent", "pi"])
    assert rc == agent_vscode.EXIT_SALLOC_FAILED
    cache = agent_vscode.read_cache(agent_vscode.cache_path())
    assert cache and cache["failure_count"] == 1
    assert cache["last_failure_at"] is not None
    assert cache["job_id"] is None


def test_main_persistent_failure_refuses(isolated_cache, install_dir, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(install_dir / "bin" / "agent-vscode")])
    cache_p = agent_vscode.cache_path()
    cache_p.parent.mkdir(parents=True, exist_ok=True)
    state = agent_vscode.initial_state(agent_vscode.vscode_session_key())
    state["failure_count"] = 2
    state["last_failure_at"] = _stamp_seconds_ago(60)
    agent_vscode.write_cache(cache_p, state)

    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    rc = agent_vscode.main(["--agent", "pi"])
    assert rc == agent_vscode.EXIT_REFUSE_PERSISTENT_FAILURE
    # Should not call salloc or srun
    assert calls == []


def test_main_cooldown_rate_limit(isolated_cache, install_dir, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(install_dir / "bin" / "agent-vscode")])
    cache_p = agent_vscode.cache_path()
    cache_p.parent.mkdir(parents=True, exist_ok=True)
    state = agent_vscode.initial_state(agent_vscode.vscode_session_key())
    state["failure_count"] = 1
    state["last_failure_at"] = _stamp_seconds_ago(5)  # within 30s cooldown
    agent_vscode.write_cache(cache_p, state)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("should not run"))
    rc = agent_vscode.main(["--agent", "pi"])
    assert rc == agent_vscode.EXIT_REFUSE_PERSISTENT_FAILURE


def test_main_retry_after_cooldown(isolated_cache, install_dir, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(install_dir / "bin" / "agent-vscode")])
    cache_p = agent_vscode.cache_path()
    cache_p.parent.mkdir(parents=True, exist_ok=True)
    state = agent_vscode.initial_state(agent_vscode.vscode_session_key())
    state["failure_count"] = 1
    state["last_failure_at"] = _stamp_seconds_ago(60)  # past cooldown
    agent_vscode.write_cache(cache_p, state)
    monkeypatch.setattr(agent_vscode, "squeue_job_alive", lambda jid: True)

    def fake_run(cmd, *args, **kwargs):
        if cmd[0] == "salloc":
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="",
                stderr="salloc: Granted job allocation 333\n",
            )
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    rc = agent_vscode.main(["--agent", "pi"])
    assert rc == 0
    cache = agent_vscode.read_cache(cache_p)
    assert cache and cache["job_id"] == 333
    assert cache["failure_count"] == 0


def test_main_vscode_session_change_invalidates_cache(isolated_cache, install_dir, monkeypatch):
    """Cached vscode_session_pid != current key → drop cache, allocate fresh."""
    monkeypatch.setattr(sys, "argv", [str(install_dir / "bin" / "agent-vscode")])
    cache_p = agent_vscode.cache_path()
    cache_p.parent.mkdir(parents=True, exist_ok=True)
    state = agent_vscode.initial_state(vscode_session="ppid:12345")
    state["job_id"] = 111
    state["failure_count"] = 2  # poisoned by a since-restarted VSCode
    state["last_failure_at"] = _stamp_seconds_ago(10)
    agent_vscode.write_cache(cache_p, state)

    monkeypatch.setattr(agent_vscode, "squeue_job_alive", lambda jid: True)
    monkeypatch.setattr(agent_vscode, "vscode_session_key", lambda: "ppid:67890")

    def fake_run(cmd, *args, **kwargs):
        if cmd[0] == "salloc":
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="",
                stderr="salloc: Granted job allocation 999\n",
            )
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    rc = agent_vscode.main(["--agent", "pi"])
    assert rc == 0
    cache = agent_vscode.read_cache(cache_p)
    assert cache and cache["job_id"] == 999
    assert cache["vscode_session_pid"] == "ppid:67890"
    assert cache["failure_count"] == 0


def test_main_passes_apptainer_env_via_srun(isolated_cache, install_dir, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(install_dir / "bin" / "agent-vscode")])
    monkeypatch.setenv("CLAUDE_CODE_SSE_PORT", "37386")
    monkeypatch.setattr(agent_vscode, "squeue_job_alive", lambda jid: True)

    captured_env: dict = {}

    def fake_run(cmd, *args, **kwargs):
        if cmd[0] == "salloc":
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="",
                stderr="salloc: Granted job allocation 42\n",
            )
        if cmd[0] == "srun":
            captured_env.update(kwargs.get("env") or {})
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    rc = agent_vscode.main(["--agent", "claude"])
    assert rc == 0
    assert captured_env.get("APPTAINERENV_CLAUDE_CODE_SSE_PORT") == "37386"
    assert captured_env.get("APPTAINERENV_CODING_AGENTS_VSCODE_LAUNCHED") == "1"


def test_main_isatty_false_no_pty(isolated_cache, install_dir, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(install_dir / "bin" / "agent-vscode")])
    monkeypatch.setattr(agent_vscode, "squeue_job_alive", lambda jid: True)
    monkeypatch.setattr(os, "isatty", lambda fd: False)

    captured = []

    def fake_run(cmd, *args, **kwargs):
        captured.append(list(cmd))
        if cmd[0] == "salloc":
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="",
                stderr="salloc: Granted job allocation 1\n",
            )
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    agent_vscode.main(["--agent", "codex"])
    srun_cmd = next(c for c in captured if c[0] == "srun")
    assert "--pty" not in srun_cmd


def test_main_isatty_true_uses_pty(isolated_cache, install_dir, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(install_dir / "bin" / "agent-vscode")])
    monkeypatch.setattr(agent_vscode, "squeue_job_alive", lambda jid: True)
    monkeypatch.setattr(os, "isatty", lambda fd: True)

    captured = []

    def fake_run(cmd, *args, **kwargs):
        captured.append(list(cmd))
        if cmd[0] == "salloc":
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="",
                stderr="salloc: Granted job allocation 1\n",
            )
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    agent_vscode.main(["--agent", "pi"])
    srun_cmd = next(c for c in captured if c[0] == "srun")
    assert "--pty" in srun_cmd


def test_main_age_out_resets_old_failure(isolated_cache, install_dir, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(install_dir / "bin" / "agent-vscode")])
    cache_p = agent_vscode.cache_path()
    cache_p.parent.mkdir(parents=True, exist_ok=True)
    state = agent_vscode.initial_state(agent_vscode.vscode_session_key())
    state["failure_count"] = 5
    state["last_failure_at"] = _stamp_seconds_ago(5 * 3600)  # > 4h
    agent_vscode.write_cache(cache_p, state)
    monkeypatch.setattr(agent_vscode, "squeue_job_alive", lambda jid: True)

    def fake_run(cmd, *args, **kwargs):
        if cmd[0] == "salloc":
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="",
                stderr="salloc: Granted job allocation 444\n",
            )
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    rc = agent_vscode.main(["--agent", "pi"])
    assert rc == 0
    cache = agent_vscode.read_cache(cache_p)
    assert cache and cache["job_id"] == 444
    assert cache["failure_count"] == 0


# --------------------------------------------------------------------------- #
# Concurrency / flock
# --------------------------------------------------------------------------- #

def test_concurrent_invocations_serialize(isolated_cache, install_dir, monkeypatch, tmp_path):
    """Two agent_vscode invocations under the same flock share one allocation.

    We exercise this by running ``run_with_lock`` twice and counting the
    salloc calls — the second run should see the cache populated by the first
    and reuse the job id. The flock'd code path is the only one that writes
    the cache, so this also checks the serialisation invariant.
    """
    monkeypatch.setattr(sys, "argv", [str(install_dir / "bin" / "agent-vscode")])
    monkeypatch.setattr(agent_vscode, "squeue_job_alive", lambda jid: True)

    salloc_calls = 0

    def fake_run(cmd, *args, **kwargs):
        nonlocal salloc_calls
        if cmd[0] == "salloc":
            salloc_calls += 1
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="",
                stderr=f"salloc: Granted job allocation {1000 + salloc_calls}\n",
            )
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    rc1 = agent_vscode.run_with_lock("pi", [], install_dir, vscode_session=4242)
    rc2 = agent_vscode.run_with_lock("pi", [], install_dir, vscode_session=4242)
    assert rc1 == 0 and rc2 == 0
    assert salloc_calls == 1  # second call reused the cached job
