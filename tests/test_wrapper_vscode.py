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


def test_stub_probes_for_python_3_7(install_dir):
    """The stub must search python3.7..3.13 explicitly so it doesn't fall
    through to a 3.6 ``python3`` (which chokes on ``from __future__ import
    annotations`` before our code runs)."""
    written = emit_extension_stubs(install_dir, ["claude"])
    content = written[0].read_text()
    for cand in ("python3.7", "python3.8", "python3.9", "python3.10",
                 "python3.11", "python3.12", "python3.13"):
        assert cand in content, f"stub must probe for {cand}"
    assert "version_info >= (3, 7)" in content
    assert "exit 13" in content


def test_stub_refuses_when_no_python_found(install_dir, tmp_path):
    """If the stub runs with a PATH that has no Python ≥ 3.7, it should
    exit 13 and emit a self-diagnosing error rather than fall through."""
    import shutil
    import subprocess

    emit_extension_stubs(install_dir, ["claude"])
    stub = install_dir / "bin" / "agent-claude-vscode"

    # Build a PATH with bash present (so the shebang resolves) but no
    # python interpreter. Symlink bash into a fresh dir.
    bin_only = tmp_path / "bash-only"
    bin_only.mkdir()
    bash = shutil.which("bash")
    assert bash, "test host has no bash"
    (bin_only / "bash").symlink_to(bash)

    result = subprocess.run(
        [str(stub)],
        capture_output=True,
        text=True,
        env={"PATH": str(bin_only)},
        check=False,
    )
    assert result.returncode == 13, (result.returncode, result.stderr)
    assert "no python >= 3.7" in result.stderr


def test_stubs_resolve_symlinks_via_readlink(install_dir):
    """Regression: bin/path-shim/opencode symlink → ../agent-opencode-vscode
    needs the stub to resolve $0 through the symlink so it finds agent-vscode
    in bin/, not in path-shim/. Checking that all four stubs use readlink."""
    written = emit_extension_stubs(install_dir)
    for stub in written:
        content = stub.read_text()
        assert "readlink -f" in content, (
            f"{stub.name} must resolve symlinks via readlink -f so the "
            f"OpenCode path-shim invocation finds agent-vscode in bin/"
        )


def test_opencode_path_shim_invocation_finds_agent_vscode(install_dir, tmp_path):
    """End-to-end: write the OpenCode stub + path-shim symlink + a fake
    agent-vscode, invoke through the symlink, and confirm bash resolves
    to the real bin/agent-vscode (not bin/path-shim/agent-vscode)."""
    import subprocess

    emit_extension_stubs(install_dir, ["opencode"])
    emit_path_shim(install_dir)

    # Fake agent-vscode that just prints its own dir + args, so we can
    # tell which path it was launched from. The new stub invokes this via
    # ``python <helper>`` rather than relying on the helper's shebang, so
    # the helper must be Python (not bash).
    helper = install_dir / "bin" / "agent-vscode"
    helper.write_text(
        '#!/usr/bin/env python3\n'
        'import os, sys\n'
        'print("AGENT_VSCODE_DIR=" + os.path.dirname(sys.argv[0]))\n'
        'print("AGENT_VSCODE_ARGS=" + " ".join(sys.argv[1:]))\n'
    )
    helper.chmod(0o755)

    shim = install_dir / "bin" / "path-shim" / "opencode"
    out = subprocess.run(
        [str(shim), "--port", "1234"], capture_output=True, text=True, check=True
    )
    assert f"AGENT_VSCODE_DIR={install_dir / 'bin'}" in out.stdout, out.stdout
    assert "--agent opencode -- --port 1234" in out.stdout, out.stdout
