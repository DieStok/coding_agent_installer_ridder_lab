"""Tests for the per-extension wrapper-stub installer module."""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from coding_agents.installer.wrapper_vscode import (
    EXTENSION_STUBS,
    emit_agent_vscode_helper,
    emit_extension_stubs,
    emit_path_shim,
)


@pytest.fixture
def install_dir(tmp_path):
    return tmp_path / "install"


def test_emit_pi_stub_renders(install_dir):
    written = emit_extension_stubs(install_dir, ["pi"])
    assert len(written) == 1
    stub = written[0]
    content = stub.read_text()
    assert "exec" in content
    assert "--agent pi" in content
    assert content.startswith("#!/usr/bin/env bash")


def test_stub_has_executable_bit(install_dir):
    written = emit_extension_stubs(install_dir, ["pi"])
    mode = written[0].stat().st_mode
    assert mode & stat.S_IXUSR
    assert mode & stat.S_IXGRP
    assert mode & stat.S_IXOTH


def test_emit_all_four_stubs(install_dir):
    written = emit_extension_stubs(install_dir, ["pi", "claude", "codex", "opencode"])
    names = sorted(p.name for p in written)
    assert names == [
        "agent-claude-vscode",
        "agent-codex-vscode",
        "agent-opencode-vscode",
        "agent-pi-vscode",
    ]


def test_emit_default_to_all(install_dir):
    written = emit_extension_stubs(install_dir)
    assert len(written) == 4


def test_emit_unknown_agent_skipped(install_dir, caplog):
    written = emit_extension_stubs(install_dir, ["bogus"])
    assert written == []


def test_helper_copied_with_shebang_intact(install_dir):
    helper = emit_agent_vscode_helper(install_dir)
    assert helper == install_dir / "bin" / "agent-vscode"
    assert helper.read_text().startswith("#!/usr/bin/env python3")
    assert helper.stat().st_mode & stat.S_IXUSR


def test_helper_overwritten_on_reinstall(install_dir):
    emit_agent_vscode_helper(install_dir)
    # Mutate to verify a re-emit overwrites with fresh content.
    target = install_dir / "bin" / "agent-vscode"
    target.write_text("#!/usr/bin/env python3\n# old stub\n")
    emit_agent_vscode_helper(install_dir)
    assert "old stub" not in target.read_text()
    assert target.read_text().startswith("#!/usr/bin/env python3")


def test_path_shim_symlink_targets_agent_opencode(install_dir):
    shim = emit_path_shim(install_dir)
    assert shim == install_dir / "bin" / "path-shim" / "opencode"
    assert shim.is_symlink()
    # Resolves relative to its parent dir
    assert os.readlink(shim) == "../agent-opencode-vscode"


def test_path_shim_idempotent(install_dir):
    first = emit_path_shim(install_dir)
    second = emit_path_shim(install_dir)
    assert first == second
    assert first.is_symlink()


def test_extension_stubs_dict_has_four_entries():
    assert set(EXTENSION_STUBS.keys()) == {"pi", "claude", "codex", "opencode"}
