"""CI guard against silent edit-no-effect bugs from duplicate bundled/ trees.

The repo previously carried two ``bundled/`` directories: an outer one at
``<repo>/bundled/`` and an inner one at ``<repo>/src/coding_agents/bundled/``.
Synthesis §3.5 documents how they drifted: ``executor._bundled_dir()`` resolves
the inner copy, so the outer tree is effectively dead at runtime — yet some
build artifacts and READMEs reference the outer one. Maintainers editing the
outer tree got no warning that nothing read it.

Sprint 1 Task 1.3 picks the inner tree as canonical and replaces the outer
with a single stub README pointing at it. This test fails the build if the
divergence ever returns.

Also asserts there is no stale root-level ``<repo>/hooks/`` directory.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTER_BUNDLED = REPO_ROOT / "bundled"
INNER_BUNDLED = REPO_ROOT / "src" / "coding_agents" / "bundled"
ROOT_HOOKS = REPO_ROOT / "hooks"


def _hash_tree(root: Path) -> dict[str, str]:
    """Map relpath → sha256 for every regular file under ``root``."""
    out: dict[str, str] = {}
    if not root.exists():
        return out
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        # Ignore platform / editor cruft so the test focuses on payload.
        if p.name in {".DS_Store"} or p.suffix == ".backup":
            continue
        if "__pycache__" in p.parts:
            continue
        rel = p.relative_to(root).as_posix()
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def test_inner_bundled_tree_exists() -> None:
    """The canonical bundled tree (inner copy) must exist."""
    assert INNER_BUNDLED.is_dir(), (
        f"{INNER_BUNDLED} is the canonical bundled tree per Sprint 1 Task 1.3 "
        "and must exist."
    )


def test_no_stale_root_hooks_directory() -> None:
    """The root-level <repo>/hooks/ directory must not exist.

    Synthesis §3.5: the root-level hooks/deny_rules.json was already stale by
    8 home-dir denies and a Read(./build) → Read(./build/**) glob fix. Sprint 1
    Task 1.3 deletes it; this test ensures it stays deleted.
    """
    assert not ROOT_HOOKS.exists(), (
        f"{ROOT_HOOKS} should be deleted (Sprint 1 Task 1.3); the canonical "
        f"deny_rules.json lives in {INNER_BUNDLED / 'hooks' / 'deny_rules.json'}."
    )


def test_outer_bundled_is_stub_or_absent() -> None:
    """The outer <repo>/bundled/ tree should either be absent or a single
    stub README pointing at the inner tree.

    A diverging duplicate is a known drift trap. If the test fails because
    you legitimately need new content in the outer tree, prefer adding a
    hatch build hook that copies from inner → outer at build time, instead
    of maintaining two copies by hand.
    """
    if not OUTER_BUNDLED.exists():
        return  # absent is fine
    payload = [
        p
        for p in OUTER_BUNDLED.rglob("*")
        if p.is_file()
        and p.name not in {".DS_Store"}
        and p.suffix != ".backup"
        and "__pycache__" not in p.parts
    ]
    # Allow a single README.md as a stub.
    non_readme = [p for p in payload if p.name.lower() != "readme.md"]
    assert not non_readme, (
        f"{OUTER_BUNDLED} should contain only a stub README.md pointing at "
        f"{INNER_BUNDLED}. Found: {[str(p.relative_to(OUTER_BUNDLED)) for p in non_readme]}"
    )


def test_outer_and_inner_bundled_do_not_diverge() -> None:
    """If both trees exist, every file the outer tree contains must be
    byte-identical to its counterpart in the inner tree (modulo the stub
    README, which is allowed to differ since the inner tree typically has
    no README of its own at the same path).
    """
    if not OUTER_BUNDLED.exists():
        pytest.skip("outer bundled tree absent; nothing to compare")
    outer = _hash_tree(OUTER_BUNDLED)
    inner = _hash_tree(INNER_BUNDLED)
    diffs: list[str] = []
    for relpath, h_outer in outer.items():
        if relpath.lower() == "readme.md":
            continue  # stub README permitted to differ
        h_inner = inner.get(relpath)
        if h_inner is None:
            diffs.append(f"{relpath}: present in outer, missing in inner")
        elif h_inner != h_outer:
            diffs.append(f"{relpath}: outer ({h_outer[:8]}) ≠ inner ({h_inner[:8]})")
    assert not diffs, (
        "Outer and inner bundled trees have diverged — pick one canonical "
        "location (Sprint 1 Task 1.3) and route all reads through it. "
        "Differences:\n  " + "\n  ".join(diffs)
    )
