---
title: Post-HPC-diagnostic cleanup
type: fix
status: active
date: 2026-04-27
origin: docs/brainstorms/2026-04-27-post-hpc-diagnostic-cleanup-brainstorm.md
---

# Post-HPC-diagnostic cleanup

Six small follow-ups from `REPORT_2026-04-27-2010.md` Sections 14.5 +
14.7. None of them touches the SIF or the wrapper-template substantive
behavior — wrapper-side and CLI-side fixes from `a1f1160` + `687b15d` +
`8aed05f` + `dce06f8` are confirmed working in production.

## Overview

| Phase | Items | Files | Tests |
|---|---|---|---|
| 1 | Doctor probes (A1 opt-in SIF probe + A2 CLI source drift) | `commands/doctor.py`, `cli.py` | `tests/test_doctor.py` |
| 2 | Installer sweep (B1) + safe_symlink self-loop guard (B2) | `installer/executor.py`, `utils.py` | `tests/test_installer_sweeps_stale_node_modules.py`, `tests/test_safe_symlink.py` |
| 3 | Docs: refresh-after-pull subsection (C1) + CHANGELOG (C2) | `README.md`, `CHANGELOG.md` | n/a |
| 4 | Wrapper-template comment refresh (D1, D2) | `bundled/templates/wrapper/agent.template.sh` | n/a (comment-only — verify tests still pass) |
| 5 | Diagnostic-script bug fixes (E1, E2) | `code_review_claude_code_hpc_27_04_2026/scripts/{02,06,08}_*.sh` | n/a (shell scripts, manual verify) |

Phases are independent — any single phase can ship as a standalone
commit. Recommended order: 1 → 2 → 3 → 4 → 5 (defensive doctor probes
first so phase-2 regression tests see the right signal; docs after code
change is real; comment refresh after the underlying behavior is stable;
diagnostic scripts last because they're not on a hot path).

## Phase 1 — Doctor probes (A1 + A2)

### A1. Opt-in SIF runtime probe

**Behavior:** add a CLI flag `--probe-sif` to `coding-agents doctor`. By
default, row 19 keeps its current "labels via `apptainer inspect`"
behavior (fast). With `--probe-sif`, doctor additionally executes
`apptainer exec --containall --no-mount home --writable-tmpfs SIF
<bin> --version` for each baked tool and adds a row per tool:

```
│ N   │ SIF runtime: biome                       │ FAIL   │ SIF needs rebuild
│ N+1 │ SIF runtime: claude                      │ PASS   │ 2.1.119
```

**Tools to probe:** `claude`, `codex`, `opencode`, `pi`, `biome`,
`gitleaks`, `node`, `python` (eight). Probe binaries listed in the
existing `bundled/sif/package.json` plus the four baked-via-curl agents.

**Implementation sketch:**

```python
# src/coding_agents/commands/doctor.py — pseudocode
@click.option("--probe-sif", is_flag=True, help="Run apptainer exec SIF <bin> --version per baked tool. Slow (~5s).")
def doctor(scan_cron, scan_systemd, probe_sif):
    ...
    if probe_sif and apptainer and sif_resolved:
        for tool in _SIF_PROBED_TOOLS:  # tuple at module level
            ok, version = _probe_sif_binary(apptainer, sif_resolved, tool)
            checks.append((f"SIF runtime: {tool}", "pass" if ok else "fail", version or "binary missing — SIF rebuild needed"))
```

**Edge cases:**
- No apptainer on PATH → skip `--probe-sif` rows (don't fail the flag).
- SIF not readable → already covered by row 18; skip probes.
- Tool exits non-zero but prints to stderr (e.g., gitleaks `--version`
  exits 0 but some tools exit 1 on `--version`) — record stdout+stderr,
  PASS if either is non-empty AND exit ∈ {0, 1, 2}.

**Tests:**
- `test_doctor_probe_sif_flag_off_keeps_old_behavior`: invoke
  `coding-agents doctor` (no flag), assert no `SIF runtime:` rows.
- `test_doctor_probe_sif_executes_apptainer_per_tool`: monkeypatch
  `subprocess.run`, assert one call per tool in `_SIF_PROBED_TOOLS`.
- `test_doctor_probe_sif_reports_missing_binary_as_fail`: stub one
  apptainer call returning `FATAL: "biome": executable file not found`,
  assert row is FAIL with the rebuild hint.

### A2. CLI source drift row

**Behavior:** new doctor row (always-on, fast — single md5 compare).
Compares the byte content of:

- The currently-running `coding_agents/cli.py` (via
  `inspect.getsourcefile(coding_agents.cli)`).
- The on-disk `src/coding_agents/cli.py` in the project root.

If the running file is **inside** the project root's `src/` (editable /
dev install), short-circuit PASS — they're the same file. Otherwise
md5-compare. Mismatch → FAIL with hint `uv tool install --reinstall .`.

**Implementation sketch:**

```python
# src/coding_agents/commands/doctor.py — pseudocode
def _check_cli_source_drift(checks):
    import hashlib, inspect
    import coding_agents.cli as _cli
    running = Path(inspect.getsourcefile(_cli)).resolve()
    project_root = Path(__file__).resolve().parents[3]  # repo root
    on_disk = project_root / "src" / "coding_agents" / "cli.py"
    if not on_disk.exists():
        # CLI installed outside any repo (e.g., shipped wheel) — skip.
        return
    if str(running).startswith(str(project_root / "src")):
        checks.append(("coding-agents CLI matches source", "pass", "(editable install)"))
        return
    if hashlib.md5(running.read_bytes()).hexdigest() == hashlib.md5(on_disk.read_bytes()).hexdigest():
        checks.append(("coding-agents CLI matches source", "pass", ""))
    else:
        checks.append(("coding-agents CLI matches source", "fail", "uv tool install --reinstall ."))
```

**Edge cases:**
- Doctor invoked from a different cwd than the repo — `project_root`
  resolution via `Path(__file__).parents[3]` is robust to this.
- Wheel installed but no repo on disk (released package) — `on_disk` not
  found, skip the row entirely (don't false-positive).
- File reads fail (permissions, NFS) — wrap in try/except, report as
  `warn` with "could not compare".

**Tests:**
- `test_doctor_cli_drift_editable_install_passes`: simulate
  `getsourcefile` returning a path under repo `src/`, assert PASS.
- `test_doctor_cli_drift_matching_md5_passes`: stub running and on-disk
  to identical bytes, assert PASS.
- `test_doctor_cli_drift_mismatching_md5_fails`: stub differing bytes,
  assert FAIL row with the `--reinstall` hint.
- `test_doctor_cli_drift_missing_repo_skips`: `on_disk` absent, assert
  no row added (no false-positive on shipped wheels).

## Phase 2 — Installer sweep + symlink guard

### B1. Sweep `tools/node_modules/` in HPC mode

**Where:** `executor._install_tools` (or wherever the tools dir is set
up). When `mode == "hpc"`, before any other tools logic, `rmtree`
`<install_dir>/tools/node_modules/` if it exists, then log:

```
[install] HPC mode — removed stale tools/node_modules/ (biome and friends now live in the SIF)
```

In `--local` mode: untouched.

**Implementation sketch:**

```python
# src/coding_agents/installer/executor.py — pseudocode
def _install_tools(install_dir, tools, log, mode="hpc"):
    tools_node_modules = install_dir / "tools" / "node_modules"
    if mode == "hpc" and tools_node_modules.exists():
        shutil.rmtree(tools_node_modules)
        log.write("[install] HPC mode — swept stale tools/node_modules/ (now lives in SIF)\n")
    ...  # existing logic
```

**Tests** — new file `tests/test_installer_sweeps_stale_node_modules.py`:
- `test_install_tools_sweeps_node_modules_in_hpc_mode`: pre-populate
  `<install_dir>/tools/node_modules/.bin/biome`, run `_install_tools(...,
  mode="hpc")`, assert dir gone.
- `test_install_tools_preserves_node_modules_in_local_mode`: same setup,
  `mode="local"`, assert dir untouched.
- `test_install_tools_no_op_when_node_modules_absent_in_hpc_mode`: no
  pre-existing dir, run with `mode="hpc"`, assert no error and no log
  spam.

### B2. `safe_symlink` self-loop guard

**Where:** `src/coding_agents/utils.py:218` — add a guard at the top of
`safe_symlink`. If `source.absolute() == target.absolute()`, raise
`ValueError(f"safe_symlink: refusing to create self-loop at {target}")`
**before** any unlink / rename. This way the function fails loud rather
than silently producing a broken symlink.

**Implementation sketch:**

```python
# src/coding_agents/utils.py — pseudocode (insert at line ~233)
def safe_symlink(source: Path, target: Path) -> None:
    log.debug("safe_symlink: %s → %s", source, target)
    if source.absolute() == target.absolute():
        raise ValueError(
            f"safe_symlink: refusing to create self-loop "
            f"(source == target == {target.absolute()})"
        )
    if is_dry_run():
        ...
```

Why before `is_dry_run`: the dry-run path's `would(...)` would otherwise
report a self-loop intent without flagging it as broken. The guard
should fire under both normal and dry-run.

**Tests** — extend `tests/test_safe_symlink.py`:
- `test_safe_symlink_rejects_self_loop_absolute_paths`: pass identical
  absolute Path objects, assert `ValueError`.
- `test_safe_symlink_rejects_self_loop_via_relative_paths`: same dir,
  one absolute one relative — should still raise after `.absolute()`
  normalization.
- `test_safe_symlink_self_loop_guard_under_dry_run`: set
  `CODING_AGENTS_DRY_RUN=1`, assert `ValueError` still fires.

## Phase 3 — Docs

### C1. README "Refreshing the CLI after `git pull`" subsection

Append after the existing `uv tool install .` block (around line 80) in
`README.md`:

```markdown
### Refreshing the CLI after `git pull`

After pulling source changes, refresh the installed `coding-agents` CLI
with:

```bash
uv tool install --reinstall .
```

**Why `--reinstall` and not `--force`?** uv caches built wheels keyed by
the project version string. Because `coding-agents` keeps its version
pinned at `0.1.0` for in-place dev, `uv tool install --force .`
recreates the venv but reuses the cached wheel — your source changes
never make it in. `--reinstall` rebuilds the wheel from source. Doctor
row "coding-agents CLI matches source" surfaces this drift if you
forget.
```

### C2. CHANGELOG entry

Add to `CHANGELOG.md`:

```markdown
- Add `--probe-sif` flag to `coding-agents doctor` for explicit SIF
  runtime probing (slow, per-binary `apptainer exec --version`).
- Add doctor row "coding-agents CLI matches source" — flags drift
  between the installed uv-tool wheel and the on-disk source. Catches
  the common case where `git pull` lands new code but the user forgot
  to `uv tool install --reinstall .`.
- HPC-mode `coding-agents install` now sweeps stale
  `<install_dir>/tools/node_modules/` (left over from pre-9b87b0b
  installs that put biome on the host).
- `safe_symlink` rejects self-loops loudly (`ValueError`) instead of
  producing a broken symlink. Defensive — covers all callers.
- Docs: clarified that the post-`git pull` refresh recipe is `uv tool
  install --reinstall .`, not `--force` (the latter reuses cached
  wheels because the project version is pinned).
```

## Phase 4 — Wrapper-template comment refresh (D1, D2)

**File:** `src/coding_agents/bundled/templates/wrapper/agent.template.sh`

### D1. `/tmp` mechanism comment

Find the legacy block (likely above the `--bind "$TMPDIR:/tmp"` line)
that mentions "Cluster nodes share /tmp under sticky-bit semantics" and
replace with:

```bash
# /tmp inside the SIF: we use --writable-tmpfs (gives the container its
# own writable overlay) BUT also explicitly --bind "$TMPDIR:/tmp" so
# /tmp resolves to SLURM's per-job xfs tmpspace (gigabytes), NOT
# apptainer's default 64MiB tmpfs overlay. pi-subagents / Codex arg0
# need real fs semantics; the overlay rejects fcntl locks and similar.
# When SLURM is not in play, $TMPDIR usually equals /tmp anyway and the
# bind is a no-op (mount over self).
```

### D2. APPTAINERENV_HOME comment

Find the comment block that explains `--env HOME="$HOME"` and adjust to
remove the implication that `--env` silences the warning. Replacement:

```bash
# HOME inside the SIF: --env HOME="$HOME" sets the environment variable.
# It does NOT silence apptainer 1.4.5+'s cosmetic warning
# ("Overriding HOME environment variable with APPTAINERENV_HOME is not
# permitted") — apptainer translates --env KEY=val to APPTAINERENV_KEY
# internally, then warns on the translated form. We silence the warning
# downstream via the stderr-filter block (search for
# CODING_AGENTS_VERBOSE).
```

**Verification:** comment-only changes — `pytest tests/test_wrappers.py`
should still pass (no behavioral regression). No new tests.

## Phase 5 — Diagnostic-script bug fixes (E1, E2)

### E1. `02_smoke_versions.sh` and `06_audit_logs.sh`

Both scripts currently look at `$HOME/agent-logs/`. Change the
log-directory resolution to:

```bash
LOG_DIR="${AGENT_LOGS_DIR:-$HOME/agent-logs}"
```

…and use `$LOG_DIR` everywhere `$HOME/agent-logs` appears. The wrapper
exports `AGENT_LOGS_DIR` already (verified by Section 6 of the report:
`/hpc/compgen/users/dstoker/agent-logs/`).

### E2. `08_cwd_policy_behavior.sh`

The script uses `( cd <dir> && agent-claude --help | head -5; echo "[08]
exit=$?" )`. The `$?` reads `head`'s exit, not the agent's. Fix:

```bash
(
  cd "$dir" || exit 1
  out=$(agent-claude --help 2>&1)
  rc=$?
  echo "$out" | head -5
  echo "[08] exit=$rc"
)
```

**Verification:** scripts are shell only — no test harness in the repo
for them. Manual verify: re-run the scripts on an HPC node and confirm
they read the right paths / capture the right exit codes.

## Acceptance Criteria

- [ ] `coding-agents doctor` runs with no new flag and produces the same
      25-row output as before, plus one new row "coding-agents CLI
      matches source" (PASS in editable / unchanged install).
- [ ] `coding-agents doctor --probe-sif` adds 8 rows ("SIF runtime:
      <tool>") with PASS/FAIL based on actual `apptainer exec` output.
- [ ] After `coding-agents install` in HPC mode on a system with stale
      `tools/node_modules/.bin/biome`, the dir is gone.
- [ ] `safe_symlink(p, p)` raises `ValueError` (not silently a self-
      loop).
- [ ] `README.md` has the new "Refreshing the CLI after `git pull`"
      subsection.
- [ ] `CHANGELOG.md` lists all five changes.
- [ ] Wrapper-template comments accurately describe `--bind
      "$TMPDIR:/tmp"` and the stderr-filter mechanism.
- [ ] Diagnostic scripts read `$AGENT_LOGS_DIR` and capture real exit
      codes.
- [ ] All existing tests pass (399 → 399+N where N is the new tests).

## Dependencies & Risks

- **None on external dependencies.** All changes are internal.
- **Low risk on B1.** Sweeping `tools/node_modules/` in HPC mode is
  consistent with the post-9b87b0b architecture; `--local` mode is
  untouched.
- **Low risk on B2.** `ValueError` on self-loop is a hard failure, but
  this only fires in genuinely broken cases that today silently produce
  bad symlinks. Loud failure beats silent corruption.
- **Lab-admin coordination on biome-in-SIF.** Outside this plan's
  scope, but the new `--probe-sif` row will surface the gap in the
  report's "Section 14.7 #1". Once the SIF is rebuilt, the row will go
  green automatically.

## Out of Scope

- Rebuilding the SIF (lab admin job).
- Restoring backups (per known-still-pending #3 in the report).
- Codex `arg0` ENOTEMPTY (upstream cosmetic).
- Cwd-policy on `agent-<name> --version` (deferred per known-still-
  pending #1).
- `sif_sha` empty in audit logs.

## Sources & References

- **Origin:**
  `code_review_claude_code_hpc_27_04_2026/REPORT_2026-04-27-2010.md`
  (Sections 14.5 + 14.7).
- **Brainstorm:**
  `docs/brainstorms/2026-04-27-post-hpc-diagnostic-cleanup-brainstorm.md`.
- **Verified during plan write:**
  - `src/coding_agents/commands/doctor.py:358–376` (row 19 reads SIF
    labels, not manifest — corrected from brainstorm's first draft).
  - `src/coding_agents/bundled/coding_agent_hpc.def:10–17` (labels are
    static strings — confirms A1 premise).
  - `src/coding_agents/utils.py:218–256` (safe_symlink lacks
    source==target guard — confirms B2).
  - `src/coding_agents/installer/executor.py:357–366` (bin/claude
    symlink writer — single call site; B2's guard in safe_symlink
    covers it).
  - `rg "uv tool install" README.md docs/` (only `README.md:78` has it,
    no `--force` — C1 reframed to "add", not "swap").
