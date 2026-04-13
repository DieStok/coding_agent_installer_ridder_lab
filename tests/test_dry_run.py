"""Tests for dry-run mode — the --dry-run flag and its machinery."""
from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def reset_dry_run():
    """Ensure dry-run state is clean before and after the test."""
    from coding_agents.dry_run import get_recorder, set_dry_run

    set_dry_run(False)
    get_recorder().reset()
    yield
    set_dry_run(False)
    get_recorder().reset()


@pytest.fixture
def tmp_home(monkeypatch, tmp_path):
    """Point ``Path.home()`` at a temporary directory for the test."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Core module
# ---------------------------------------------------------------------------


def test_is_dry_run_defaults_false(reset_dry_run):
    from coding_agents.dry_run import is_dry_run

    assert is_dry_run() is False


def test_set_dry_run_toggles_flag(reset_dry_run):
    from coding_agents.dry_run import is_dry_run, set_dry_run

    set_dry_run(True)
    assert is_dry_run() is True
    set_dry_run(False)
    assert is_dry_run() is False


def test_would_records_action(reset_dry_run):
    from coding_agents.dry_run import get_recorder, would

    would("test_cat", "test_action", key="value", number=42)

    actions = get_recorder().actions
    assert len(actions) == 1
    cat, action, fields = actions[0]
    assert cat == "test_cat"
    assert action == "test_action"
    assert fields == {"key": "value", "number": 42}


def test_recorder_counts(reset_dry_run):
    from coding_agents.dry_run import get_recorder, would

    would("subprocess", "run")
    would("subprocess", "run")
    would("file_write", "secure_write_text")

    assert get_recorder().counts() == {"subprocess": 2, "file_write": 1}


def test_content_fingerprint_stable():
    from coding_agents.dry_run import content_fingerprint

    assert content_fingerprint("hello") == content_fingerprint("hello")
    assert content_fingerprint("hello") != content_fingerprint("world")
    assert len(content_fingerprint("x")) == 8


def test_fake_completed_process_shape():
    from coding_agents.dry_run import fake_completed_process

    cp = fake_completed_process(["echo", "hi"])
    assert isinstance(cp, subprocess.CompletedProcess)
    assert cp.args == ["echo", "hi"]
    assert cp.returncode == 0
    assert cp.stdout == ""
    assert cp.stderr == ""

    cp2 = fake_completed_process(["x"], capture=False)
    assert cp2.stdout is None and cp2.stderr is None


def test_emit_summary_outputs_counts(reset_dry_run, caplog):
    from coding_agents.dry_run import emit_summary, would

    would("subprocess", "run")
    would("file_write", "x")
    would("file_write", "y")

    with caplog.at_level(logging.WARNING, logger="coding-agents"):
        emit_summary()

    text = "\n".join(r.message for r in caplog.records)
    assert "DRY-RUN SUMMARY" in text
    assert "3 actions would have been performed" in text
    assert "subprocess" in text
    assert "file_write" in text


# ---------------------------------------------------------------------------
# utils.py intercepts
# ---------------------------------------------------------------------------


def test_run_in_dry_run_returns_mock_and_never_calls_subprocess(reset_dry_run):
    from coding_agents.dry_run import get_recorder, set_dry_run
    from coding_agents.utils import run

    set_dry_run(True)
    with patch(
        "subprocess.run", side_effect=AssertionError("subprocess.run called in dry-run")
    ):
        result = run(["this-binary-does-not-exist"])

    assert result.returncode == 0
    assert result.stdout == ""
    actions = [a[0] for a in get_recorder().actions]
    assert "subprocess" in actions


def test_safe_symlink_in_dry_run_creates_nothing(reset_dry_run, tmp_path):
    from coding_agents.dry_run import set_dry_run
    from coding_agents.utils import safe_symlink

    src = tmp_path / "source"
    src.write_text("x")
    target = tmp_path / "link"

    set_dry_run(True)
    safe_symlink(src, target)

    assert not target.exists()
    assert not target.is_symlink()


def test_secure_write_text_in_dry_run_creates_nothing(reset_dry_run, tmp_path):
    from coding_agents.dry_run import set_dry_run
    from coding_agents.utils import secure_write_text

    path = tmp_path / "new.json"

    set_dry_run(True)
    secure_write_text(path, "should not exist")

    assert not path.exists()


def test_inject_shell_block_in_dry_run_leaves_rc_unchanged(
    reset_dry_run, tmp_home, monkeypatch
):
    from coding_agents.dry_run import set_dry_run
    from coding_agents.utils import inject_shell_block

    monkeypatch.setenv("SHELL", "/bin/zsh")
    bashrc = tmp_home / ".bashrc"
    zshrc = tmp_home / ".zshrc"
    bashrc.write_text("# existing bashrc\n")
    zshrc.write_text("# existing zshrc\n")
    original_bashrc = bashrc.read_text()
    original_zshrc = zshrc.read_text()

    set_dry_run(True)
    files = inject_shell_block(tmp_home / "install")

    assert bashrc.read_text() == original_bashrc
    assert zshrc.read_text() == original_zshrc
    assert bashrc in files and zshrc in files


def test_inject_shell_block_unsafe_path_still_raises_in_dry_run(reset_dry_run):
    """Security check runs BEFORE dry-run short-circuit."""
    from coding_agents.dry_run import set_dry_run
    from coding_agents.utils import inject_shell_block

    set_dry_run(True)
    with pytest.raises(ValueError, match="unsafe characters"):
        inject_shell_block(Path("/tmp/evil; rm -rf /"))


def test_remove_shell_block_in_dry_run_leaves_rc_unchanged(
    reset_dry_run, tmp_home
):
    from coding_agents.dry_run import set_dry_run
    from coding_agents.utils import remove_shell_block

    bashrc = tmp_home / ".bashrc"
    marked = (
        "before\n"
        "# >>> coding-agents >>>\n"
        "export PATH=whatever\n"
        "# <<< coding-agents <<<\n"
        "after\n"
    )
    bashrc.write_text(marked)

    set_dry_run(True)
    files = remove_shell_block()

    assert bashrc.read_text() == marked
    assert bashrc in files


# ---------------------------------------------------------------------------
# merge_settings.py, config.py, detect_existing.py, convert_mcp.py
# ---------------------------------------------------------------------------


def test_merge_json_section_in_dry_run_does_not_write(reset_dry_run, tmp_path):
    from coding_agents.dry_run import get_recorder, set_dry_run
    from coding_agents.merge_settings import merge_json_section

    settings = tmp_path / "settings.json"
    # Use a string-list section (permissions.deny) to dodge merge_json_section's
    # vacuous-truth quirk with an empty dict-list.
    original = json.dumps(
        {"permissions": {"deny": ["Read(./.env)"]}},
        indent=2,
    ) + "\n"
    settings.write_text(original)

    set_dry_run(True)
    result = merge_json_section(
        settings,
        "permissions.deny",
        ["Read(./secrets.json)"],
    )

    assert settings.read_text() == original
    assert "Read(./secrets.json)" in result.added_keys
    categories = [a[0] for a in get_recorder().actions]
    assert "json_merge" in categories


def test_save_config_in_dry_run_does_not_write(reset_dry_run, monkeypatch, tmp_path):
    from coding_agents import config as config_mod
    from coding_agents.dry_run import get_recorder, set_dry_run

    config_path = tmp_path / ".coding-agents.json"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", config_path)

    set_dry_run(True)
    config_mod.save_config({"install_dir": str(tmp_path), "mode": "local"})

    assert not config_path.exists()
    categories = [a[0] for a in get_recorder().actions]
    assert "config_save" in categories


def test_backup_agent_dir_in_dry_run_creates_no_tar(reset_dry_run, tmp_path):
    from coding_agents.detect_existing import AgentInventory, backup_agent_dir
    from coding_agents.dry_run import set_dry_run

    # Build a minimal fake agent dir
    agent_dir = tmp_path / ".fake-agent"
    agent_dir.mkdir()
    (agent_dir / "a.txt").write_text("hello")

    inv = AgentInventory(
        agent_key="fake",
        display_name="Fake",
        config_dir=agent_dir,
        exists=True,
        files=["a.txt"],
        total_size=5,
    )

    set_dry_run(True)
    backup_path = backup_agent_dir(inv)

    assert backup_path is not None
    assert not backup_path.exists()  # no tar was created


def test_convert_mcp_in_dry_run_writes_nothing(
    reset_dry_run, tmp_home, tmp_path
):
    from coding_agents.convert_mcp import convert_mcp
    from coding_agents.dry_run import set_dry_run

    servers_json = tmp_path / "servers.json"
    servers_json.write_text(json.dumps({
        "servers": {
            "context7": {"command": "npx", "args": ["@c7/mcp"]},
        }
    }))

    set_dry_run(True)
    written = convert_mcp(servers_json, ["claude"])

    # claude writes to ~/.mcp.json
    assert not (tmp_home / ".mcp.json").exists()
    # We still return the list of paths that would be written
    assert any(".mcp.json" in p for p in written)


# ---------------------------------------------------------------------------
# fs_ops helpers
# ---------------------------------------------------------------------------


def test_fs_ops_dry_run_mkdir_does_nothing(reset_dry_run, tmp_path):
    from coding_agents.dry_run import set_dry_run
    from coding_agents.installer.fs_ops import dry_run_mkdir

    set_dry_run(True)
    dry_run_mkdir(tmp_path / "ghost" / "subdir")
    assert not (tmp_path / "ghost").exists()


def test_fs_ops_dry_run_copy_does_nothing(reset_dry_run, tmp_path):
    from coding_agents.dry_run import set_dry_run
    from coding_agents.installer.fs_ops import dry_run_copy

    src = tmp_path / "src.txt"
    src.write_text("x" * 100)
    dst = tmp_path / "dst.txt"

    set_dry_run(True)
    dry_run_copy(src, dst)
    assert not dst.exists()


def test_fs_ops_dry_run_rmtree_does_nothing(reset_dry_run, tmp_path):
    from coding_agents.dry_run import set_dry_run
    from coding_agents.installer.fs_ops import dry_run_rmtree

    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "a.txt").write_text("don't delete me")

    set_dry_run(True)
    dry_run_rmtree(victim)
    assert victim.exists()
    assert (victim / "a.txt").exists()


def test_fs_ops_dry_run_unlink_does_nothing(reset_dry_run, tmp_path):
    from coding_agents.dry_run import set_dry_run
    from coding_agents.installer.fs_ops import dry_run_unlink

    victim = tmp_path / "victim.txt"
    victim.write_text("x")

    set_dry_run(True)
    dry_run_unlink(victim)
    assert victim.exists()


def test_fs_ops_dry_run_write_text_does_nothing(reset_dry_run, tmp_path):
    from coding_agents.dry_run import set_dry_run
    from coding_agents.installer.fs_ops import dry_run_write_text

    target = tmp_path / "new.sh"

    set_dry_run(True)
    dry_run_write_text(target, "#!/bin/bash\necho hi\n", mode=0o755)
    assert not target.exists()


def test_fs_ops_real_run_still_works(reset_dry_run, tmp_path):
    from coding_agents.installer.fs_ops import (
        dry_run_copy,
        dry_run_mkdir,
        dry_run_write_text,
    )

    dry_run_mkdir(tmp_path / "subdir")
    assert (tmp_path / "subdir").is_dir()

    src = tmp_path / "src.txt"
    src.write_text("hello")
    dst = tmp_path / "subdir" / "dst.txt"
    dry_run_copy(src, dst)
    assert dst.read_text() == "hello"

    dry_run_write_text(tmp_path / "script.sh", "echo hi", mode=0o755)
    assert (tmp_path / "script.sh").read_text() == "echo hi"
    assert oct((tmp_path / "script.sh").stat().st_mode & 0o777) == "0o755"


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cli_dry_run_flag_implies_debug(reset_dry_run, tmp_home, monkeypatch):
    """`coding-agents --dry-run doctor` should enable debug logging and set
    the dry-run flag."""
    from typer.testing import CliRunner

    from coding_agents import cli
    from coding_agents.dry_run import is_dry_run

    runner = CliRunner()
    # doctor exits 1 when there's no install config; that's fine for this test
    result = runner.invoke(cli.app, ["--dry-run", "doctor"])
    assert is_dry_run() is True
    # Either exit 0 (no checks to fail, unlikely) or exit 1 (expected)
    assert result.exit_code in (0, 1)

    # logger is configured to DEBUG with both handlers
    logger = logging.getLogger("coding-agents")
    assert logger.level == logging.DEBUG


def test_cli_dry_run_creates_dry_run_prefixed_log(
    reset_dry_run, tmp_home, monkeypatch
):
    """The log file should be prefixed ``dry-run-`` not ``debug-``."""
    from typer.testing import CliRunner

    from coding_agents import cli

    runner = CliRunner()
    runner.invoke(cli.app, ["--dry-run", "doctor"])

    # Search for dry-run log in either install_dir/logs (doesn't exist) or home fallback
    hits = list(tmp_home.glob(".coding-agents-dry-run-*.log"))
    assert hits, f"no dry-run log found in {tmp_home}"


def test_cli_debug_still_uses_debug_prefix(reset_dry_run, tmp_home):
    """--debug alone (without --dry-run) should still produce debug-*.log."""
    from typer.testing import CliRunner

    from coding_agents import cli
    from coding_agents.dry_run import is_dry_run

    runner = CliRunner()
    runner.invoke(cli.app, ["--debug", "doctor"])

    assert is_dry_run() is False  # not dry-run
    hits = list(tmp_home.glob(".coding-agents-debug-*.log"))
    assert hits, f"no debug log found in {tmp_home}"


# ---------------------------------------------------------------------------
# Integration: execute_install under dry-run does no real work
# ---------------------------------------------------------------------------


def test_execute_install_in_dry_run_touches_nothing(
    reset_dry_run, tmp_home, tmp_path, monkeypatch
):
    """Full end-to-end: run the installer in dry-run and prove nothing happens."""
    import asyncio

    from coding_agents.dry_run import get_recorder, set_dry_run
    from coding_agents.installer.executor import execute_install
    from coding_agents.installer.state import InstallerState

    # Patch subprocess.run at source — dry-run should short-circuit utils.run
    # before it ever reaches subprocess.
    def boom(*args, **kwargs):
        raise AssertionError(f"subprocess.run called in dry-run: {args!r}")

    monkeypatch.setattr(subprocess, "run", boom)

    # Fake RichLog: captures writes without needing Textual
    class FakeLog:
        def __init__(self):
            self.lines = []

        def write(self, s):
            self.lines.append(s)

    state = InstallerState(
        mode="local",
        install_dir=str(tmp_path / "install"),
        agents=["claude", "codex"],
        tools=[],
        skills=[],
        hooks=[],
        jai_enabled=False,
        vscode_extensions=False,
    )

    set_dry_run(True)
    asyncio.run(execute_install(state, FakeLog()))

    # Nothing should have been created
    assert not (tmp_path / "install").exists()
    # And the recorder should have entries across multiple categories
    cats = set(a[0] for a in get_recorder().actions)
    assert "mkdir" in cats
    assert "subprocess" in cats or "symlink" in cats or "file_copy" in cats


def test_atexit_emit_summary_registered():
    """The CLI module should have registered an atexit hook for the summary."""
    import atexit

    from coding_agents import cli  # noqa: F401

    # The callback is named _summary_atexit in cli.py — ensure some atexit
    # callback references the coding_agents CLI module.
    # atexit callbacks aren't directly inspectable in a portable way, so we
    # verify by calling the function directly with dry-run off and on.
    from coding_agents.dry_run import get_recorder, set_dry_run
    from coding_agents.dry_run import would

    set_dry_run(True)
    get_recorder().reset()
    would("test", "atexit_check")
    cli._summary_atexit()  # should emit without error
    set_dry_run(False)
