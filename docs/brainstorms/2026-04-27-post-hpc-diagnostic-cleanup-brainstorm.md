---
title: Post-HPC-diagnostic cleanup
date: 2026-04-27
status: open
origin: code_review_claude_code_hpc_27_04_2026/REPORT_2026-04-27-2010.md
---

# Post-HPC-diagnostic cleanup

After the 2026-04-27 HPC diagnostic run, the wrapper-side and CLI-side
issues from `a1f1160` + `687b15d` + `8aed05f` + `dce06f8` are confirmed
fixed in production (Section 14.3 / 14.6 of the report). What remains is
six small follow-ups, all within the package — no new SIF builds, no
architectural changes.

## What We're Building

Six targeted fixes, grouped by intent:

**A. Doctor probes that catch silent regressions**
- **A1** Doctor row 19 (`SIF baked versions`) reads
  `coding-agents.versions.*` labels from `apptainer inspect --json`.
  Those labels are **static strings** declared in
  `coding_agent_hpc.def` `%labels` (verified: `def` lines 10–17). They
  are decoupled from actual install success in `%post` — biome was
  added to `package.json` in 9b87b0b without a matching label, and even
  with a label, "label declared" ≠ "binary present". Add a runtime
  probe: per baked tool, `apptainer exec SIF <bin> --version`. Slow
  path, but truth.
- **A2** New doctor row: compare `md5(src/coding_agents/cli.py)` against
  `md5(installed cli.py via inspect.getsourcefile)`. Catches stale
  uv-tool wheels after `git pull` (the exact regression from 14.4).

**B. Installer sweep + symlink guard**
- **B1** In HPC mode, `coding-agents install` should `rm -rf
  <install_dir>/tools/node_modules/` to sweep stale host-side biome (and
  any other npm leftovers from pre-9b87b0b installs). Add a regression
  test.
- **B2** `safe_symlink` (utils.py:218) was already fixed in 7f7490b for
  the `target.resolve()`-follows-symlinks bug, but it still lacks an
  explicit `source.absolute() == target.absolute()` guard. The
  `bin/claude` self-loop seen in the report (Section 10) is consistent
  with a pathological case where the resolved source happens to equal
  the target. Add the guard inside `safe_symlink` itself — covers all
  callers (binary AND config-file paths) in one place.

**C. Documentation: refresh recipe after `git pull`**
- **C1** Verified doc surface: only `README.md:78` says `uv tool install
  .` (initial install). No `--force` mentions anywhere in docs. So this
  is **add**, not **swap** — append a "Refreshing the CLI after `git
  pull`" subsection to README that says `uv tool install --reinstall .`
  with one-paragraph rationale (uv's wheel cache + pinned `0.1.0` makes
  `--force` a silent no-op; only `--reinstall` rebuilds from source).
- **C2** CHANGELOG entry recording the rationale (forward-looking — for
  anyone who follows old guides that say `--force`).

**D. Wrapper-template comment refresh**
- **D1** Replace legacy "Cluster nodes share /tmp under sticky-bit
  semantics" comment in `agent.template.sh` with the current mechanism:
  explicit `--bind "$TMPDIR:/tmp"` mapping the per-job SLURM tmpspace.
- **D2** Clarify the APPTAINERENV_HOME comment: `--env HOME=$HOME` does
  NOT silence apptainer 1.4.5's warning (it fires regardless). The
  actual silencer is the stderr-filter block from 687b15d. One-line fix.

**E. Diagnostic-script bugs (in-repo `code_review_claude_code_hpc_27_04_2026/scripts/`)**
- **E1** Scripts `02_smoke_versions.sh` and `06_audit_logs.sh` look
  under `$HOME/agent-logs/` but the wrapper writes to `$AGENT_LOGS_DIR`
  (defaults to `<install_dir>/../agent-logs/`). Honor `$AGENT_LOGS_DIR`
  first.
- **E2** `08_cwd_policy_behavior.sh` reads `head`'s exit via the pipe.
  Capture the agent's real exit code instead.

## Why This Approach

The report's failures clustered around three themes:

1. **Silent caches** — uv wheel cache made `--force` invisible; SIF
   rebuild gap made `manifest`-based doctor checks dishonest. Fix: have
   the doctor *execute* probes (A1) and *compare bytes* (A2). Cheap
   defensive engineering.
2. **Stale artifacts left behind on the host** — pre-9b87b0b biome,
   one-time `bin/claude` self-loop. Fix: sweep on install (B1), guard
   the symlink writer (B2).
3. **Documentation and inline comments drifting** behind code commits
   (C, D). Fix: short, mechanical updates.

Group E is bonus housekeeping — the scripts live in this repo from
`d91bc8d`, but they're not on a hot path. Worth doing while we're here
so the next diagnostic run doesn't trip on the same script bugs.

## Key Decisions

- **Doctor row 19 probes runtime, not manifest.** Slower (extra
  `apptainer exec` calls), but the manifest is build-time metadata and
  doesn't reflect "did the SIF rebuild actually succeed". Section 4 of
  the report shows the exact failure mode.
- **CLI-source drift as a doctor row, not an install nudge** (A2). A
  doctor row is discoverable on demand; an install nudge fires only on
  install, which is the *opposite* of when the drift is dangerous (drift
  matters between installs).
- **`coding-agents install` in HPC mode does the sweep** (B1), not a
  separate `coding-agents clean` command. The user already runs install
  to refresh; piggybacking the cleanup avoids a second-step they could
  forget.
- **Don't add a `--reinstall` shorthand** to coding-agents (e.g.
  `coding-agents refresh-cli`). The right answer is to teach docs to use
  the right uv command — adding our own wrapper hides what's actually
  happening and creates support surface.
- **No SIF-rebuild logic in the package.** That's a lab-admin
  responsibility (`/hpc/compgen/users/shared/agent/current.sif`).
  Doctor's new runtime probe (A1) will surface the gap; humans handle
  the rebuild.

## Scope Boundaries

In scope:
- Doctor row 19 probe (A1)
- New doctor row for CLI drift (A2)
- Installer sweep of `tools/node_modules/` (B1)
- bin-symlink self-loop guard (B2)
- Doc swap `--force` → `--reinstall` + CHANGELOG (C1, C2)
- Two wrapper-template comment updates (D1, D2)
- Diagnostic-script fixes (E1, E2)

Out of scope:
- Rebuilding the SIF (lab admin)
- Restoring backups (per known-still-pending #3 in the report)
- Codex `arg0` ENOTEMPTY (upstream cosmetic)
- Cwd-policy on `agent-<name> --version` (deferred per known-still-
  pending #1)
- `sif_sha` empty in audit logs (mentioned but not investigated in the
  report)

## Resolved Questions

1. **A1 implementation cost.** Each `apptainer exec SIF <bin> --version`
   adds ~0.5–1s per probed binary. With ~8 baked tools, that's 4–8s on
   doctor. **Decision: opt-in `--probe-sif` flag.** Doctor stays snappy
   by default; CI / HPC operators can run the slow probe explicitly.
2. **B1 blast radius.** **Decision: HPC-only.** The sweep only fires
   when `config["mode"] == "hpc"`. Local mode preserves the host npm
   install.
3. **A2 corner cases.** **Decision: short-circuit for editable installs.**
   If `inspect.getsourcefile(coding_agents.cli)` resolves under the
   repo's `src/` dir, mark the row PASS without an md5 compare (running
   source IS on-disk source).
4. **C1 doc surface.** **Verified by `rg`:** only `README.md:78` says
   `uv tool install .` (initial install, no flag). No existing `--force`
   to swap. C1 reframes to: append a "Refreshing the CLI after `git
   pull`" subsection.

## Open Questions

(none remaining — all resolved above)

## Next Steps

After this brainstorm passes a small review:

1. Resolve open questions (lean answers above) before writing the plan.
2. Convert to `/ce:plan` with explicit phases + filenames + tests.
3. User confirms before any code is written.
