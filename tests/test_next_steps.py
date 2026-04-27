"""Tests for the post-install next-steps step list builder."""
from __future__ import annotations

from coding_agents.installer.next_steps import (
    Step,
    build_next_steps,
    render_terminal,
)
from coding_agents.installer.state import InstallerState


def _state(**kwargs) -> InstallerState:
    s = InstallerState()
    s.install_dir = "/tmp/install"
    s.mode = "hpc"
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


def test_first_three_steps_are_bashrc_sync_doctor():
    steps = build_next_steps(_state(agents=[]))
    assert "source ~/.bashrc" in (steps[0].action or ("", ""))[1]
    assert "coding-agents sync" in (steps[1].action or ("", ""))[1]
    assert "coding-agents doctor" in (steps[2].action or ("", ""))[1]


def test_vscode_steps_only_when_wrappable_agents_selected():
    steps_none = build_next_steps(_state(agents=["gemini"]))
    titles = [s.title for s in steps_none]
    assert not any("VSCode" in t for t in titles), titles

    steps_pi = build_next_steps(_state(agents=["pi"]))
    titles = [s.title for s in steps_pi]
    assert any("VSCode extensions" in t for t in titles)
    assert any("Settings Sync" in t for t in titles)


def test_smoke_test_step_skipped_in_local_mode():
    steps = build_next_steps(_state(agents=["claude"], mode="local"))
    assert not any("SLURM" in s.title for s in steps)


def test_smoke_test_step_present_in_hpc():
    steps = build_next_steps(_state(agents=["claude"], mode="hpc"))
    assert any("SLURM" in s.title for s in steps)


def test_vscode_reset_action_in_sidebar_step():
    steps = build_next_steps(_state(agents=["claude", "pi"]))
    sidebar = next(s for s in steps if "sidebar" in s.title.lower())
    assert sidebar.action == ("cmd", "coding-agents vscode-reset")


def test_doc_link_step_present():
    steps = build_next_steps(_state(agents=[]))
    last = steps[-1]
    assert last.action is not None
    assert last.action[0] == "url"
    assert "vscode_integration.md" in last.action[1]


def test_render_terminal_contains_each_step_title():
    steps = build_next_steps(_state(agents=["claude"]))
    out = render_terminal(steps)
    for s in steps:
        assert s.title in out


def test_render_terminal_marks_runnable_commands():
    steps = build_next_steps(_state(agents=[]))
    out = render_terminal(steps)
    # Each cmd step renders a "$ <cmd>" line
    assert "$ source ~/.bashrc" in out
    assert "$ coding-agents sync" in out


def test_render_terminal_marks_url_steps():
    steps = build_next_steps(_state(agents=[]))
    out = render_terminal(steps)
    assert "docs/vscode_integration.md" in out
    # OSC-8 hyperlink wrapping (start sequence + label visible)
    assert "\x1b]8;;docs/vscode_integration.md\x07docs/vscode_integration.md" in out


def test_render_terminal_renders_ext_links_with_osc8():
    steps = build_next_steps(_state(agents=["claude", "codex", "opencode", "pi"]))
    out = render_terminal(steps)
    # Each extension produces vscode: + marketplace OSC-8 wrappers
    assert "\x1b]8;;vscode:extension/anthropic.claude-code" in out
    assert "marketplace.visualstudio.com/items?itemName=anthropic.claude-code" in out
    # CLI fallback also present
    assert "code --install-extension anthropic.claude-code" in out


def test_ext_links_step_carries_all_selected_agents():
    steps = build_next_steps(_state(agents=["pi", "codex"]))
    ext_step = next(s for s in steps if s.ext_links)
    keys = {pair[0] for pair in ext_step.ext_links}
    assert keys == {"pi", "codex"}


def test_steps_are_dataclass_frozen():
    s = Step(title="t", body="b", action=None)
    import dataclasses
    assert dataclasses.is_dataclass(s)
    try:
        s.title = "x"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("Step should be frozen")
