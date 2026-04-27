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


def test_secure_write_text_atomic_no_zero_byte_on_write_failure():
    """Synthesis §3.3 / Sprint 1 Task 1.2: a Ctrl-C / scancel / OOM
    mid-write must not zero the target file. The previous implementation
    used O_TRUNC + os.write, so any failure mid-write left a 0-byte file
    that downstream JSONDecodeError handlers silently swallowed.

    Atomic safe-replace (mkstemp → fsync → os.replace) means the target
    is either fully written or untouched — never half-written.
    """
    import os as _os
    from unittest.mock import patch

    from coding_agents.utils import secure_write_text

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "settings.json"
        path.write_text('{"original": true}\n')
        original_mtime = path.stat().st_mtime

        # Simulate a kernel-level write failure mid-flight.
        real_write = _os.write
        call_count = [0]

        def failing_write(fd, data):
            call_count[0] += 1
            # Allow the first internal mkstemp-bookkeeping write through
            # if any, but fail the payload write.
            if call_count[0] >= 1 and len(data) > 5:
                raise OSError(28, "No space left on device (simulated)")
            return real_write(fd, data)

        with patch("coding_agents.utils.os.write", side_effect=failing_write):
            with pytest.raises(OSError):
                secure_write_text(path, '{"new_content": "would be written"}\n')

        # Target still has its original content — never zero bytes.
        assert path.read_text() == '{"original": true}\n', (
            "Atomic write failed: target was modified despite OSError. "
            "secure_write_text should leave the original untouched on failure."
        )
        # Mtime unchanged (the rename never happened).
        assert path.stat().st_mtime == original_mtime

        # No leftover .*.tmp files in the parent.
        leftover = list(Path(tmpdir).glob(".settings.json.*.tmp"))
        assert leftover == [], (
            f"Temp files leaked on write failure: {leftover}"
        )


def test_secure_write_text_atomic_target_visible_only_when_complete():
    """A reader that polls the target during secure_write_text must see
    either the old content or the new content — never something in
    between (no partial JSON, no zero bytes).

    Verified indirectly: between mkstemp and os.replace, the target
    still has its old content (proved by checking just before the
    final os.replace would fire).
    """
    import os as _os
    from unittest.mock import patch

    from coding_agents.utils import secure_write_text

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "settings.json"
        path.write_text('{"v": 1}\n')

        observed_during_write = []
        real_replace = _os.replace

        def observing_replace(src, dst):
            # At this point the temp file holds the new content but the
            # target still holds the old. Reader sees old.
            observed_during_write.append(Path(dst).read_text())
            return real_replace(src, dst)

        with patch("coding_agents.utils.os.replace", side_effect=observing_replace):
            secure_write_text(path, '{"v": 2}\n')

        # Just before os.replace, the target still showed the OLD content
        # (atomic visibility transition).
        assert observed_during_write == ['{"v": 1}\n']
        # And after, the target has the new content.
        assert path.read_text() == '{"v": 2}\n'


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
