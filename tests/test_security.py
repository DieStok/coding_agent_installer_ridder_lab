"""Tests for security fixes."""
import os
import stat
import tempfile
from pathlib import Path

import pytest


def test_secure_write_text_creates_file_with_0600():
    from coding_agents.utils import secure_write_text

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.json"
        secure_write_text(path, '{"test": true}')

        assert path.exists()
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600
        assert path.read_text() == '{"test": true}'


def test_secure_write_text_creates_parent_dirs():
    from coding_agents.utils import secure_write_text

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "subdir" / "deep" / "test.json"
        secure_write_text(path, "content")
        assert path.exists()


def test_secure_write_text_overwrites():
    from coding_agents.utils import secure_write_text

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.json"
        secure_write_text(path, "first")
        secure_write_text(path, "second")
        assert path.read_text() == "second"


def test_path_validation_regex():
    from coding_agents.utils import _SAFE_PATH_RE

    # Safe paths
    assert _SAFE_PATH_RE.match("/home/user/coding_agents")
    assert _SAFE_PATH_RE.match("/hpc/compgen/users/dstoker/coding_agents")
    assert _SAFE_PATH_RE.match("~/coding_agents")

    # Unsafe paths
    assert not _SAFE_PATH_RE.match('/tmp/"; rm -rf /')
    assert not _SAFE_PATH_RE.match("/tmp/$HOME")
    assert not _SAFE_PATH_RE.match("/tmp/`whoami`")
    assert not _SAFE_PATH_RE.match("/path with spaces")


def test_inject_shell_block_rejects_unsafe_path():
    from coding_agents.utils import inject_shell_block

    with pytest.raises(ValueError, match="unsafe characters"):
        inject_shell_block(Path('/tmp/"; evil'))


def test_run_raises_on_check_true_failure():
    import subprocess
    from coding_agents.utils import run

    with pytest.raises(subprocess.CalledProcessError):
        run(["false"], check=True)


def test_run_returns_result_on_check_false():
    from coding_agents.utils import run

    result = run(["false"], check=False)
    assert result.returncode != 0


def test_build_hook_entries_shared():
    """Verify the shared build_hook_entries function works."""
    from coding_agents.config import build_hook_entries

    entries = build_hook_entries(Path("/test/install"), ["agents_md_check", "lint_runner"])
    assert len(entries) == 2
    assert all("hooks" in e for e in entries)
    assert "on_start_agents_md_check.py" in entries[0]["hooks"][0]["command"]
    assert entries[0]["hooks"][0]["timeout"] == 10  # on_start_ = 10s
    assert entries[1]["hooks"][0]["timeout"] == 30  # on_stop_ = 30s


def test_load_config_uses_deepcopy():
    """Verify that mutating returned config doesn't corrupt DEFAULT_CONFIG."""
    from coding_agents.config import DEFAULT_CONFIG, load_config
    from unittest.mock import patch

    original_skills = list(DEFAULT_CONFIG["skills"])

    with patch("coding_agents.config.CONFIG_PATH", Path("/nonexistent")):
        config = load_config()
        config["skills"].append("new-skill")

        # DEFAULT_CONFIG should be unchanged
        assert DEFAULT_CONFIG["skills"] == original_skills
