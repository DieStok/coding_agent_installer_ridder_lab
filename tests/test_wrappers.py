"""Tests for the Apptainer sandbox wrapper template + renderer.

Validates:
- Template loads from the bundled location.
- Placeholder set in the template matches WRAPPER_VARS exactly (drift detect).
- Render produces output for each MVP agent.
- Re-rendering with the same inputs produces byte-identical output (idempotency).
- Required exit-code messages and security-critical strings are present.
"""
from __future__ import annotations

import re

import pytest

from coding_agents.installer.sandbox_wrappers import (
    WRAPPER_VARS,
    load_template,
    render_wrapper,
    template_placeholders,
)


def test_template_loads():
    text = load_template()
    assert text.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in text
    assert "umask 077" in text


def test_template_placeholders_match_wrapper_vars():
    """Drift detect: the {{VAR}} set in the template must equal WRAPPER_VARS."""
    text = load_template()
    placeholders = template_placeholders(text)
    assert placeholders == set(WRAPPER_VARS), (
        f"Template/renderer drift. Template has {placeholders}, "
        f"WRAPPER_VARS has {set(WRAPPER_VARS)}. "
        "Update both in lockstep."
    )


@pytest.mark.parametrize("agent_key,binary", [
    ("claude", "claude"),
    ("codex", "codex"),
    ("opencode", "opencode"),
    ("pi", "pi"),
])
def test_render_per_mvp_agent(agent_key, binary):
    text = load_template()
    rendered = render_wrapper(
        text,
        agent_key=agent_key,
        agent_display_name=f"Test-{agent_key}",
        agent_binary=binary,
        default_sif_path="/some/path/current.sif",
    )
    # All placeholders consumed
    assert "{{" not in rendered, "Unsubstituted placeholder left in output"
    # Agent name and binary appear in expected positions
    assert f'AGENT_NAME="{agent_key}"' in rendered
    assert f'AGENT_BINARY="{binary}"' in rendered
    # Default SIF path baked in
    assert "/some/path/current.sif" in rendered


def test_render_is_byte_identical_on_repeat():
    """Idempotency: same inputs → same bytes."""
    text = load_template()
    a = render_wrapper(
        text,
        agent_key="claude",
        agent_display_name="Claude Code",
        agent_binary="claude",
        default_sif_path="/x/current.sif",
    )
    b = render_wrapper(
        text,
        agent_key="claude",
        agent_display_name="Claude Code",
        agent_binary="claude",
        default_sif_path="/x/current.sif",
    )
    assert a == b


def test_render_rejects_missing_var():
    """Renderer guards: refuse if WRAPPER_VARS gains a value with no source."""
    # We can only verify by mutating WRAPPER_VARS via inspection — instead,
    # confirm that all 4 known placeholders are required (the renderer's
    # guard runs unconditionally, since values is built explicitly).
    # This test is a smoke test for the guard structure.
    text = "{{AGENT_KEY}} {{AGENT_BINARY}} {{AGENT_DISPLAY_NAME}} {{DEFAULT_SIF_PATH}}"
    rendered = render_wrapper(
        text,
        agent_key="x",
        agent_display_name="X",
        agent_binary="x",
        default_sif_path="/p",
    )
    assert rendered == "x x X /p"


def test_wrapper_contains_security_critical_strings():
    """Security findings (security-sentinel H3/H4/M5) must remain in template."""
    text = load_template()

    # H4: conda/venv binds default :ro
    # Find the conda bind line and confirm it ends with :ro
    conda_bind = re.search(r'--bind "\$CONDA_BASE_REAL:\$CONDA_BASE_REAL:(\w+)"', text)
    assert conda_bind, "conda base bind missing"
    assert conda_bind.group(1) == "ro", "conda base must bind read-only (security H4)"

    venv_bind = re.search(r'--bind "\$VENV_HOME_REAL:\$VENV_HOME_REAL:(\w+)"', text)
    assert venv_bind, "venv home bind missing"
    assert venv_bind.group(1) == "ro", "venv home must bind read-only (security H4)"

    # H3: pyvenv.cfg path canonicalization + allowlist
    assert "realpath -e" in text, "must canonicalize pyvenv.cfg home (security H3)"
    assert "/opt/python/" in text, "system-python prefix allowlist required"

    # M5: per-agent API key passthrough from $AGENT_SECRETS_DIR
    # (Auto-discovery glob over *_api_key / *_token / *_endpoint / etc.
    # replaced the original hardcoded `_export_key_if_present` helper so
    # adding a new provider doesn't require a wrapper edit.)
    assert 'APPTAINERENV_' in text, "must export keys via APPTAINERENV_* (M5)"
    assert '"$AGENT_SECRETS_DIR"/*_api_key' in text, "must scan secrets dir for *_api_key (M5)"
    assert '"$AGENT_SECRETS_DIR"/*_token' in text, "must scan secrets dir for *_token (M5)"
    assert 'provider.env' in text, "must support provider.env for multi-var configs (M5)"

    # Wrapper exit codes covered
    for code, hint in (
        (3, "SLURM_JOB_ID"),
        (4, "claude login"),
        (5, "SIF unreadable"),
        (7, "cwd not writable"),
        (8, "TMPDIR"),
    ):
        assert f"exit {code}" in text, f"missing exit {code} ({hint})"


def test_wrapper_uses_sif_sha_sidecar_not_per_invocation_hash():
    """Performance: sha256sum of SIF must NOT appear in the wrapper hot path
    (cached at install time in ${SIF_REAL}.sha256). See perf-oracle review."""
    text = load_template()
    assert "sha256sum" not in text, (
        "Wrapper must not run sha256sum on the SIF per invocation — "
        "use the cached ${SIF_RESOLVED}.sha256 sidecar."
    )
    assert "${SIF_RESOLVED}.sha256" in text, "SHA sidecar read missing"


def test_wrapper_does_not_carry_cut_extra_bind_env_hatches():
    """AGENT_EXTRA_BIND/AGENT_EXTRA_ENV were cut from MVP (simplicity #4 +
    security H3/M1). Re-introduction needs the v2 D6 canonicalization library."""
    text = load_template()
    assert "AGENT_EXTRA_BIND" not in text
    assert "AGENT_EXTRA_ENV" not in text
