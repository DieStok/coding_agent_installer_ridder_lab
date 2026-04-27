"""Tests for the lab cwd-policy module.

Mirrors the bash-side checks in
``bundled/templates/wrapper/agent.template.sh``. The two sides are kept
in lockstep — if you change one, change the other and update the tests.
"""
from __future__ import annotations

from coding_agents.cwd_policy import evaluate


def test_under_shared_lab_infra_is_refused():
    verdict, msg = evaluate(
        cwd="/hpc/compgen/users/shared/agent",
        user="dstoker",
    )
    assert verdict == "refuse"
    assert "shared lab" in msg


def test_exactly_shared_root_is_refused():
    verdict, _ = evaluate(cwd="/hpc/compgen/users/shared", user="dstoker")
    assert verdict == "refuse"


def test_bare_projects_root_is_refused():
    verdict, msg = evaluate(cwd="/hpc/compgen/projects", user="dstoker")
    assert verdict == "refuse"
    assert "bare /hpc/compgen/projects root" in msg


def test_project_root_without_subdir_is_refused():
    verdict, msg = evaluate(
        cwd="/hpc/compgen/projects/cool_project",
        user="dstoker",
    )
    assert verdict == "refuse"
    assert "no subdir" in msg


def test_project_with_one_subdir_is_ok_or_warn():
    """A subdir under the project root passes the refusal check; the
    follow-up warn check fires only if $USER isn't a path component."""
    verdict, msg = evaluate(
        cwd="/hpc/compgen/projects/cool_project/raw",
        user="dstoker",
    )
    # Refusal check passed (we have a subdir under the project)
    assert verdict != "refuse"
    # But $USER 'dstoker' isn't a component, so warn fires
    assert verdict == "warn"
    assert "no path component 'dstoker'" in msg


def test_canonical_analysis_path_is_ok():
    """The lab convention path passes everything cleanly."""
    verdict, msg = evaluate(
        cwd="/hpc/compgen/projects/cool_project/cool_subproject/analysis/dstoker/work",
        user="dstoker",
    )
    assert verdict == "ok"
    assert msg == ""


def test_user_personal_scratch_is_ok():
    """/hpc/compgen/users/<user>/ is always fine (personal scratch)."""
    verdict, _ = evaluate(
        cwd="/hpc/compgen/users/dstoker/coding_agents",
        user="dstoker",
    )
    assert verdict == "ok"


def test_user_substring_does_not_satisfy_path_component_check():
    """The $USER check is component-based, not substring. 'dstokers'
    (e.g. another user with longer name) doesn't satisfy 'dstoker'."""
    verdict, _ = evaluate(
        cwd="/hpc/compgen/projects/cool_project/dstokers/work",
        user="dstoker",
    )
    # 'dstoker' is not a full component (only 'dstokers' is); should warn
    assert verdict == "warn"


def test_no_user_env_skips_warning():
    """If $USER is empty, the warning is skipped silently — CI / sandboxed
    shells shouldn't be bothered."""
    verdict, msg = evaluate(
        cwd="/hpc/compgen/projects/cool_project/raw",
        user="",
    )
    assert verdict == "ok"
    assert msg == ""


def test_outside_hpc_compgen_evaluates_normally():
    """The evaluator itself doesn't gate on /hpc/compgen — that's done
    by check_cwd_warn_only at the CLI surface. evaluate() returns ok
    for paths outside the lab tree, since none of the policy patterns
    match."""
    verdict, _ = evaluate(cwd="/Users/alice/some/repo", user="alice")
    assert verdict == "ok"
