"""Tests for utils.py — symlinks, shell integration, platform detection."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def test_safe_symlink_creates_link():
    from coding_agents.utils import safe_symlink

    with tempfile.TemporaryDirectory() as tmpdir:
        source = Path(tmpdir) / "source.txt"
        source.write_text("hello")
        target = Path(tmpdir) / "subdir" / "link.txt"

        safe_symlink(source, target)
        assert target.is_symlink()
        assert target.read_text() == "hello"


def test_safe_symlink_replaces_existing_symlink():
    from coding_agents.utils import safe_symlink

    with tempfile.TemporaryDirectory() as tmpdir:
        source1 = Path(tmpdir) / "source1.txt"
        source1.write_text("first")
        source2 = Path(tmpdir) / "source2.txt"
        source2.write_text("second")
        target = Path(tmpdir) / "link.txt"

        safe_symlink(source1, target)
        assert target.read_text() == "first"

        safe_symlink(source2, target)
        assert target.read_text() == "second"


def test_safe_symlink_backs_up_regular_file():
    from coding_agents.utils import safe_symlink

    with tempfile.TemporaryDirectory() as tmpdir:
        source = Path(tmpdir) / "source.txt"
        source.write_text("new")
        target = Path(tmpdir) / "existing.txt"
        target.write_text("old")

        safe_symlink(source, target)
        assert target.is_symlink()
        assert target.read_text() == "new"
        backup = target.with_suffix(".txt.bak")
        assert backup.exists()
        assert backup.read_text() == "old"


def test_shell_markers():
    from coding_agents.utils import SHELL_MARKERS

    assert "coding-agents" in SHELL_MARKERS[0]
    assert "coding-agents" in SHELL_MARKERS[1]


def test_inject_and_remove_shell_block():
    from coding_agents.utils import _write_guarded_block, SHELL_MARKERS

    with tempfile.NamedTemporaryFile(suffix=".bashrc", delete=False, mode="w") as f:
        f.write("# existing content\n")
        rc = Path(f.name)

    try:
        block = f"{SHELL_MARKERS[0]}\nexport TEST=1\n{SHELL_MARKERS[1]}"
        _write_guarded_block(rc, block)

        content = rc.read_text()
        assert "export TEST=1" in content
        assert SHELL_MARKERS[0] in content

        # Re-run should replace, not duplicate
        _write_guarded_block(rc, block)
        assert content.count(SHELL_MARKERS[0]) == 1 or rc.read_text().count(SHELL_MARKERS[0]) == 1
    finally:
        rc.unlink(missing_ok=True)


def test_detect_platform():
    from coding_agents.utils import detect_platform

    info = detect_platform()
    assert "os" in info
    assert "arch" in info
    assert isinstance(info["git"], bool)
