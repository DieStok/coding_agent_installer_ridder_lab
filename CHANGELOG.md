# Changelog

## Unreleased

### Breaking changes

- **`CODING_AGENTS_NO_WRAP=1` no longer skips the SIF.** The env var
  previously exec'd the host npm-installed binary directly, bypassing
  every layer of sandboxing. It now goes through `apptainer exec
  --containall --no-mount home,tmp <sif> <agent>` — still bypasses the
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
