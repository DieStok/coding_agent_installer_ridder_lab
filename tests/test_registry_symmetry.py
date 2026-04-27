"""CI guard for registry-vs-handler symmetry.

Synthesis §3.6 / Sprint 1 Task 1.4: ``agents.py:34`` declares Codex's
``deny_rules_format`` as ``"codex_toml"``, but ``commands/sync.py:155``
dispatches on ``"starlark"``. The mismatch silently no-ops Codex deny-rule
sync. This test ensures every ``deny_rules_format`` and ``mcp_format``
string declared in the registry has a corresponding dispatch handler — both
on the install path (``policy_emit.py``, ``convert_mcp.py``) and on the
sync path (``commands/sync.py``).
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from coding_agents.agents import AGENTS


def _read_source(rel_path: str) -> str:
    return (
        Path(__file__).resolve().parent.parent
        / "src"
        / "coding_agents"
        / rel_path
    ).read_text()


def _declared(field: str) -> set[str]:
    """Distinct non-None values declared for ``field`` across the registry."""
    return {
        agent[field]
        for agent in AGENTS.values()
        if agent.get(field) is not None
    }


def test_every_declared_deny_rules_format_has_a_sync_handler() -> None:
    """Every ``deny_rules_format`` string must appear in commands/sync.py
    so that ``coding-agents sync`` actually applies it. Catches synthesis
    §3.6's ``"starlark"`` vs ``"codex_toml"`` drift.
    """
    sync_src = _read_source("commands/sync.py")
    declared = _declared("deny_rules_format")
    missing = {fmt for fmt in declared if f'"{fmt}"' not in sync_src and f"'{fmt}'" not in sync_src}
    assert not missing, (
        "These deny_rules_format values are declared in agents.py but have "
        f"no dispatch in commands/sync.py: {sorted(missing)}. "
        "Add an 'elif fmt == ...' branch or update the registry."
    )


def test_no_orphan_deny_format_strings_in_sync() -> None:
    """The reverse: every literal ``elif fmt == "..."`` in sync.py must
    correspond to a declared format. Catches stale dispatch branches like
    the ``"starlark"`` bug that synthesis §3.6 documented.
    """
    sync_src = _read_source("commands/sync.py")
    declared = _declared("deny_rules_format") | {"claude"}  # claude format also handled

    # Find quoted strings that follow ``fmt ==`` (single or double quoted).
    import re

    pattern = re.compile(r"""fmt\s*==\s*['"]([^'"]+)['"]""")
    used = set(pattern.findall(sync_src))
    orphans = used - declared
    assert not orphans, (
        f"commands/sync.py dispatches on these format strings that are not "
        f"declared in any agent's deny_rules_format: {sorted(orphans)}. "
        "Either remove the dead branch or add the agent."
    )


def test_every_declared_mcp_format_has_a_writer() -> None:
    """Every ``mcp_format`` string must have a writer in ``convert_mcp.py``.

    Catches the dual class of bugs where a new mcp_format is added to
    the registry but no writer exists, and where a writer exists but no
    agent declares the format.
    """
    convert_src = _read_source("convert_mcp.py")
    declared = _declared("mcp_format")
    # Each declared format must appear as a string literal somewhere in
    # convert_mcp.py (in the dispatch table or in a writer function).
    missing = {
        fmt
        for fmt in declared
        if f'"{fmt}"' not in convert_src and f"'{fmt}'" not in convert_src
    }
    assert not missing, (
        "These mcp_format values are declared in agents.py but have no "
        f"writer dispatch in convert_mcp.py: {sorted(missing)}."
    )


def test_registry_uses_only_known_format_strings() -> None:
    """Catch typos like ``"codex_toml"`` vs ``"codex-toml"`` by asserting
    the declared format strings come from a known set. Update the allowed
    sets when adding a genuinely new format.
    """
    allowed_deny = {"claude", "codex_toml", "opencode"}
    allowed_mcp = {"claude", "codex", "opencode", "pi", "gemini", "amp"}

    declared_deny = _declared("deny_rules_format")
    declared_mcp = _declared("mcp_format")

    unknown_deny = declared_deny - allowed_deny
    unknown_mcp = declared_mcp - allowed_mcp

    assert not unknown_deny, (
        f"Unknown deny_rules_format strings: {sorted(unknown_deny)}. "
        "Either fix the typo or extend the allowed set in this test."
    )
    assert not unknown_mcp, (
        f"Unknown mcp_format strings: {sorted(unknown_mcp)}. "
        "Either fix the typo or extend the allowed set in this test."
    )
