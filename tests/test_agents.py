"""Tests for agents.py — agent registry validation."""
import pytest


def test_all_agents_have_required_fields():
    from coding_agents.agents import AGENTS

    required = [
        "display_name", "method", "binary", "version_cmd",
        "config_dir", "instruction_file", "hooks_support",
        "deny_rules_format", "mcp_format",
    ]
    for key, agent in AGENTS.items():
        for field in required:
            assert field in agent, f"Agent {key} missing field {field}"


def test_no_jai_keys_remain():
    """JAI is hard-deleted in MVP; no agent should carry jai_conf/jai_env_keys."""
    from coding_agents.agents import AGENTS

    for key, agent in AGENTS.items():
        assert "jai_conf" not in agent, f"Agent {key} still has jai_conf"
        assert "jai_env_keys" not in agent, f"Agent {key} still has jai_env_keys"


def test_opencode_package_name_corrected():
    """OpenCode's npm package is `opencode-ai`, not `opencode` (404 on npm)."""
    from coding_agents.agents import AGENTS

    assert AGENTS["opencode"]["package"] == "opencode-ai"


def test_six_agents():
    from coding_agents.agents import AGENTS

    assert len(AGENTS) == 6
    assert "claude" in AGENTS
    assert "codex" in AGENTS
    assert "opencode" in AGENTS
    assert "pi" in AGENTS
    assert "gemini" in AGENTS
    assert "amp" in AGENTS


def test_no_aider():
    from coding_agents.agents import AGENTS

    assert "aider" not in AGENTS


def test_presets():
    from coding_agents.agents import PRESETS, AGENTS

    assert set(PRESETS["core"]) == {"claude", "codex", "opencode", "pi"}
    assert set(PRESETS["all"]) == set(AGENTS.keys())


def test_npm_agents_have_package():
    from coding_agents.agents import AGENTS

    for key, agent in AGENTS.items():
        if agent["method"] == "npm":
            assert "package" in agent, f"npm agent {key} missing 'package'"


def test_vscode_extensions():
    from coding_agents.agents import agents_with_vscode_ext

    exts = agents_with_vscode_ext(["claude", "codex", "gemini"])
    ext_dict = dict(exts)
    assert ext_dict["claude"] == "anthropic.claude-code"
    assert ext_dict["codex"] == "openai.chatgpt"
    assert "gemini" not in ext_dict  # Gemini has no VSCode extension


def test_corrected_gemini_package():
    """Verify the Gemini CLI package name correction."""
    from coding_agents.agents import AGENTS

    assert AGENTS["gemini"]["package"] == "@google/gemini-cli"


def test_corrected_codex_vscode_extension():
    """Verify the Codex VSCode extension ID correction."""
    from coding_agents.agents import AGENTS

    assert AGENTS["codex"]["vscode_extension"] == "openai.chatgpt"


def test_pi_has_post_install():
    from coding_agents.agents import AGENTS

    assert "post_install" in AGENTS["pi"]
    assert any("pi-ask-user" in cmd for cmd in AGENTS["pi"]["post_install"])
