# Coding-agents HPC Diagnostic Report

**Date:** YYYY-MM-DD HH:MM
**Operator:** (your username on the HPC)
**Cluster node:** (login or compute, hostname)
**Repo HEAD:** (output of `git log -1 --oneline`)
**Wrapper template version markers** (from script 05): ...

## Top-line summary

| Area | Status | Notes |
|---|---|---|
| `coding-agents doctor` (script 01) | PASS / WARN / FAIL | row count, any WARN/FAIL detail |
| Per-agent `--version` (script 02) | | |
| Pi interactive load + extensions (script 03) | | |
| Apptainer flag probes (script 04) | | |
| Wrapper template inspection (script 05) | | |
| Audit logs (script 06) | | |
| OpenCode path-shim (script 07) | | |
| Cwd-policy behavior (script 08) | | |
| Stale runtime residue (script 09) | | |
| Host node/npm dependency (script 10) | | |
| VSCode sidebars end-to-end | TESTED / NOT-TESTABLE-IN-SESSION | |

## Section 1 — `coding-agents doctor`

(quote the doctor table here)

**Anomalies and 5-whys:** none / list

## Section 2 — Per-agent `--version` smoke

For each of `agent-claude`, `agent-codex`, `agent-opencode`, `agent-pi`:

```
$ agent-<name> --version
<verbatim output>
```

**Was apptainer actually invoked?**  yes / no / unclear (paste `ps -ef | grep apptainer` or audit-log entry)
**Cwd-policy line shown?**  yes / no
**Any residual `WARNING:` lines?**  none / quote them

## Section 3 — Pi interactive + extensions

```
$ agent-pi
<verbatim output up to and including the [Extensions] block>
```

Expected: `pi-ask-user pi-mcp-adapter pi-subagents pi-web-access` all listed.

If failure: 5-whys chain.

## Section 4 — Apptainer flag probes

For each probe in `04_apptainer_probes.sh`, paste the command and the
first ~10 lines of output. Confirm:

- HOME inside SIF resolves to host's HOME path.
- `--writable-tmpfs` overlay does NOT serve `/tmp` (host tmp is mounted).
- `--no-privs` is OK with our agent set.

## Section 5 — Wrapper template inspection

```
$ grep -E "no-mount|--env|APPTAINERENV|writable-tmpfs|no-privs" \
        /hpc/compgen/users/$USER/coding_agents/bin/agent-claude
```

Expected: `--no-mount home`, `--env "HOME=$HOME"`, `--writable-tmpfs`,
`--no-privs`, NO `APPTAINERENV_HOME` exports, NO `--no-mount home,tmp`.

## Section 6 — Audit logs

```
$ ls -la ~/agent-logs/
$ tail -3 ~/agent-logs/claude-$(date -I).jsonl 2>/dev/null
```

For each agent that was invoked in section 2: a JSONL entry should exist.
Note any agent that did NOT produce an audit log entry.

## Section 7 — OpenCode path-shim resolution

```
$ which opencode
$ readlink -f $(which opencode)
```

The resolved path should end at
`<install_dir>/bin/agent-opencode-vscode`. If it resolves to anything
else, the shell-rc PATH-prefix block is broken or shadowed.

## Section 8 — Cwd-policy behavior

```
# Refusal cases
$ cd /hpc/compgen/users/shared && agent-claude --help; echo "exit=$?"
$ cd /hpc/compgen/projects && agent-claude --help; echo "exit=$?"

# Warn case
$ cd $HOME && agent-claude --help; echo "exit=$?"

# OK case
$ cd /hpc/compgen/projects/<some-proj>/<some-sub>/analysis/$USER && agent-claude --help; echo "exit=$?"
```

Expected: refuse cases exit 12, warn case exits non-error with a yellow
warning line, OK case is silent.

## Section 9 — Stale runtime residue

```
$ ls -la /tmp/pi-*-uid-$(id -u)/ 2>/dev/null
$ ls -la ~/.codex/tmp/arg0/ 2>/dev/null
$ ls -la ~/.coding-agents.json
$ ls -la ${XDG_RUNTIME_DIR:-$HOME/.coding-agents}/vscode-session.json 2>/dev/null
```

Document any file older than the most recent install. If anything is
left over from before commit `215ca9c`, decide whether it could
re-trigger the Pi /tmp issue.

## Section 10 — Host node / npm dependency

```
$ which node && node --version
$ which npm && npm --version
$ ls /hpc/compgen/users/$USER/coding_agents/tools/node_modules/.bin/biome 2>/dev/null
```

After commit `9b87b0b`, host biome should NOT be installed in HPC mode.
If biome IS in `tools/node_modules/.bin/`, the user installed in
`--local` mode OR the install pre-dates `9b87b0b`.

## Section 11 — Open observations

Anything you noticed that doesn't fit the script structure. Stale
config files, weird permissions, unexpected processes, stuff in
`~/agent-logs/` that's older than the install_at timestamp, etc.

## Section 12 — Hypotheses and 5-whys roundup

For each FAIL or WARN you observed, copy the 5-whys chain you
constructed inline above. Cross-reference with the relevant commit
from the bug-fix-context table in the instructions.

## Section 13 — Recommendations

(things the user should consider doing — but you do NOT do them yourself)

- Things to confirm before declaring the install production-ready.
- Things that look brittle and might need more testing.
- Cleanup actions safe to run (e.g. `rm -rf /tmp/pi-*-uid-$(id -u)/`
  if you found stale dirs).
- Things that look like real bugs versus things that are merely
  surprising-but-correct.
