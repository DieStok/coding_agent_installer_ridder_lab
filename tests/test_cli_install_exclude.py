"""Tests for the new `coding-agents install --exclude` flag wiring.

The flag itself lives in cli.py; the filter applies in two places:
1. CodingAgentsInstaller.__init__ filters state.agents on construction.
2. AgentSelectScreen filters the picker + preset application.
"""
from __future__ import annotations

import pytest


def test_tui_exclude_filters_state_on_construction(monkeypatch, tmp_path):
    """Constructing the TUI with excluded_agents removes them from state.agents."""
    # Avoid loading the user's real ~/.coding-agents.json
    monkeypatch.setattr("coding_agents.installer.tui.load_config", lambda: {})

    from coding_agents.installer.tui import CodingAgentsInstaller

    # Excluding 'claude' should leave codex/opencode/pi from the default core preset
    tui = CodingAgentsInstaller(mode="hpc", excluded_agents={"claude"})
    assert "claude" not in tui.state.agents
    assert "codex" in tui.state.agents
    assert "opencode" in tui.state.agents
    assert "pi" in tui.state.agents
    assert tui.excluded_agents == {"claude"}


def test_tui_no_exclude_keeps_full_default(monkeypatch):
    """Default behavior (no --exclude) is unchanged."""
    monkeypatch.setattr("coding_agents.installer.tui.load_config", lambda: {})

    from coding_agents.installer.tui import CodingAgentsInstaller

    tui = CodingAgentsInstaller(mode="hpc")
    assert set(tui.state.agents) == {"claude", "codex", "opencode", "pi"}
    assert tui.excluded_agents == set()


def test_cli_rejects_unknown_agent_name():
    """Typing --exclude foo should exit non-zero with a clear message."""
    from typer.testing import CliRunner
    from coding_agents.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["install", "--exclude", "definitely_not_an_agent"])
    assert result.exit_code != 0
    assert "unknown agent" in result.stdout.lower()


def test_cli_accepts_known_agents_then_requires_tty(monkeypatch):
    """--exclude with a real agent name passes validation (TUI then errors on no TTY)."""
    from typer.testing import CliRunner
    from coding_agents.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["install", "--exclude", "claude,codex"])
    # Validation passes; TUI then refuses non-TTY (CliRunner has no real tty)
    assert result.exit_code == 1
    assert "interactive terminal" in result.stdout.lower()
