# `bundled/` is a stub — canonical content lives at `src/coding_agents/bundled/`

The `bundled/` tree was deduplicated on 2026-04-27 (Sprint 1 Task 1.3 of
`docs/plans/2026-04-27-001-fix-mvp-review-remediation-and-v1-finalization-plan.md`).

**Canonical location:** `src/coding_agents/bundled/`

That tree ships with the wheel via `[tool.hatch.build.targets.wheel]
packages = ["src/coding_agents"]` in `pyproject.toml`, so it's the only
location consumed by the installed package at runtime. Maintainers editing
the outer tree historically got no signal that their edits had no effect
(`executor._bundled_dir()` resolves the inner copy). Synthesis §3.5
documents how the two trees had already diverged when the dedup happened.

**SIF build:** `coding_agent_hpc.def` is now in `src/coding_agents/bundled/`
alongside the rest of the bundled content. The build still runs from the
repo root:

```bash
apptainer build coding_agent_hpc.sif src/coding_agents/bundled/coding_agent_hpc.def
```

The `%files` paths inside the `.def` resolve relative to the build context
(repo root) and reference `src/coding_agents/bundled/sif/...`.

**CI guard:** `tests/test_bundled_tree_dedup.py` fails the build if the
divergence ever returns or if anything more than this stub README appears
in `bundled/`.
