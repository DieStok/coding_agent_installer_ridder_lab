"""Phase 4: OpenCode-specific behaviour for the VSCode extension wrapping.

OpenCode is the architectural outlier — no settings-side wrapper hook,
caught via shell-rc PATH-prefix shim instead.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from coding_agents.installer.policy_emit import emit_managed_vscode_settings
from coding_agents.installer.wrapper_vscode import (
    emit_extension_stubs,
    emit_path_shim,
)
from coding_agents.runtime import agent_vscode
from coding_agents.utils import (
    SHELL_MARKERS,
    SHELL_MARKERS_PATH_SHIM,
    inject_shell_block,
    remove_shell_block,
    render_path_shim_block,
    render_shell_block,
)


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.delenv("VSCODE_AGENT_FOLDER", raising=False)
    monkeypatch.setenv("SHELL", "/bin/bash")
    return tmp_path


@pytest.fixture
def install_dir(tmp_path):
    p = tmp_path / "install"
    (p / "bin").mkdir(parents=True)
    return p


# --------------------------------------------------------------------------- #
# OpenCode stub + path-shim symlink
# --------------------------------------------------------------------------- #

def test_opencode_stub_argv(install_dir):
    written = emit_extension_stubs(install_dir, ["opencode"])
    content = written[0].read_text()
    assert "--agent opencode" in content


def test_path_shim_dir_only_contains_opencode(install_dir):
    emit_extension_stubs(install_dir, ["opencode"])
    emit_path_shim(install_dir)
    shim_dir = install_dir / "bin" / "path-shim"
    children = list(shim_dir.iterdir())
    assert len(children) == 1
    assert children[0].name == "opencode"


def test_path_shim_symlink_relative_target(install_dir):
    emit_extension_stubs(install_dir, ["opencode"])
    shim = emit_path_shim(install_dir)
    assert shim.is_symlink()
    assert os.readlink(shim) == "../agent-opencode-vscode"


# --------------------------------------------------------------------------- #
# Settings.json defence-in-depth: terminal.integrated.env.linux.PATH
# --------------------------------------------------------------------------- #

def test_emit_includes_terminal_path_prefix(fake_home, install_dir):
    settings = fake_home / ".vscode-server" / "data" / "User" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{}")
    emit_managed_vscode_settings(install_dir, ["opencode"])
    parsed = json.loads(settings.read_text())
    term = parsed["terminal.integrated.env.linux"]
    assert term["PATH"].startswith(str(install_dir / "bin" / "path-shim"))
    assert "${env:PATH}" in term["PATH"]


def test_emit_terminal_merges_with_existing(fake_home, install_dir):
    settings = fake_home / ".vscode-server" / "data" / "User" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({
        "terminal.integrated.env.linux": {"OTHER": "1"}
    }))
    emit_managed_vscode_settings(install_dir, ["opencode"])
    parsed = json.loads(settings.read_text())
    assert parsed["terminal.integrated.env.linux"]["OTHER"] == "1"
    assert "PATH" in parsed["terminal.integrated.env.linux"]


# --------------------------------------------------------------------------- #
# Shell-rc dual marker block
# --------------------------------------------------------------------------- #

def test_render_path_shim_block_basics(tmp_path):
    block = render_path_shim_block(tmp_path / "install")
    assert SHELL_MARKERS_PATH_SHIM[0] in block
    assert SHELL_MARKERS_PATH_SHIM[1] in block
    assert "path-shim" in block
    assert 'export PATH=' in block


def test_inject_shell_block_path_shim_appended(fake_home, install_dir):
    rc = fake_home / ".bashrc"
    rc.write_text("# user content\n")
    inject_shell_block(install_dir, inject_path_shim=True)
    content = rc.read_text()
    assert SHELL_MARKERS[0] in content
    assert SHELL_MARKERS_PATH_SHIM[0] in content
    # Order: main block before path-shim block (so user-prepended bins go
    # first, then our shim wins).
    main_idx = content.index(SHELL_MARKERS[0])
    shim_idx = content.index(SHELL_MARKERS_PATH_SHIM[0])
    assert main_idx < shim_idx


def test_inject_idempotent_for_both_blocks(fake_home, install_dir):
    rc = fake_home / ".bashrc"
    rc.write_text("# user\n")
    inject_shell_block(install_dir, inject_path_shim=True)
    first = rc.read_text()
    inject_shell_block(install_dir, inject_path_shim=True)
    second = rc.read_text()
    assert first == second
    # Each marker appears exactly once
    assert second.count(SHELL_MARKERS[0]) == 1
    assert second.count(SHELL_MARKERS_PATH_SHIM[0]) == 1


def test_inject_without_shim_does_not_add_shim_block(fake_home, install_dir):
    rc = fake_home / ".bashrc"
    rc.write_text("")
    inject_shell_block(install_dir, inject_path_shim=False)
    content = rc.read_text()
    assert SHELL_MARKERS[0] in content
    assert SHELL_MARKERS_PATH_SHIM[0] not in content


def test_remove_shell_block_strips_both(fake_home, install_dir):
    rc = fake_home / ".bashrc"
    rc.write_text("# user\n")
    inject_shell_block(install_dir, inject_path_shim=True)
    remove_shell_block()
    content = rc.read_text()
    assert SHELL_MARKERS[0] not in content
    assert SHELL_MARKERS_PATH_SHIM[0] not in content
    assert "# user" in content


def test_remove_handles_only_main_block(fake_home, install_dir):
    rc = fake_home / ".bashrc"
    rc.write_text("")
    inject_shell_block(install_dir, inject_path_shim=False)
    remove_shell_block()
    assert SHELL_MARKERS[0] not in rc.read_text()


# --------------------------------------------------------------------------- #
# OpenCode env passthrough + binds
# --------------------------------------------------------------------------- #

def test_opencode_env_passthrough_full_list():
    parent = {name: f"v-{name}" for name in agent_vscode.ENV_PASSTHROUGH["opencode"]}
    overlay = agent_vscode.passthrough_env("opencode", parent)
    for name in agent_vscode.ENV_PASSTHROUGH["opencode"]:
        assert overlay[f"APPTAINERENV_{name}"] == f"v-{name}"


def test_opencode_env_includes_extension_port():
    overlay = agent_vscode.passthrough_env(
        "opencode", {"_EXTENSION_OPENCODE_PORT": "21337"}
    )
    assert overlay == {"APPTAINERENV__EXTENSION_OPENCODE_PORT": "21337"}


def test_opencode_binds_include_config_dir(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    (fake_home / ".config" / "opencode").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    binds = agent_vscode.build_apptainer_binds("opencode")
    assert any("/.config/opencode:" in b and b.endswith(":rw") for b in binds)


# --------------------------------------------------------------------------- #
# Doctor path-shim placement check
# --------------------------------------------------------------------------- #

def test_path_shim_check_pass(monkeypatch, install_dir):
    from coding_agents.commands import doctor_vscode
    expected = install_dir / "bin" / "path-shim" / "opencode"
    fake = subprocess.CompletedProcess(args=[], returncode=0, stdout=str(expected) + "\n", stderr="")
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fake)
    name, status, fix = doctor_vscode.opencode_path_shim_check(install_dir)
    assert status == "pass"


def test_path_shim_check_warn_on_npm_path(monkeypatch, install_dir):
    from coding_agents.commands import doctor_vscode
    fake = subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout=str(install_dir / "node_modules" / ".bin" / "opencode") + "\n",
        stderr="",
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fake)
    name, status, fix = doctor_vscode.opencode_path_shim_check(install_dir)
    assert status == "warn"
    assert "expected" in fix
