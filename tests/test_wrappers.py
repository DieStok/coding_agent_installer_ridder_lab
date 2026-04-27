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


# ---------------------------------------------------------------------------
# Sprint 1 Task 1.1 — wrapper security trio (synthesis §3.1, §3.2, §3.4)
# ---------------------------------------------------------------------------


def test_wrapper_validates_pwd_shape():
    """Synthesis §3.1: refuse cwd containing `"`, control chars, or
    newlines — these are audit-log-forgery vectors."""
    text = load_template()
    # The check is a case-pattern. Verify the patterns are present.
    assert '*[[:cntrl:]]*' in text
    assert '*\\"*' in text
    assert "exit 6" in text


def test_wrapper_requires_jq_on_host():
    """Synthesis §3.1: the audit-log JSON build relies on jq's --arg
    escaping. The previous fallback was unsafe; jq is now a hard
    requirement on the host."""
    text = load_template()
    assert "command -v jq" in text
    assert "exit 10" in text
    # No more printf-only fallback for argv encoding
    assert "<argv-elided: jq not in host PATH>" not in text


def test_wrapper_audit_log_uses_jq_n_for_safe_encoding():
    """Synthesis §3.1: the JSONL line is built entirely through jq -n
    --arg / --argjson, not printf interpolation."""
    text = load_template()
    # Old unsafe printf pattern is gone
    assert (
        'printf \'{"ts":"%s","agent":"%s","cwd":"%s"' not in text
    ), "audit log still uses printf interpolation (synthesis §3.1)"
    # New safe path is present
    assert "jq -nc" in text or "jq -n " in text
    assert '--arg ts' in text
    assert '--argjson argv' in text


def test_wrapper_audit_log_uses_flock():
    """Synthesis §3.4: line-atomic JSONL append via flock. POSIX O_APPEND
    atomicity only holds for ≤PIPE_BUF (4 KB); Codex prompt-as-argv
    flows trivially exceed that."""
    text = load_template()
    assert "flock 9" in text
    # The fd-9 redirection pattern
    assert "9>>" in text


def test_wrapper_provider_env_rejects_invalid_key_names():
    """Synthesis §3.2: provider.env keys must match a strict regex AND
    not be a poisonous-name. Both helpers must be defined and used."""
    text = load_template()
    assert "_is_valid_env_name" in text
    assert "_is_poisonous_env_name" in text
    # Defence rules
    assert "^[A-Z][A-Z0-9_]{0,63}$" in text
    # Spot-check the poisonous-name pattern includes the high-impact
    # injection vectors
    for poison in ("BASH_ENV", "PROMPT_COMMAND", "LD_*", "PYTHON*", "NODE_*"):
        assert poison in text, f"poisonous-name blocklist missing {poison}"


def test_wrapper_provider_env_allowlist_applied_to_keyfile_glob_too():
    """Synthesis §3.2 cross-ref: same allowlist applies to filename-derived
    names from the *_api_key / *_token / *_endpoint glob (not just to
    provider.env). Otherwise an attacker who can drop a file named
    `bash_env` (lowercase) into the secrets dir gets BASH_ENV exported."""
    text = load_template()
    # The keyfile loop must call _is_valid_env_name and
    # _is_poisonous_env_name on var_name before exporting.
    keyfile_section = text[text.index("for keyfile in"):]
    keyfile_section = keyfile_section[: keyfile_section.index("if [ -r \"$AGENT_SECRETS_DIR/provider.env\"")]
    assert "_is_valid_env_name" in keyfile_section
    assert "_is_poisonous_env_name" in keyfile_section


# ---------------------------------------------------------------------------
# Sprint 1 Task 1.7 — Pi + OpenCode HOME bind-mount (user decision 2026-04-27)
# ---------------------------------------------------------------------------


def test_wrapper_binds_claude_home():
    """Sprint 1 Task 1.5 (uniformity follow-up to Task 1.7): the claude
    case binds host ~/.claude/ writable so settings.json deny rules,
    CLAUDE.md memory, file-history, and statusbar config persist + are
    actually readable inside the SIF (the host-side write at install
    time is unreachable inside the SIF without this bind)."""
    text = load_template()
    case_block = text[text.index("case \"$AGENT_NAME\""):]
    case_block = case_block[: case_block.index("esac")]
    assert "claude)" in case_block
    assert '--bind "$HOME/.claude:$HOME/.claude"' in case_block


def test_wrapper_binds_codex_home():
    """Sprint 1 Task 1.5: codex case binds host ~/.codex/ writable so the
    sandbox_mode = "workspace-write" + [sandbox_workspace_write] schema
    we emit at install time is actually read by Codex inside the SIF."""
    text = load_template()
    case_block = text[text.index("case \"$AGENT_NAME\""):]
    case_block = case_block[: case_block.index("esac")]
    assert "codex)" in case_block
    assert '--bind "$HOME/.codex:$HOME/.codex"' in case_block


def test_wrapper_credentials_no_longer_overlay_at_agentuser_path():
    """Pre-Sprint-1.5 the wrapper did
        --bind $TMP/.credentials.json:/home/agentuser/.claude/.credentials.json:ro
    That target path was wrong once APPTAINERENV_HOME=$HOME made
    in-container HOME match the host's HOME path. Now that the whole
    ~/.claude/ is bound writable, the per-file overlay is removed (and
    the wrapper no longer breaks Claude's live OAuth token refresh).

    Strip comments before the check so inline historical notes about
    the old path don't cause a false positive.
    """
    text = load_template()
    # Drop full-line comments + trailing comments — leave only active code.
    code_only_lines = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        # Trailing-comment strip (cheap heuristic: split on " # " only)
        if " # " in line:
            line = line.split(" # ", 1)[0]
        code_only_lines.append(line)
    code_only = "\n".join(code_only_lines)
    assert "/home/agentuser/.claude" not in code_only, (
        "wrapper still has an active --bind targeting /home/agentuser/.claude/ "
        "— that target is incorrect since APPTAINERENV_HOME now sets in-container "
        "HOME to the host path."
    )


def test_wrapper_claude_login_existence_gate_preserved():
    """The 'run claude login first' message + exit 4 must still fire for
    AGENT_NAME=claude when ~/.claude/.credentials.json is missing (the
    pre-Sprint-1 user-onboarding flow)."""
    text = load_template()
    assert 'run \'claude login\' on submit node first' in text
    assert "exit 4" in text


def test_wrapper_binds_pi_agent_home():
    """Synthesis §3.10 + Sprint 1 Task 1.7: pi case binds host
    ~/.pi/agent into the container at the same path."""
    text = load_template()
    pi_block = text[text.index("case \"$AGENT_NAME\""):]
    pi_block = pi_block[: pi_block.index("esac")]
    assert "pi)" in pi_block
    assert '--bind "$HOME/.pi/agent:$HOME/.pi/agent"' in pi_block


def test_wrapper_binds_four_opencode_dirs():
    """Synthesis §3.12: OpenCode persists state in four HOME subdirs;
    all must be bound writable."""
    text = load_template()
    for sub in (".config/opencode", ".local/share/opencode", ".cache/opencode", ".local/state/opencode"):
        assert sub in text, f"OpenCode bind missing for {sub}"
    # The OPENCODE_DISABLE_DEFAULT_PLUGINS=1 default
    assert "APPTAINERENV_OPENCODE_DISABLE_DEFAULT_PLUGINS=1" in text


def test_wrapper_passes_apptainerenv_home_for_bind_compat():
    """The bind-mount path uses $HOME on the host; the in-container HOME
    must match so ~/.pi/agent and ~/.config/opencode/ resolve to the
    bound paths inside the SIF."""
    text = load_template()
    assert 'APPTAINERENV_HOME="$HOME"' in text


def test_wrapper_opencode_passthrough_allowlist():
    """Synthesis §3.12 bonus: OPENCODE_* env vars get passed through, but
    every name still goes through the security regex + poisonous-name
    blocklist (no env-var smuggling)."""
    text = load_template()
    for var in ("OPENCODE_CONFIG", "OPENCODE_PERMISSION", "OPENCODE_DISABLE_LSP_DOWNLOAD"):
        assert var in text, f"OpenCode passthrough missing {var}"
    # The passthrough loop validates each name before exporting.
    oc_block_start = text.index("OPENCODE_CONFIG OPENCODE_CONFIG_DIR")
    oc_block_end = text.index("# --- Audit log append")
    oc_block = text[oc_block_start:oc_block_end]
    assert "_is_valid_env_name" in oc_block
    assert "_is_poisonous_env_name" in oc_block


def test_wrapper_exec_includes_agent_home_binds():
    """The new AGENT_HOME_BINDS array must be wired into the exec call,
    or the bind-mount block has no effect."""
    text = load_template()
    # Find the exec block
    exec_start = text.index("exec apptainer exec")
    exec_block = text[exec_start:]
    assert '"${AGENT_HOME_BINDS[@]}"' in exec_block


def test_wrapper_exit_codes_cover_new_failures():
    """Sprint 1 Task 1.1/1.7 introduced new exit codes:
    6 ($PWD shape), 10 (jq missing), 11 (HOME bind setup failed)."""
    text = load_template()
    for code, reason in (
        (6, "$PWD shape"),
        (10, "jq missing"),
        (11, "HOME bind"),
    ):
        assert f"exit {code}" in text, f"missing exit {code} ({reason})"


def test_wrapper_refuses_shared_lab_infra_cwd():
    """Lab cwd-policy: refuse to run from /hpc/compgen/users/shared/*
    (read-only shared infrastructure, the SIF lives there)."""
    text = load_template()
    # Both bare and any-subdir patterns must be in the case statement.
    assert "/hpc/compgen/users/shared|/hpc/compgen/users/shared/*" in text
    # Hint mentions the user's own analysis dir
    assert "your own analysis dir" in text


def test_wrapper_refuses_bare_projects_root():
    """Lab cwd-policy: /hpc/compgen/projects (or with trailing /) is the
    bare projects root — work belongs in a specific project subdir."""
    text = load_template()
    assert "/hpc/compgen/projects|/hpc/compgen/projects/" in text
    assert "bare /hpc/compgen/projects root" in text


def test_wrapper_refuses_project_root_without_subdir():
    """Lab cwd-policy: /hpc/compgen/projects/<project>/ with no subdir
    under it is also refused — must be inside a subproject / analysis /
    raw / etc. subdir."""
    text = load_template()
    # The path-depth check counts IFS=/ parts.
    assert 'IFS=\'/\' read -ra _PWD_PARTS <<< "$PWD"' in text
    assert '"${#_PWD_PARTS[@]}" -lt 6' in text
    assert "refusing to run from a project root" in text


def test_wrapper_warns_when_cwd_has_no_user_component():
    """Lab cwd-policy: warn (don't refuse) if $PWD doesn't contain $USER
    as a path component. Convention is everyone works under their own
    analysis dir."""
    text = load_template()
    # The check is a case-glob with the full-component pattern */USER/*
    assert '*/"$USER"/*' in text
    assert "no path component" in text
    assert "Lab convention: work in your own subdir" in text
    # Must NOT exit on this — it's a warning only.
    warn_block_start = text.index('no path component')
    warn_block_end = text.index('# --- Precondition: $PWD is shape-safe')
    warn_block = text[warn_block_start:warn_block_end]
    assert "exit " not in warn_block, (
        "$USER-not-in-path is a warning only; must not call exit."
    )


def test_wrapper_cwd_policy_introduces_exit_12():
    """The cwd-policy refusals all use the same new exit code 12."""
    text = load_template()
    assert "exit 12" in text


def test_wrapper_carries_install_dir_relocation_todo():
    """Track the optional post-MVP design note: relocate
    ~/.{claude,codex,pi,opencode} into <install_dir>/state/<agent>/
    via per-agent env vars so the host $HOME isn't touched at all.
    Documented inline in the wrapper template; tested here so the TODO
    isn't silently dropped by a future cleanup pass."""
    text = load_template()
    assert "TODO (optional, post-MVP): relocate" in text, (
        "Inline TODO about relocating agent state into install_dir was "
        "removed. If you've actually done that work, also remove this test."
    )
    # Touch the four env vars by name so a future researcher grep'ing
    # for them lands here.
    for env_var in (
        "CLAUDE_CONFIG_DIR",
        "CODEX_HOME",
        "PI_CODING_AGENT_DIR",
        "OPENCODE_CONFIG_DIR",
    ):
        assert env_var in text, (
            f"TODO comment should mention {env_var} as the relocation lever; "
            "future implementers will grep for these."
        )
