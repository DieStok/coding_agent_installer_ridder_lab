---
title: Fix installer documentation staleness after no-wrap-via-sif
type: fix
status: active
date: 2026-04-27
origin: docs/plans/2026-04-27-003-refactor-no-wrap-via-sif-drop-npm-install-plan.md
---

# Fix installer documentation staleness after no-wrap-via-sif

The no-wrap-via-sif refactor (plan 003) dropped the host npm install for
codex/opencode/pi and moved Pi extension wiring into the SIF. Several
user-facing texts still describe the old world. This plan sweeps the
TUI screens, README, and the two related docs in one pass.

## Acceptance Criteria

- [x] TUI tools screen no longer says "Pi extensions will be auto-installed"
- [x] TUI install-dir screen no longer implies a top-level `node_modules/`
- [ ] README "Installer Walkthrough" matches the actual six-screen TUI
  - step count 7 → 6
  - drop top-level `node_modules/` from install-dir contents
  - Step 3 (VSCode extensions): describe HPC vs local correctly (no toggle on HPC)
  - Step 4 (Tools): default is `linters` only; remove crawl4ai/agent-browser; drop "Pi extensions auto-installed" claim
  - Step 5 (jai Sandbox): section deleted (no jai screen exists)
  - Renumber Skills & Hooks to Step 5; Review & Install to Step 6
- [ ] `docs/vscode_integration.md`: confirm current; no changes if already aligned
- [ ] `docs/requirements.md` Step 4 Pi-extensions table: replace `npm i -g pi-ask-user` instructions with "baked into SIF, see vscode_integration.md §SIF-builder requirements"
- [ ] Tests still green (388/388)

## Context

- TUI fixes already applied in this session: `tools.py:64-69`, `install_dir.py:86`.
- Current TUI step count: `install_dir.TOTAL_STEPS = 6`.
- Default tools: `config.DEFAULT_TOOLS = ["linters"]`.
- Pi extensions baked: `bundled/coding_agent_hpc.def %post` runs the four
  `pi install npm:pi-…` commands; wrapper template's first-run hook
  copies `/opt/pi-default-settings.json` to `~/.pi/agent/settings.json`.

## Sources

- Origin: [`docs/plans/2026-04-27-003-refactor-no-wrap-via-sif-drop-npm-install-plan.md`](2026-04-27-003-refactor-no-wrap-via-sif-drop-npm-install-plan.md)
- Code paths verified live before each edit:
  - `src/coding_agents/installer/screens/install_dir.py:17` (TOTAL_STEPS)
  - `src/coding_agents/config.py:52` (DEFAULT_TOOLS)
  - `src/coding_agents/installer/screens/_links.py:42` (TOOLS list)
  - `src/coding_agents/installer/executor.py:280-303` (npm install skipped)
