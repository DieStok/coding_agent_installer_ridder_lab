# Coding-agents sandbox installer — status snapshot
**As of:** 2026-04-26 18:33
**Branch / HEAD:** `main` @ (post-`929b404` + the home-dir revert that ships in this commit)
**Origin:** https://github.com/DieStok/coding_agent_installer_ridder_lab

---

## TL;DR

Everything **needed to ship MVP** is on `main`. The lab admin can build the SIF (done), upload (done — SHA matched), copy `install_coding_agents.sh` to the shared bin, and tell the lab. **The remaining work is post-MVP polish and end-to-end verification on the cluster.**

---

## ✅ Done

### Architecture & planning
- **Brainstorm + supplement + v2-deferred docs** captured in `/Users/dstoker6/Downloads/coding_agent_plans/docs/` (outside the package repo).
  - `brainstorms/2026-04-24-sandboxing-installer-rewrite-brainstorm.md` — original architecture
  - `brainstorms/2026-04-26-sandboxing-installer-mvp-supplement.md` — locked 28 MVP decisions
  - `v2-deferred.md` — explicit out-of-scope list
  - `plans/2026-04-26-001-feat-apptainer-sandbox-installer-mvp-plan.md` — A-LOT plan with 17 `[DEEPENED]` amendments after parallel review by 6 specialist agents (security/architecture/simplicity/performance/python/best-practices)

### Phase 1 — Foundation (commit `526e016` + `7d886f8`)
- Hard-deleted JAI from all three locations (`./jai/`, `bundled/jai/`, `src/coding_agents/bundled/jai/`) and from `agents.py`, state machinery, TUI screens, sync, uninstall, doctor, detect_existing.
- Fixed pre-existing bug: `agents.py` had `package: "opencode"` (404 on npm) — corrected to `opencode-ai`.
- `state.py`: collapsed 8 sandbox fields → 3 + `slurm_defaults` dict (per architecture-strategist review).
- `config.py`: dropped `jai_enabled`; added `SANDBOX_MODE: Literal["apptainer"]`, `DEFAULT_SANDBOX_SIF_PATH`, `DEFAULT_SLURM_DEFAULTS` with explicit `--export` allowlist (resolves M5/M10 SpecFlow contradiction).
- `bundled/templates/wrapper/agent.template.sh`: 130-line cwd-only Apptainer wrapper. Conda/venv `:ro` auto-binds, `pyvenv.cfg home =` realpath canonicalize + system-python allowlist (security H3), per-agent API key passthrough (security M5), SHA sidecar read instead of per-invocation hash (perf-oracle).
- `installer/sandbox_wrappers.py`: pure renderer with pinned `WRAPPER_VARS` + drift-detect.
- `utils.py`: extracted `render_shell_block` as pure function; new `AGENT_SIF`/`AGENT_SECRETS_DIR`/`AGENT_LOGS_DIR` env exports.
- All deletions cross-checked + tests updated.

### Phase 2+3 — SIF + managed policy (commit `0d85ea5`)
- `bundled/coding_agent_hpc.def`: Apptainer 1.4 recipe. After fixes (see "Build errors fixed" below): Ubuntu 24.04, Node 20 LTS, Python 3.12, gitleaks v8.21.2 pinned binary, all 4 agents via `npm ci` from committed `package-lock.json` (including `@anthropic-ai/claude-code@2.1.119` via npm not curl, for SIF reproducibility), `DISABLE_AUTOUPDATER=1`, `%labels` block for `apptainer inspect --json` doctor read.
- `bundled/sif/{package.json,README.md}` + lab-admin build instructions (Mac via official `ghcr.io/apptainer/apptainer:1.4.5` Docker image OR Lima; Linux native).
- `bundled/templates/managed-claude-settings.json`: defaults with corrected nesting (`permissions.disableBypassPermissionsMode` is a string `"disable"`, not boolean).
- `bundled/hooks/deny_rules.json`: expanded to ~/.ssh, ~/.gnupg, ~/.aws, ~/.kube, ~/.gcloud, ~/.codex/auth.json, ~/.netrc, ~/.config/gh; fixed `Read(./build) → Read(./build/**)`; replaced legacy starlark with `codex_config_toml_deny_paths`.
- `installer/policy_emit.py`: pure `merge_claude_settings`/`merge_codex_deny_paths` + I/O wrappers using `tomli_w` (added to `pyproject.toml`); back up on drift.
- `bundled/templates/agent-batch.sbatch`: canonical sbatch with `--export` allowlist.

### SIF build errors fixed (in main)
The first end-to-end build attempt revealed four stale assumptions; fixes pushed:
| Commit | Fix |
|---|---|
| `29a5bc6` | `From: ubuntu:22.04 → 24.04` (22.04's apt has no `python3.12`) |
| `b05d989` | Removed `npm config set unsafe-perm` (npm 10 dropped the option) |
| `a121def` | Removed hardcoded `useradd -u 1000` (Ubuntu 24.04 reserves UID 1000 for `ubuntu`) |
| `133dbda` | Rewrote `bundled/sif/README.md` with the actually-working command (`apptainer build` keyword required after the image name; `--platform linux/amd64` mandatory on Apple Silicon) |

### Phase B — SIF deployed to cluster (user manual + this turn)
- SIF built locally on dstoker's Mac (Apple Silicon, via `ghcr.io/apptainer/apptainer:1.4.5` Docker image with `--platform linux/amd64`).
- Uploaded to `/hpc/compgen/users/shared/agent/` via sftp (rsync/scp blocked by remote shell pollution; addressed via .bashrc restructure to early-return for non-interactive — `# >>> conda + uv stay above the guard, banner + aliases + functions go below`).
- SHA sidecar verified: ✅ matches.
- Atomic symlink swap: ✅ (`current.sif → coding_agent_hpc-2026.04.sif`).

### Polish (commit `8f9c6ec` + `723d5b4` + `929b404` + this commit)
- **`--exclude` flag** on `coding-agents install`. Skips an agent's install_cmd, wrapper, and managed-settings emit. Multi-agent `--exclude claude,codex`. Validation runs before TTY check so scripted callers get the right error.
- **Dry-run gaps in `policy_emit.py`** plugged: `_backup_if_drifted`, `target.parent.mkdir`, malformed-TOML backup branch — all now honor `is_dry_run()`. `coding-agents --dry-run install` truly touches no disk for the policy-emit step.
- **`scripts/install_coding_agents.sh`** — Variant A bootstrap. 134 lines. Idempotent (pulls instead of clones on re-run; skips venv if `.venv` exists). Defaults to `$HOME/coding_agents/` (~23 MB total — fine in home). Validation + `uv` check + prereq check + venv create + `uv pip install -e .` + clear next-step block.

### Tests
**124 pytest tests pass** on `main`. New tests added during MVP work:
- `tests/test_wrappers.py` — wrapper template drift-detect, idempotency, security/perf invariants (10 tests).
- `tests/test_policy_emit.py` — pure merge functions, dedup behaviour, settings template nesting, deny_rules security-critical paths, single-source claude/codex parity, dry-run no-disk-write assertions (10 tests).
- `tests/test_cli_install_exclude.py` — `--exclude` flag wiring, default-preservation, unknown-agent rejection (4 tests).

---

## 🟡 Partially done / verified-conceptually-not-end-to-end

### Phase C — Install + smoke-test on cluster
**What's done:** the package is committed; the SIF is on the share; the wrappers and policy emit are all wired.
**What's NOT verified end-to-end:**
- Lab admin has not yet copied `scripts/install_coding_agents.sh` to `/hpc/compgen/users/shared/agent/bin/install_coding_agents.sh`.
- No user has run `coding-agents install` against the new code on the cluster yet.
- `agent-claude --version` from a `srun --pty` has not been smoke-tested. (Local Docker-exec test passed — confirms the SIF-baked binary works.)
- `coding-agents doctor` from a compute node has not been run.
- The four wrappers (`agent-claude`, `agent-codex`, `agent-opencode`, `agent-pi`) have not been exercised against real agent invocations.

### Bashrc restructuring
- User restructured `~/.bashrc` on the HPC into the three-section layout (always-run env + early-return guard + interactive content).
- **Not verified clean** — non-interactive ssh still emits `declare -x` blob (likely `/etc/profile.d/*.sh` → VS Code env-capture).
- User worked around it via sftp instead of rsync. **Long-term fix:** move the early-return guard above `/etc/bashrc` source line if the noise persists for non-VSCode SSH contexts.

---

## 🔴 Remaining work (post-MVP, in priority order)

### Phase 4 follow-up (lab-internal polish)
None of these block the MVP from being usable. Each is independently shippable.

| # | Item | Effort | Plan ref |
|---|---|---|---|
| 1 | **`installer/screens/sandbox_config.py`** — replacement TUI screen for the deleted `JaiConfigScreen`. Surfaces SIF path, secrets/logs dirs, SLURM defaults, canonical `srun` line. Right now the TUI silently uses `config.py` defaults. | ~3-4 h | Plan §4.1 Phase 3 task 5, M24 |
| 2 | **`commands/project_init.py` helpers** — append git-ignore blocklist to `~/.config/git/ignore` (idempotent, marker-wrapped); install `.git/hooks/pre-commit` calling `gitleaks protect --staged` (collision-safe). | ~2 h | Plan §4.1 Phase 3 task 6, M21/M22 |
| 3 | **`commands/sync.py`** — `_sync_managed_settings()`, `_sync_codex_config()`, `_sync_sif_sha_sidecar()`. Currently sync doesn't touch the policy files or the SHA sidecar. | ~1 h | Plan §4.1 Phase 4 task 1 |
| 4 | **`commands/uninstall.py` opt-in prompts** — "Remove agent-secrets/? [y/N]" / "Remove agent-logs/? [y/N]". Currently silent retention. | ~30 min | Plan §4.1 Phase 4 task 2 |
| 5 | **`commands/doctor.py` IntEnum + CheckResult dataclass refactor** — replace `(name, status, message)` tuples + magic strings with `class DoctorExit(IntEnum)` + `@dataclass(frozen=True) class CheckResult`. Improves type safety + makes scripted `doctor` use viable. | ~2 h | Plan §4.1 Phase 2 task 5 + kieran-python review |
| 6 | **`scripts/hpc_sandbox_check.sh`** — companion to `hpc_prereq_check.sh`. From inside `srun --pty`: probe `apptainer --version ≥ 1.4`, SIF execs (`apptainer exec current.sif true`), `--no-mount home,cwd,tmp` honoured, `unshare -U true`, `ulimit -n ≥ 65536`. | ~1 h | Plan §4.1 Phase 4 task 3, M27 |
| 7 | **README rewrite** — three sections (quick-start, conda/venv idiom, troubleshooting table) + DPO callout in bold near top. | ~2 h | Plan §4.1 Phase 4 task 5 |

**Total Phase 4 effort:** ~11–13 hours of focused work.

### Lab-admin one-time deployment (no code change)
- [ ] Copy `scripts/install_coding_agents.sh` to `/hpc/compgen/users/shared/agent/bin/install_coding_agents.sh` (`chmod 0755`).
- [ ] Announce path to lab.
- [ ] Optional: write a 1-page lab-internal "how to use sandboxed agents" doc.

### Open external dependencies (track but don't block)
- [ ] **hpcsupport** — confirm `/hpc/compgen/users/shared/agent/` exists with read-all + write-lab-admin (PARENT brainstorm §5 "unverified assumption"; `dstoker` confirmed write access in this session).
- [ ] **UMC DPO** — approval for LLM endpoint usage (US endpoints currently shipped; EU endpoints deferred to v2 G1; NOT approved for patient data).
- [ ] **Lab admin** — decision on SIF rebuild cadence (manual for now; v2 C1 brings CI-built signed SIF).

---

## 🔵 Deferred to v2 (explicitly NOT in MVP)

See `docs/v2-deferred.md` (in the parent dir, outside the package git repo) for the full list. **Headline items by priority** per the v2-prioritisation hint:

1. **Outbound proxy + auth-header injection** (B1/B3) — biggest residual security risk; today API keys are visible to any in-sandbox process.
2. **EU-endpoint defaults** (G1) — blocks patient-data work.
3. **Stop-hook PreToolUse migration** (E1/E2/E3) — turns warn-only into actual blocking.
4. **Managed Claude settings true enforcement** (D5, NEW from deepening review) — write to `/etc/claude-code/managed-settings.json` instead of `~/.claude/settings.json` so users can't override the disable-bypass setting.
5. **SIF SHA allowlist verification** (C4, NEW from deepening) — doctor verifies `current.sif` SHA against `/hpc/.../shared/agent/SHA256SUMS` published by lab admin.
6. **Bind-path canonicalization library** (D6, NEW from deepening) — centralised path-validation; prerequisite for re-introducing `AGENT_EXTRA_BIND` safely.
7. **JSONL `O_APPEND` line-atomicity guard** (F3, NEW from deepening) — `flock` for argv >4 KB to prevent log interleaving.
8. **age-encrypted credentials** (D2).
9. **Log rotation + Loki** (F1/F2).
10. **CI-built signed SIF + version pinning** (C1/C2).
11. **Bubblewrap fallback / `--local` mode / macOS support** (A1/A2).
12. **iRODS/Yoda staging helper** (H1).
13. **JAI auto-migration command** (H2).
14. **Skill-repo SHA pinning** (H3).
15. **Shared lab-admin servers.json / deny-list / sbatch templates dir** (H7).

---

## 🎯 Immediate next concrete step

For dstoker, when next on the HPC:

```bash
# 1. Pull main to your existing repo clone (or run install_coding_agents.sh fresh)
cd ~/coding_agents/coding-agents-package    # or wherever your clone is
git pull origin main

# 2. Re-install the package
source .venv/bin/activate
uv pip install -e .

# 3. Safe self-test (no Claude install touched, no real disk writes)
coding-agents --dry-run install --exclude claude

# 4. Real install (still excludes Claude — your existing claude binary unchanged)
coding-agents install --exclude claude

# 5. Doctor on submit node
coding-agents doctor

# 6. Smoke-test on a compute node
srun --account=compgen --time=00:30:00 --mem=2G --gres=tmpspace:2G \
     --cpus-per-task=1 \
     --export=PATH,VIRTUAL_ENV,CONDA_PREFIX,CONDA_DEFAULT_ENV,LD_LIBRARY_PATH,HOME,USER,TERM,LANG,LC_ALL \
     --pty bash
agent-codex --version          # should print version through the SIF
agent-opencode --version
agent-pi --version
```

If any of those steps trip, paste the error — most failures will be one of the wrapper exit codes 3 / 4 / 5 / 7 / 8, each with a self-explaining message.

---

## File index (all in the package repo)

| Path | Role |
|---|---|
| `bundled/coding_agent_hpc.def` | Apptainer SIF recipe |
| `bundled/sif/{package.json,package-lock.json,README.md}` | npm bundle pinning + build instructions |
| `bundled/templates/wrapper/agent.template.sh` | The wrapper template (renderered per agent) |
| `bundled/templates/managed-claude-settings.json` | Claude defaults |
| `bundled/templates/agent-batch.sbatch` | Canonical sbatch template |
| `bundled/hooks/deny_rules.json` | Single-source deny rules → Claude JSON + Codex TOML |
| `src/coding_agents/installer/sandbox_wrappers.py` | Pure wrapper renderer |
| `src/coding_agents/installer/policy_emit.py` | Claude settings + Codex TOML emitter |
| `src/coding_agents/installer/executor.py` | The install pipeline (added `_create_sandbox_wrappers`, `_bootstrap_user_dirs`, `_emit_managed_policy`) |
| `scripts/install_coding_agents.sh` | Lab-shared bootstrap script (Variant A) |
| `scripts/hpc_prereq_check.sh` | Submit-node prereq audit (existing; banner adds: "does not verify sandboxing") |
