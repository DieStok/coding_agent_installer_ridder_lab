# Diagnostic Review — coding-agents on UMC Utrecht HPC

You are Claude Code, running on the HPC login or compute node. The user
who launched you is testing the `coding-agents` package after a heavy
afternoon of fixes on 2026-04-27. Your job is to perform a **thorough
end-to-end diagnostic review** and produce a written report.

You are NOT to fix code on your own — only report. The user will read
your report and decide what to act on.

## Scope and ground rules

- **Read-only investigation by default.**
  - **Allowed without asking:** running `scripts/*.sh`, `git fetch`,
    `git pull`, `git status`, `git log`, `git clone` of the 5-whys
    skill into `.claude/skills/`, reading any file, running
    `coding-agents doctor` and any other read-only `coding-agents`
    subcommand.
  - **Not allowed without explicit user approval:** `coding-agents
    install`, `coding-agents uninstall`, `coding-agents sync`,
    `coding-agents update`, `git push`, `git commit`, deleting or
    moving any file under `~/.claude`, `~/.codex`, `~/.opencode`,
    `~/.pi`, `~/.config/opencode`, allocating a SLURM job longer than
    5 minutes, or writing outside `code_review_claude_code_hpc_27_04_2026/`.
  - **Always allowed for cleanup of obvious junk:** `rm` of files
    under `/tmp/pi-*-uid-$(id -u)/` after the residue check; if the
    user did not run any agent today, those are leftovers from earlier
    sessions and pose no value.
- **No agent re-installs.** A working install already exists at
  `~/coding_agents/` or `/hpc/compgen/users/$USER/coding_agents/`. Use
  it as-is. If it's missing or broken, stop and report that fact.
- **Use 5-Whys for non-trivial failures, not cosmetic noise.** Apply
  the technique to: any FAIL row from `coding-agents doctor`, any
  agent that fails to launch or load extensions, any audit log that
  has gaps, any symlink that resolves to itself or to nothing. Do NOT
  apply it to: warnings the user already knows about (the cwd-policy
  bash check is one), expected `(via SIF)` notes, or cosmetic
  formatting issues.
- **Report all hypotheses, not just the one you confirm.** If you think
  there are three possible causes, list all three with the evidence
  for/against each, even after one is confirmed.

## Setup (run these once, in order)

### 1. Make sure the repo is on the latest commit

```bash
cd ~/coding-agents-package    # or wherever the checkout is
git fetch
git status
git log -1 --oneline
```

The HEAD should be `215ca9c` ("fix(wrapper): mount host /tmp instead of
SIF tmpfs overlay") or later. If older, `git pull` first.

### 2. Install the 5-whys skill project-locally

```bash
mkdir -p .claude/skills
git clone https://github.com/awesome-skills/5-whys-skill.git \
  .claude/skills/5-whys
```

This places the skill at `.claude/skills/5-whys/` so it is available to
you within this project. Read its `SKILL.md` and apply its workflow to
every failure mode you investigate. Do not skip the technique — answer
all five "why" levels even if the first feels obvious.

### 3. Confirm the wrapper template version

```bash
grep -c "no-mount home,tmp" /hpc/compgen/users/$USER/coding_agents/bin/agent-claude
# should be 0  — the host /tmp fix landed on commit 215ca9c
grep -c "no-mount home" /hpc/compgen/users/$USER/coding_agents/bin/agent-claude
# should be 1
```

If the deployed wrapper is still on the old form, the user will need to
re-run `coding-agents install`. **Stop and report** rather than running
install yourself.

## Diagnostic procedure

The `scripts/` directory contains numbered shell scripts. Run them in
order. Each prints labelled output that you should quote in your report
section by section.

| # | Script | What it checks |
|---|---|---|
| 01 | `01_doctor_baseline.sh`     | `coding-agents doctor` — all 25+ rows |
| 02 | `02_smoke_versions.sh`      | `--version` for each agent + audit-log spot-check |
| 03 | `03_pi_extensions.sh`       | Pi loads all four lab-default extensions interactively |
| 04 | `04_apptainer_probes.sh`    | Live apptainer-flag probes (HOME mechanism, /tmp source) |
| 05 | `05_wrapper_inspect.sh`     | Wrapper template state, version, expected flags |
| 06 | `06_audit_logs.sh`          | Audit log files exist + are append-only + have entries |
| 07 | `07_path_shim_resolution.sh`| OpenCode shell-rc path-shim still wins on PATH |
| 08 | `08_cwd_policy_behavior.sh` | Cwd-policy: refuse paths, warn paths, OK paths |
| 09 | `09_residue_check.sh`       | Stale `/tmp/pi-*` and `~/.codex/tmp/arg0/` from prior runs |
| 10 | `10_node_dependency.sh`     | Whether the host actually needs node/npm anymore |

You are encouraged to invent additional ad-hoc probes if the canned
scripts surface anomalies. Document any custom probe in your report.

## What to investigate beyond the scripts

After running the scripts, also probe the following — these are the
weak/uncertain spots the user wants verified:

1. **Cwd-policy bash check.** The wrapper warns about cwd convention
   for `agent-<name> --version` etc. Document the current behavior in
   the report (which exact cwds trigger refusal vs warn vs OK) — the
   user will decide separately whether to act on it. Don't propose a
   redesign.
2. **Cosmetic-warning filter (commit `687b15d`).** Verify
   `agent-claude --version` prints no `WARNING:` lines from apptainer.
   If any warning slips through, quote the exact text and propose
   the precise additional grep pattern. Don't change the wrapper
   yourself.
3. **Pi `/tmp/pi-subagents-uid-<uid>/` accumulation.** Run
   `agent-pi --version` twice in a row and check whether the
   directory accumulates state between runs. Report what you see.
4. **OpenCode VSCode end-to-end.** If a VSCode Remote-SSH session is
   active to the cluster, open the OpenCode sidebar and observe whether
   the wrapper actually intercepts the `child_process.spawn("opencode")`
   call. Confirm via `ps -ef | grep apptainer` while the sidebar is
   alive. **If you cannot connect via Remote-SSH, mark this as
   "untestable in this session" — do not attempt to spawn VSCode
   yourself.**
5. **First-run Pi seed (read-only check).** Inspect the deployed
   `agent-pi` wrapper for the `/opt/pi-default-settings.json` cp
   block; verify the inner `apptainer exec` has `--env "HOME=$HOME"`
   (commit `8aed05f`). **Do NOT delete or rename
   `~/.pi/agent/settings.json` to force a re-test** — that would lose
   user state. A real seed test requires a fresh user account, which
   is outside this review's scope.
6. **Symlink integrity.** `safe_symlink` had a self-loop bug fixed on
   `7f7490b`. Without re-running `coding-agents sync` (which is not
   allowed), spot-check that key symlinks point at real files:
   ```bash
   for f in ~/.claude/CLAUDE.md ~/.codex/AGENTS.md \
            ~/.pi/agent/AGENTS.md ~/.config/opencode/AGENTS.md; do
     [ -e "$f" ] && \
       echo "$f -> $(readlink "$f") (resolves to: $(readlink -f "$f"))" || \
       echo "$f: missing"
   done
   ```
   Each present link should resolve to a regular file (not back to
   itself, not dangling).
7. **Backup performance.** Don't trigger a backup. Just report the
   sizes (`du -sh ~/.claude ~/.codex 2>/dev/null`) so the user can
   estimate next-install duration against the parallelization +
   gzip-level-6 commit `2cb88c8`.

## Apply the 5-Whys skill to every failure

For each red row from doctor, each FAIL from the smoke scripts, and
each unexpected behavior:

1. Quote the symptom verbatim.
2. Walk down the chain: Why did X happen? Because Y. Why Y? Because Z.
   Continue until you hit a root cause that's actionable (or until you
   bottom out at "this is how the upstream library works, can't go
   deeper from here").
3. Record the chain in the report alongside the symptom.

Do this even for non-blocking warnings — the goal is institutional
knowledge, not just a clean report.

## Produce the report

Fill in `REPORT_TEMPLATE.md` (in this same directory) with your
findings. Save it as `REPORT_<YYYY-MM-DD-HHMM>.md` next to the template
when complete.

### Report quality bar

- **One section per script run.** Don't bundle script outputs into a
  single dump.
- **Quote actual output** rather than paraphrasing. The user will trust
  raw output more than your summary.
- **Mark every claim PASS / WARN / FAIL** in the table at the top.
- **End every FAIL section with a 5-whys chain.**
- **List hypotheses you considered and rejected**, not just the one you
  confirmed. If you eliminated alternative theories, mention which and
  on what evidence.
- **Distinguish "tested and confirmed working" from "looked OK
  superficially."** If you ran an actual end-to-end probe, say so. If
  you only inspected the rendered wrapper script statically, say that.

## Bug-fix context (what the user shipped today, 2026-04-27)

This is what changed in the package today. Use this list to know what
you're testing, and to attribute any observed weirdness to the right
commit if needed.

| Commit | Change |
|---|---|
| `860aa38` | Auto-discover all provider API keys + support `provider.env` |
| `a2ba3cb` | Canonicalize HOME + expand `pyvenv.cfg` allowlist |
| `d35efe7` | Pre-delete stale `<install_dir>/bin/entire` before re-install |
| `c3ab926` | Add `pi-web-access` + `pi-mcp-adapter` to Pi post-install |
| `928a7e8` | Per-tool links for the 'linters' bundle |
| `fc7c378` | SIF: bump ccstatusline to 2.2.10 |
| `3d6aa43` | Fix "unhashable type: dict" merging hook entries into empty list |
| `a3383de` | OpenCode path-shim resolves `agent-vscode` via `readlink -f` |
| `7b523b0` | Align installer TUI text + walkthrough with no-wrap-via-sif reality |
| `7f7490b` | **Fix safe_symlink self-loop bug** (ELOOP on re-install / re-sync) |
| `2cb88c8` | Parallelize agent backups + gzip level 6 (perf) |
| `9b87b0b` | **Bake biome into SIF**, drop host npm install in HPC mode |
| `8aed05f` | Pass HOME via `--env`, dedupe binds under `$PWD` |
| `687b15d` | Silence cosmetic apptainer warnings via stderr filter |
| `215ca9c` | **Mount host /tmp** instead of SIF tmpfs overlay (Pi fix) |

### Known-fixed issues (verify they're really gone)

1. **Re-install ELOOP** — `~/.pi/agent/AGENTS.md` etc. became self-loop
   symlinks on the second run. Fixed on `7f7490b`. Verify by re-checking
   symlink targets after any sync.
2. **Pi extensions claim in TUI tools screen** — the text used to say
   "auto-installed after Pi setup"; it's now "baked into the SIF, seeded
   on first run." Fixed on `7b523b0`. Verify the TUI text.
3. **Merge "unhashable type: dict"** — fixed on `3d6aa43`. Re-running
   `coding-agents sync` over an existing config should not crash.
4. **OpenCode path-shim** — `bin/path-shim/opencode` symlink now
   resolves `agent-vscode` correctly via `readlink -f`. Fixed on
   `a3383de`.
5. **Cwd-policy at CLI surface** — the warning used to fire on
   `coding-agents install`/`sync`/`doctor`. Now only on actual agent
   invocations. Fixed inside `7b523b0`. Verify `coding-agents install`
   prints no cwd-policy line.
6. **APPTAINERENV_HOME warning** — on apptainer 1.3+ the wrapper's
   `export APPTAINERENV_HOME=$HOME` triggered a cosmetic
   "is not permitted" warning. Replaced with `--env HOME=$HOME`
   (`8aed05f`) + a stderr filter (`687b15d`). Verify the warning is now
   suppressed.
7. **Pi /tmp EPERM** — pi-subagents extension failed to load against
   the SIF tmpfs `/tmp`. Now using host `/tmp`. Fixed on `215ca9c`.
   Verify `agent-pi` (interactive, not `--version`) loads cleanly.

### Known-still-pending issues

1. **Cwd-policy bash check still fires for `agent-<name> --version`**
   even though `--version` is a no-side-effect probe. The user has
   deferred this. Document in your report whether it bothers you.
2. **`crawl4ai` / `agent-browser` are dead in the TUI picker** — the
   `_links.TOOLS` list only has `linters` and `entire`, but
   `executor.py` still has install logic for the other two. Cosmetic
   inconsistency, not a bug.
3. **No restore command** — backups are tarballs created next to the
   source dirs. The user must `tar xzf` them manually. Documented in
   the README rewrite.
4. **`~/.codex/tmp/arg0/`** — Codex CLI's own runtime sandbox. Codex
   creates symlink dirs there per invocation; if a process dies
   uncleanly they linger. **Safe to delete; Codex recreates on demand.**

## Final deliverable

A single `REPORT_<YYYY-MM-DD-HHMM>.md` next to the template, completely
filled in.

Then end your session. The user will read the report and decide what to
act on. Do NOT run `git commit` / `git push`. Do NOT modify any source
files outside this `code_review_claude_code_hpc_27_04_2026/` directory.
