# Changelog

## Unreleased

### Breaking changes

- **`CODING_AGENTS_NO_WRAP=1` no longer skips the SIF.** The env var
  previously exec'd the host npm-installed binary directly, bypassing
  every layer of sandboxing. It now goes through `apptainer exec
  --containall --no-mount home --bind $TMPDIR:/tmp <sif> <agent>` —
  still bypasses the
  wrapper template (cwd policy, audit log, lab binds, SLURM auto-srun)
  for triage, but keeps the SIF's deny rules and `--containall`
  isolation. Requires apptainer on PATH (compute-only on the lab
  cluster). See `docs/vscode_integration.md` "How to bypass". Plan:
  `docs/plans/2026-04-27-003-refactor-no-wrap-via-sif-drop-npm-install-plan.md`.
- **Host node ≥ 18 is no longer required for `coding-agents install`
  in HPC mode.** Codex, OpenCode, and Pi run from the SIF; their
  binaries no longer get npm-installed to `<install_dir>/node_modules/`.
  Host node is still needed for `--local` mode, claude curl install,
  and host tools (ccstatusline, biome, agent-browser).
- **Pi extension wiring moved into the SIF.** The `pi install
  npm:pi-ask-user` (etc.) post_install loop is dropped from the host
  installer. Lab admins must instead bake these extensions into the
  SIF build (see `docs/vscode_integration.md` "SIF-builder
  requirements"). The wrapper template's first-run hook copies a
  SIF-baked `/opt/pi-default-settings.json` into each user's
  `~/.pi/agent/settings.json` on first Pi invocation. Doctor adds a
  **"Pi defaults baked in SIF"** check that warns when the file is
  missing from the SIF.

### Migration

- Existing installs with `<install_dir>/node_modules/` populated keep
  working — the dir is dead weight after this change but not actively
  harmful. `coding-agents uninstall` rmtree's it cleanly.
- Existing users with `~/.pi/agent/settings.json` already populated
  (from the old host post_install) are unaffected — the first-run hook
  is gated on the file's absence.
- New users / fresh installs go straight to the SIF-baked path: faster
  install (no `npm install` step for SIF agents), no host node needed.

### What changed for users (non-breaking)

- New `coding-agents doctor --probe-sif` flag — opt-in slow path that
  runs `apptainer exec SIF <bin> --version` per baked tool, catching
  the case where `%labels` declared a binary but the `%post` install
  step failed silently (e.g., biome missing from a stale SIF). Plain
  `coding-agents doctor` stays snappy and keeps the existing labels
  read.
- New always-on doctor row **"coding-agents CLI matches source"** —
  md5-compares the running uv-tool wheel's `cli.py` against
  `src/coding_agents/cli.py`. Catches the silent regression where
  `git pull` lands new code but the user forgot to `uv tool install
  --reinstall .`. Editable / src installs short-circuit PASS without
  the compare. Released wheels with no co-located source skip the row
  entirely.
- HPC-mode `coding-agents install` now sweeps stale
  `<install_dir>/tools/node_modules/` on every run — left-over biome
  from pre-9b87b0b host installs would otherwise shadow the SIF copy
  on PATH. Local mode is untouched (host node_modules IS the install).
- `safe_symlink` rejects self-loops loudly (`ValueError`) instead of
  producing a broken symlink that ELOOPs on every read. Defensive —
  the 7f7490b fix removed one path that produced this silently; this
  guard covers all current and future callers.
- Docs: README gained a **"Refreshing the CLI after `git pull`"**
  subsection explaining `uv tool install --reinstall .` and why
  `--force` is a silent no-op for source changes (uv's wheel cache
  keys on the project version, which stays at `0.1.0` for in-place
  dev). The doctor "CLI matches source" row surfaces this drift if
  you forget.
- Wrapper-template comment refresh: the `--env HOME=$HOME` block now
  correctly notes that the flag does **not** silence apptainer
  1.4.5+'s "Overriding HOME" warning — the silencer is the stderr
  filter from 687b15d. Pure documentation; no behavioral change.
- Diagnostic scripts in `code_review_claude_code_hpc_27_04_2026/`
  honor `$AGENT_LOGS_DIR` (the wrapper's actual log path) instead of
  hardcoding `$HOME/agent-logs/`, and capture the agent's real exit
  code instead of `head`'s in the cwd-policy probes.
- Doctor row "Node.js >= 18" relaxed to PASS-with-note when the SIF is
  available — clearly says host node isn't required for the wrapped
  flow.
- `coding-agents sync --vscode-settings PATH` flag added for users with
  a custom `remote.SSH.serverInstallPath` whose VSCode-server lives
  outside `~/.vscode-server/`.
- VSCode settings.json resolver now also walks `data/Machine/` paths
  and `.vscode-server/` / `.cursor-server/` subdirs under
  `$VSCODE_AGENT_FOLDER`.
- TUI gained a post-install **next-steps** screen plus a terminal print
  of the same step list (with clickable VSCode marketplace + extension
  install links via OSC-8 hyperlinks).
- Codex hooks emitted as `~/.codex/hooks.json` automatically; OpenCode
  permissions emitted in `~/.config/opencode/opencode.json` with the
  unified `permission` schema (replaces the previous "manual config
  recommended" skip).
