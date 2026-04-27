# Implementation Summary & Issues — 2026-04-27

**Plan being implemented:** [`docs/plans/2026-04-27-001-fix-mvp-review-remediation-and-v1-finalization-plan.md`](plans/2026-04-27-001-fix-mvp-review-remediation-and-v1-finalization-plan.md)
**Repo:** `coding-agents-package/` @ start commit `860aa38`
**Branch:** `main`
**Started:** 2026-04-27, autonomous run

This document tracks progress through the Sprint 1 (MUST-FIX) implementation, plus any divergences, blockers, or deferred decisions encountered. The plan totals ~71 hours across four sprints; this autonomous run targets **Sprint 1 (~13 hours, 12 tasks)** which unblocks first lab-wide rollout. Sprints 2–4 are out of scope for this run and remain in the plan as future work.

## Run scope

**In scope (Sprint 1, MUST-FIX):**
- Task 1.0 — Pre-flight CI guardrail tests
- Task 1.1 — Wrapper security trio (jq/JSON validation, provider.env allowlist, flock for JSONL)
- Task 1.2 — Atomic `secure_write_text`
- Task 1.3 — Bundled tree dedup + stale root cleanup
- Task 1.4 — Codex integration trio (sync dispatch fix, `[sandbox_workspace_write]` schema, drop fictional key)
- Task 1.5 — OpenCode MCP shape fix (Effect Schema-correct writer)
- Task 1.6 — Pi MCP `imports: ["claude-code"]` + `toolPrefix: "short"`
- Task 1.7 — Pi + OpenCode HOME bind-mount in wrapper
- Task 1.8 — Claude managed-settings: `$schema` + first-run banner (hpcsupport ticket left to user)
- Task 1.9 — README one-line fix

**Out of scope (deferred to future runs):**
- Sprint 2 URGENT (~35 h) — first patch release (executor split, schema versioning, atomic-write hardening, etc.)
- Sprint 3 NICE-TO-HAVE + v1 plan completion (~20 h)
- Sprint 4 NON-ESSENTIAL cleanup (~3 h)
- Manual Apptainer / SLURM smoke-tests (require real HPC node)

## Approach

- One git commit per task (or per logical group of co-touching tasks).
- Run `pytest` after each substantive code change; if any pre-existing test starts failing, halt and document.
- Push to `origin/main` periodically.
- Mark Sprint 1 plan checkboxes as done at the end; commit that.

## Progress log

(Filled in as work proceeds.)

| Task | Status | Commit | Notes |
|------|--------|--------|-------|

## Divergences from plan

(Filled in if any.)

## Deferred decisions / blockers

(Filled in if any.)

## Final summary

(Filled in at the end of the run.)
