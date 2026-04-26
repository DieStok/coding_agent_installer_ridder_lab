"""Tests for --local flag behavior."""
import pytest


def test_installer_state_default_mode():
    from coding_agents.installer.state import InstallerState

    state = InstallerState()
    assert state.mode == "hpc"


def test_installer_state_local_mode():
    from coding_agents.installer.state import InstallerState

    state = InstallerState(mode="local")
    assert state.mode == "local"


def test_config_dict_includes_mode():
    from coding_agents.installer.state import InstallerState

    state = InstallerState(mode="local")
    config = state.to_config_dict()
    assert config["mode"] == "local"


def test_from_config_preserves_mode():
    from coding_agents.installer.state import InstallerState

    config = {"install_dir": "/test", "mode": "local", "agents": ["claude"]}
    state = InstallerState.from_config(config)
    assert state.mode == "local"


def test_from_config_defaults_to_hpc():
    from coding_agents.installer.state import InstallerState

    config = {"install_dir": "/test", "agents": ["claude"]}
    state = InstallerState.from_config(config)
    assert state.mode == "hpc"


def test_default_config_has_mode():
    from coding_agents.config import DEFAULT_CONFIG

    assert "mode" in DEFAULT_CONFIG
    assert DEFAULT_CONFIG["mode"] == "hpc"


def test_hpc_only_sets():
    from coding_agents.config import HPC_ONLY_SKILLS, HPC_ONLY_HOOKS

    assert "hpc-cluster" in HPC_ONLY_SKILLS
    assert "hpc_validator" in HPC_ONLY_HOOKS


def test_local_mode_defaults_no_hpc_skills():
    from coding_agents.config import DEFAULT_SKILLS, HPC_ONLY_SKILLS

    local_skills = [s for s in DEFAULT_SKILLS if s not in HPC_ONLY_SKILLS]
    assert "hpc-cluster" not in local_skills
    assert "compound-engineering" in local_skills


def test_local_mode_defaults_no_hpc_hooks():
    from coding_agents.config import DEFAULT_HOOKS, HPC_ONLY_HOOKS

    local_hooks = [h for h in DEFAULT_HOOKS if h not in HPC_ONLY_HOOKS]
    assert "hpc_validator" not in local_hooks
    assert "lint_runner" in local_hooks
    assert "agents_md_check" in local_hooks


def test_default_dir_local():
    from coding_agents.installer.screens.install_dir import _default_dir

    result = _default_dir(mode="local")
    assert "coding_agents" in result
    assert "/hpc/" not in result


def test_centralized_defaults_used_in_state():
    """Verify InstallerState uses the centralized defaults from config.py."""
    from coding_agents.config import DEFAULT_SKILLS, DEFAULT_HOOKS, DEFAULT_TOOLS
    from coding_agents.installer.state import InstallerState

    state = InstallerState()
    assert state.skills == DEFAULT_SKILLS
    assert state.hooks == DEFAULT_HOOKS
    assert state.tools == DEFAULT_TOOLS
