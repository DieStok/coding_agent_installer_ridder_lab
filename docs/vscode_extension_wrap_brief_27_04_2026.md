# Brief — VSCode coding-agent extensions: how they invoke their CLIs, and how we wrap them

**Generated:** 2026-04-27
**Companion files attached:**
- The full diagnostic capture: `vscode_extensions_diagnostic_20260427_084046.txt`
- The codebase zip
**Audience:** deep research agent
**Goal:** answer the research questions in §6 in enough detail that a follow-up engineering pass can implement managed wrapping for all four extensions without further reverse-engineering.

---

## 1. Context (what already exists, why this matters)

The `coding-agents` package wraps four CLIs (Claude Code, Codex, OpenCode, Pi) inside an Apptainer SIF for a multi-tenant HPC cluster. The wrapper is `agent-<name>` (e.g. `agent-claude`) and lives at `<install_dir>/bin/`. It enforces:

- a per-job SLURM allocation gate
- `--no-mount home,tmp` Apptainer isolation with explicit per-agent `~/.{claude,codex,pi,opencode}/` bind-mounts (post-Sprint-1.5)
- audit-log JSONL (flock-protected, line-atomic)
- provider-key allowlist + poisonous-name blocklist on `provider.env` and `*_api_key` files
- `$PWD` validation (refuse cwds with `"`/control/newline)
- a lab cwd-policy (refuse `/hpc/compgen/users/shared/*` + bare `/hpc/compgen/projects/<project>/`)

The CLIs invoked from a SLURM-allocated terminal go through `agent-<name>` and are sandboxed correctly. **But the four VSCode extensions invoke their own CLIs out-of-band, bypassing the wrapper entirely.** That defeats the lab's sandboxing intent for any user driving the agents from VSCode (Remote-SSH connected to the cluster login node).

The desired end state: every CLI invocation — whether from a shell or from a VSCode extension — routes through `agent-<name>` so the same isolation, audit log, and cwd policy apply uniformly. This brief is research input for that work.

## 2. What we ran (the diagnostic)

`scripts/diagnose_vscode_extensions.sh` (see codebase zip). Pure read-only bash. It:

1. Searches a fixed set of extension roots (`~/.vscode/extensions`, `~/.vscode-server/extensions`, `~/.cursor/extensions`, …) for the four extensions and dumps `package.json` metadata (activation events, `contributes.configuration` settings the extension exposes, `contributes.commands`, main entry-point JS).
2. Greps the main JS bundle for `child_process.{spawn,exec,execFile,fork}`, references to the four binary names, `process.env.*` reads, and hardcoded `~/.<agent>/` paths.
3. Snapshots currently-running processes matching the four binaries — full argv, cwd, parent PID + parent argv, lsof open files, env (filtered to `[A-Z_]*` to keep PII low).
4. Dumps VSCode user + workspace `settings.json`.
5. Resolves CLI binaries on PATH + reports whether `agent-<name>` wrappers are present.
6. Tails the latest VSCode extension host log.

The capture was taken on the lab's HPC compute node (Rocky 8, Linux 4.18) over a Cursor-Stable Remote-SSH session. The user had Claude Code, ChatGPT/Codex, and OpenCode extensions installed and active (panels open). Pi extension was installed but failed to start with a "couldn't find binary on any path searched" error — that error message itself is not in the diagnostic; we'll need it from the user.

### Diagnostic gotcha (will fix in the script)

§1's "per-extension dump" came back empty for all four extensions because the search-roots list missed the user's custom VSCode-server location: `/hpc/compgen/users/dstoker/Software/cursor_and_vscode_remote_server/.vscode-server/extensions/`. Despite that, §2 (process snapshot) caught the live processes spawned by three of the four extensions, which gave us the most important information anyway. The package.json + settings dump is still missing for all four — the research below should re-derive it from upstream sources (extension marketplace pages, source repos, official docs).

## 3. Per-extension findings from the live process snapshot

### 3.1 Claude Code — `anthropic.claude-code-2.1.120-linux-x64`

**Binary** (245 MB ELF native):
```
/hpc/compgen/users/dstoker/Software/cursor_and_vscode_remote_server/
  .vscode-server/extensions/anthropic.claude-code-2.1.120-linux-x64/
  resources/native-binary/claude
```
Bundled with the extension. The user has a separate `~/.local/bin/claude` (version 2.1.119), which is what the Claude *standalone* CLI uses — but the **extension does not call that one**. It hard-codes the bundled binary's absolute path.

**Spawn argv** (full, captured live):
```
claude --output-format stream-json --verbose --input-format stream-json
       --max-thinking-tokens 31999 --permission-prompt-tool stdio
       --setting-sources=user,project,local --permission-mode acceptEdits
       --debug --debug-to-stderr --enable-auth-status --no-chrome
       --replay-user-messages
```

This tells us a lot:
- IPC: **line-delimited JSON over stdin/stdout** (`--input-format stream-json --output-format stream-json`). The extension writes JSON envelopes to the binary's stdin and reads JSON envelopes from stdout.
- `--permission-prompt-tool stdio` means the extension implements the permission-prompt UI by trapping stdio messages from the binary.
- `--setting-sources=user,project,local` means it reads three sources: user-level `~/.claude/settings.json`, project-level `<workspace>/.claude/settings.json`, and "local" (likely `<workspace>/.claude/settings.local.json` or a child override).
- `--no-chrome` → no terminal UI, headless mode.
- `--replay-user-messages` → the extension can re-send historical user messages on reconnect.

**Parent process:** the VSCode extension host (`bootstrap-fork --type=extensionHost`).

**Selected env vars passed in:**
```
CLAUDE_AGENT_SDK_VERSION=0.2.120        # which SDK the extension speaks
CLAUDE_CODE_ENTRYPOINT=claude-vscode    # tells the binary it's hosted
CLAUDECODE=1
CLAUDE_CODE_SSE_PORT=37386              # Server-Sent Events port — the extension
                                        # also runs an HTTP/SSE server the binary
                                        # connects to. NOT just stdin/stdout.
CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING=true
MCP_CONNECTION_NONBLOCKING=true
```
The `CLAUDE_CODE_SSE_PORT` is critical: the extension uses BOTH stream-JSON over stdio AND an SSE server on a localhost port (37386 in this run). Any wrapping has to preserve both channels.

PATH inside the spawned process **already contains** `/hpc/compgen/users/dstoker/coding_agents/bin:/hpc/compgen/users/dstoker/coding_agents/node_modules/.bin:` — so `agent-claude` IS resolvable by name from inside the extension's spawned process. The extension just doesn't choose to use it.

**Settings hook (from a separate macOS-side run of the diagnostic, where the extension was found):**

The extension exposes (in `package.json`'s `contributes.configuration`):

| Setting | Type | Description (verbatim) |
|---|---|---|
| `claudeCode.claudeProcessWrapper` | string | "Executable path used to launch the Claude process." |
| `claudeCode.environmentVariables` | array of `{name, value}` | "Environment variables to set when launching Claude." |
| `claudeCode.useTerminal` | boolean | "Launch Claude in the terminal instead of the native UI." |
| `claudeCode.allowDangerouslySkipPermissions` | boolean | "Allow bypass permissions mode. Recommended only for sandboxes with no internet access." |
| `claudeCode.respectGitIgnore` | boolean | "Respect .gitignore files when performing file searches." |
| `claudeCode.initialPermissionMode` | enum: default/acceptEdits/plan/bypassPermissions | "Initial permission mode for new conversations." |
| `claudeCode.disableLoginPrompt` | boolean | "When true, never prompt for login/authentication in the extension. Used when authentication is handled externally." |
| `claudeCode.autosave` | boolean | (auto-save before read/write) |
| `claudeCode.preferredLocation` | enum: sidebar/panel | (UI placement) |
| `claudeCode.enableNewConversationShortcut` | boolean | (Cmd-N to start) |

**`claudeCode.claudeProcessWrapper` is the wrapper integration point.** Set it to the absolute path of `agent-claude` and the extension launches Claude through our wrapper. `claudeCode.environmentVariables` lets us inject CLAUDE_CONFIG_DIR, provider keys, etc.

The questions that remain (for §6): does `claudeProcessWrapper` *replace* the binary path, or does it *prefix* it (i.e., is the wrapper called with all the existing argv, or does the wrapper need to invoke the binary itself)? Are the `--output-format stream-json` etc. args passed through unchanged? What about the `CLAUDE_CODE_SSE_PORT` env? See §6.1.

---

### 3.2 ChatGPT / Codex — `openai.chatgpt-26.422.30944-linux-x64`

**Binary** (205 MB native, Rust):
```
/.../extensions/openai.chatgpt-26.422.30944-linux-x64/bin/linux-x86_64/codex
```
Bundled with the extension. **The extension is named `openai.chatgpt` but ships and spawns the `codex` Rust binary** — same codebase as the standalone `codex` CLI. The user has no other `codex` on PATH; only the bundled one runs.

**Spawn argv** (full, captured live):
```
codex app-server --analytics-default-enabled
```

That's it. Two flags. Implications:
- IPC: `app-server` is an RPC subcommand of the codex Rust binary (separate from the `codex` interactive CLI subcommand). The extension talks to a long-lived process.
- We do not yet know the wire protocol. Could be Unix domain socket, named pipe, stdio JSON, or a localhost TCP port. **Question for research §6.2.**

**Parent process:** the VSCode extension host. PID parent = `bootstrap-fork --type=extensionHost`.

**Selected env vars passed in:**
```
DEBUG=release
RUST_LOG=warn
CODEX_INTERNAL_ORIGINATOR_OVERRIDE=codex_vscode
```

The override env var hints at internal origin tracking — the extension tells the binary "you were launched by VSCode, not the standalone CLI". Likely affects telemetry / logging only.

**PATH appended with the extension's `bin/linux-x86_64` dir** so any subprocess `codex` itself spawns can find sibling tools. This is a soft hint that codex shells out to other binaries it bundles.

**State on disk** (lsof captured):
- `~/.codex/logs_2.sqlite` (+ `-shm` + `-wal`) — long-running SQLite log
- `~/.codex/tmp/arg0/codex-arg0DXIRmW/.lock` — process lock files (pattern: `codex-arg0<random>/.lock`)
- Writes to `<vscode-server>/data/logs/<session>/exthost*/remoteexthost.log`

**Setting hooks: unknown.** The diagnostic's §1 didn't dump the package.json for this extension (search-root miss). Research §6.2 should enumerate `contributes.configuration` from the marketplace listing or extension source.

**Critical question:** does ChatGPT extension expose any `chatgpt.codexBinaryPath`, `chatgpt.executable`, or equivalent override? If not — the extension cannot be wrapped via settings, and we'd need to do something more invasive like symlink-replacement or process-shim.

---

### 3.3 OpenCode — `sst-dev.opencode`

**Binary** (NOT bundled — uses PATH lookup):
```
node /hpc/compgen/users/dstoker/coding_agents/node_modules/.bin/opencode --port 21337
       ↓ (this then forks)
/hpc/compgen/users/dstoker/coding_agents/node_modules/opencode-ai/bin/.opencode --port 21337
```

This is the cleanest case. **The OpenCode extension calls `opencode` from PATH** — and the user's `coding-agents install` has put `coding_agents/node_modules/.bin` on PATH via the shell-rc injection. So the extension is *already* using our managed install (just not our `agent-opencode` wrapper).

**Spawn argv:**
```
opencode --port 21337
```

IPC is **HTTP server on a localhost port**, with the port passed in via the env var `_EXTENSION_OPENCODE_PORT=21337`. The extension knows the port up front (it picks it, sets the env var, and tells the CLI which port to listen on via `--port`).

**Selected env vars passed in:**
```
OPENCODE_CALLER=vscode
_EXTENSION_OPENCODE_PORT=21337
```

(Plus the standard set we already pass through in `agent-opencode`: `OPENCODE_CONFIG`, `OPENCODE_CONFIG_DIR`, etc.)

**Setting hooks: unknown.** §1 dump missing. Research §6.3 should find:
- Does OpenCode VSCode extension support `opencode.executable` / `opencode.binaryPath` / equivalent?
- If we set `OPENCODE_CALLER=vscode` and `_EXTENSION_OPENCODE_PORT=...` ourselves and exec `agent-opencode --port $PORT`, does that work? (Probably yes, since the extension only spawns by name and inherits env. Worth verifying.)

---

### 3.4 Pi — `pi0.pi-vscode` — DID NOT START

**Status:** the user reports the extension panel opened, attempted to start, and failed with "couldn't find binary on any of the paths it searched."

**What we don't have yet:**
- The exact error message + the list of paths the extension printed.
- Whether the extension shipped a bundled binary (the other three did, varyingly — Claude+Codex bundled, OpenCode PATH-only).
- Whether the extension respects `pi.executable` / `pi.binaryPath` / similar.

**What we know from the codebase + npm:**
- `pi-coding-agent` is published as `@mariozechner/pi-coding-agent` on npm.
- Binary name once installed: `pi`.
- `pi-mcp-adapter` (separate npm package) handles MCP. We've already configured Pi via `imports: ["claude-code"]` + `toolPrefix: "short"` in `~/.pi/agent/mcp.json` (Sprint 1 Task 1.6).
- The user's PATH inside the extension host includes `coding_agents/node_modules/.bin`, where the npm install would have placed `pi` — but the Pi binary may not have been installed there because of the post-install plugin step (which runs AFTER the npm install).

**Likely causes** (research §6.4 should confirm one):
1. Pi extension searches a hardcoded list (e.g. `~/.local/bin`, `/usr/local/bin`, …) instead of full PATH.
2. Pi extension looks for the binary inside a specific package directory (e.g. `~/.pi/agent/bin/pi` or the npm prefix dir).
3. Pi extension is broken on Linux ARM/x86_64 mismatch or expects an MCP-adapter-shipped binary that's missing.
4. The user simply hasn't installed pi via npm yet; the extension cannot find what isn't there.

**This is the most important extension to research thoroughly** because (a) Pi has the richest plugin/extension ecosystem (pi-ask-user, pi-subagents, pi-web-access, pi-mcp-adapter), and (b) it failed cleanly, which means whatever surface it exposes for binary-path overrides is the most likely-to-be-honoured.

---

### 3.5 Cross-cutting environment observations

- All four extensions inherit `CLAUDE_AGENT_SDK_VERSION` from the VSCode extension host process — which means the host process itself was launched with the Anthropic Agent SDK loaded (the Claude extension activated first, set the env, the VSCode host kept it; subsequently every other extension's spawn inherits it). This is a fingerprint of "Claude was the first extension to wake up" in this session.
- The lab's coding-agents shell-rc injection IS active in the extension host PATH (we see `coding_agents/bin` and `coding_agents/node_modules/.bin` in PATH). So `agent-claude`, `agent-codex`, `agent-opencode`, `agent-pi` ARE resolvable by name from inside the extension host. The Claude+Codex extensions just don't search PATH; they use absolute bundled paths. OpenCode does search PATH and finds the user's install. Pi presumably searches PATH but with some restriction we don't yet understand.
- `AGENT_SECRETS_DIR=/hpc/compgen/users/dstoker/agent-secrets` and `AGENT_LOGS_DIR=/hpc/compgen/users/dstoker/agent-logs` are set in the extension host env — meaning if the extensions DID spawn through `agent-<name>`, the wrapper would correctly pick up secrets/logs paths.

## 4. Existing wrapper integration points (what already works)

The `agent-<name>` wrapper at `<install_dir>/bin/agent-<name>` already:
- Validates SLURM allocation, cwd policy, `$PWD` shape, jq presence, SIF integrity.
- Loads provider.env / *_api_key files into `APPTAINERENV_*`.
- Bind-mounts `~/.claude/`, `~/.codex/`, `~/.pi/agent/`, `~/.config/opencode/` (+ three more OpenCode dirs) writable into the SIF.
- Sets `APPTAINERENV_HOME=$HOME` so paths resolve consistently inside the SIF.
- `exec`s `apptainer exec ... <binary> "$@"`. So if the extension calls `agent-claude --output-format stream-json --verbose ...`, those args propagate through to the real claude binary inside the SIF.

The key implication for VSCode integration: **our wrapper is `argv`-transparent**. Whatever args / stdin / stdout the extension expects, the binary inside the SIF receives them unchanged. The wrapper does not interfere with the protocol.

The key constraint for VSCode integration: **stdio is preserved, but localhost ports require `--net=host`-style network namespace passthrough**. Apptainer 1.4 with `--containall` does NOT create a separate network namespace by default — the SIF process shares the host's localhost. So `CLAUDE_CODE_SSE_PORT=37386` listening on the host should be reachable by the binary inside the SIF, and vice versa. (Research §6.5 should verify this assumption.)

## 5. What would full wrapping look like — design intent

For each extension, we want a one-line *configuration* change that makes the extension launch our `agent-<name>` instead of the bundled binary. The wrapper then exec's into Apptainer, which runs the binary inside the SIF with bind-mounts + audit logging.

The integration would land as a new function in `src/coding_agents/installer/policy_emit.py`, called from `_emit_managed_policy` for `state.mode != "local"`:

```python
def _emit_managed_vscode_settings(install_dir, target_settings_path):
    bin_dir = install_dir / "bin"
    settings = {
        "claudeCode.claudeProcessWrapper": str(bin_dir / "agent-claude"),
        "claudeCode.environmentVariables": [
            {"name": "AGENT_SECRETS_DIR", "value": "..."},
            {"name": "AGENT_LOGS_DIR", "value": "..."},
        ],
        # Codex equivalent — UNKNOWN; needs research §6.2
        # OpenCode equivalent — UNKNOWN; needs research §6.3
        # Pi equivalent — UNKNOWN; needs research §6.4
    }
    merge_settings.merge_json_section(target_settings_path, "...", settings)
```

The settings file path itself differs per VSCode variant. Stable VSCode on Linux uses `~/.config/Code/User/settings.json`; Cursor uses `~/.config/Cursor/User/settings.json`; **the lab's custom remote-server install puts it at `/hpc/compgen/users/dstoker/Software/cursor_and_vscode_remote_server/.vscode-server/data/User/settings.json`**, which is outside any of the standard search roots. The installer should accept an explicit override.

## 6. Research questions (please answer in great detail)

Each section below frames a focused question. Cite primary sources (extension source repo, official docs, marketplace listing JSON, observed binary `--help` output) where possible.

### 6.1 Claude Code (`anthropic.claude-code`)

1. **Semantics of `claudeCode.claudeProcessWrapper`**: when the user sets this to e.g. `/usr/local/bin/agent-claude`, does the extension:
   - (a) `spawn(processWrapper, [<all-the-args-that-would-have-gone-to-claude>])`? I.e., the wrapper just gets the args and is responsible for finding/exec'ing claude?
   - (b) `spawn(processWrapper, [<bundled-claude-path>, ...args])`? I.e., wrapper is invoked with claude's path as argv[0]?
   - (c) Something else?
2. **Argv contract**: confirm the full argv list (the diagnostic captured 11 flags but the extension may pass more in some flows). Are there flags that are *only* set conditionally? Where are the args defined in the extension source?
3. **Environment contract**: confirm the full set of env vars the extension passes. Specifically:
   - Does `CLAUDE_CODE_SSE_PORT` need to reach a port the VSCode extension host is listening on? If so, must that port be reachable from inside the SIF? (Apptainer with `--containall` shares the host network namespace by default, so this should work — but please confirm.)
   - Does `CLAUDE_AGENT_SDK_VERSION` need to match anything specific? Or is it informational?
4. **Settings reference**: dump the *complete* `contributes.configuration` from `package.json`. Are there any settings beyond the 10 in §3.1 that are relevant to launching / sandboxing / authentication?
5. **`disableLoginPrompt`**: when this is `true`, how does the extension obtain auth? Does it read `~/.claude/.credentials.json` directly? Via the SDK? Via `claude /login` CLI? Important for our wrapper because we already bind-mount `~/.claude/`.
6. **Permission-prompt-tool stdio**: how does the stdio permission prompt flow work? The extension presumably injects JSON messages into the binary's stdin to grant/deny permissions. Does our wrapper preserve this if we just `exec apptainer exec ... claude`? I.e., does Apptainer pass stdin through transparently?
7. **Source of truth**: link to the public source repo (or marketplace .vsix download URL) so we can grep the JS for `process.env`, `child_process`, and the exact wrapper-resolution logic.

### 6.2 ChatGPT/Codex (`openai.chatgpt`)

1. **Binary-path override**: does the extension expose any setting (e.g. `chatgpt.codexExecutable`, `chatgpt.codexPath`, `chatgpt.binaryPath`, `openai.codex.executable`, …) that lets the user point at a custom binary? Dump the full `contributes.configuration`. **This is the make-or-break question for Codex wrapping.**
2. **`app-server` protocol**: what wire protocol does `codex app-server` speak? Sub-questions:
   - Stdio JSON-RPC? Localhost TCP port (which port and how is it discovered)? Unix domain socket? gRPC?
   - Where is the protocol documented? `codex app-server --help` should give a hint; is there a published `proto` file or schema?
   - If it's a localhost port, where is the port number communicated to the extension? (Stdout? Env? File in `~/.codex/`?)
3. **Lifecycle**: is `codex app-server` a long-running daemon (one per VSCode session) or per-conversation? If long-running, killing/replacing it cleanly matters for the wrapper.
4. **`CODEX_INTERNAL_ORIGINATOR_OVERRIDE=codex_vscode`**: where is this consumed? Telemetry only, or does it affect behaviour? Does our wrapper need to set/preserve it?
5. **Auth**: how does the extension authenticate? OAuth via `~/.codex/auth.json` (the file we already bind-mount)? An env var (`OPENAI_API_KEY`)? Both, with fallback?
6. **Source of truth**: extension is closed-source (OpenAI), but we can:
   - Read the `package.json` from the installed `.vsix` / extension dir.
   - Read the bundled JS bundle (it's a Node.js extension; the bundle is grep-able for `process.env`, `spawn`, etc.).
   - Read the codex Rust source at `https://github.com/openai/codex` (specifically the `codex-rs` crate's `app-server` subcommand).
   The diagnostic-capture file has the install path; pull the package.json from there.

### 6.3 OpenCode (`sst-dev.opencode`)

1. **Binary-path override**: does `sst-dev.opencode` expose any binary-path setting? Or does it only respect PATH lookup?
2. **`_EXTENSION_OPENCODE_PORT` semantics**: who picks the port — extension or CLI? If extension, how is it communicated to the CLI (env var only, or also a settings entry)? If CLI, how does it report the picked port back to the extension?
3. **`OPENCODE_CALLER=vscode`**: where is this consumed? Behavioural difference vs `OPENCODE_CALLER` unset? Documented?
4. **Protocol over the port**: HTTP REST? WebSocket? Server-Sent Events? Where is the API documented?
5. **The two-process pattern** (`node .../node_modules/.bin/opencode` forks `.../node_modules/opencode-ai/bin/.opencode`): is the first a thin wrapper / launcher? If we wrap with `agent-opencode`, do we replace one or both?
6. **Source of truth**: OpenCode is open source at `https://github.com/sst/opencode`; the extension lives at `packages/opencode-vscode-extension/` (or similar). We have a local clone at `local_clones/opencode/`.

### 6.4 Pi (`pi0.pi-vscode`) — top priority

1. **Why didn't Pi find its binary?** What paths does the extension search? Is it:
   - The full PATH env var?
   - A hardcoded list (`~/.local/bin`, `/usr/local/bin`, `/usr/bin`)?
   - A `pi-vscode.executable` setting?
   - An npm-resolved binary inside the extension's own `node_modules/`?
   The user got an error message with the list of searched paths — request that error from them if needed (it's the most efficient way to answer this question).
2. **Binary-path override**: does the extension expose a setting like `pi-vscode.executable` / `pi0.pi-vscode.path` / equivalent?
3. **Spawn argv**: what does the extension call `pi` with when it does start? (We don't have a captured spawn since Pi never ran.) Probably some `pi` subcommand analogous to Claude's `--input-format stream-json` or Codex's `app-server`. Dump from extension source.
4. **State requirements**: confirm that Pi extension reads/writes `~/.pi/agent/` (we already bind-mount this). Any additional state dirs (e.g. `~/.config/pi/`)?
5. **Source of truth**: Pi is open source at `https://github.com/mariozechner/pi-mono` (we have a local clone at `local_clones/pi-mono/`). The VSCode extension is at `packages/pi-vscode/` or similar.

### 6.5 Cross-cutting

1. **Localhost-port reachability inside Apptainer SIF**: confirm that with `--containall --no-mount home,tmp --writable-tmpfs --no-privs`, processes inside the SIF can reach localhost ports the host listens on (and vice versa). The Claude SSE port and the OpenCode HTTP port both depend on this. Cite the Apptainer 1.4 documentation. (Apptainer typically does NOT create a network namespace unless you pass `--net`, but please confirm.)
2. **Stdio passthrough through `apptainer exec`**: when we `exec apptainer exec ... <binary>`, does `<binary>` inside the SIF receive stdin/stdout/stderr from the original parent (the VSCode extension host)? This must work for Claude's `--input-format stream-json` and Codex's `app-server` protocols. Cite Apptainer docs.
3. **Binary-shim alternatives**: if any extension turns out to NOT respect a binary-path setting, the fallback is to symlink/shim the bundled binary. What's the cleanest pattern? Options:
   - (a) Replace `<extension>/bin/<arch>/<binary>` with a symlink to `agent-<name>`. Risk: extension auto-updates may overwrite.
   - (b) Mount a tmpfs over the bundled-binary file with our wrapper. Risk: requires extension to re-spawn after we mount; may not survive VSCode restart.
   - (c) Hook the extension host's `child_process.spawn` via a vscode-extension-side plugin. Risk: invasive; may violate extension marketplace terms.
   - (d) Use `LD_PRELOAD` to intercept the bundled binary's `execve`. Risk: complex; macOS has SIP that blocks this.
   Discuss the tradeoffs.
4. **Settings file location for the lab's custom VSCode-server install**: standard search-roots miss `/hpc/compgen/users/dstoker/Software/cursor_and_vscode_remote_server/.vscode-server/data/User/settings.json`. Is there an env var or convention we can use to discover the right path automatically? `VSCODE_AGENT_FOLDER=/hpc/compgen/users/dstoker/Software/cursor_and_vscode_remote_server/.vscode-server` is set in the extension host env — that gives us the agent folder; settings live at `<agent>/data/User/settings.json`. Confirm this convention applies across VSCode / VSCode-Insiders / Cursor / Windsurf / VSCodium.
5. **Multi-extension shared resources**: if we wrap all four, do they fight? Specifically:
   - Each extension wants to manage its own `~/.<agent>/` config; our managed-settings emission also writes there. Ordering?
   - VSCode settings.json is a single shared file. Atomic writes + drift backup are already in place from Sprint 1 Task 1.2 — but the extension itself may also write to settings.json (e.g. ChatGPT writes back its own config on auth). Race / merge conflict?

## 7. Out-of-scope / non-goals

- The standalone CLI invocation flow (terminal `agent-<name>`) is already correct; nothing in the research needs to change for it.
- Extension-side feature parity (e.g. Claude's stream-JSON UI vs OpenCode's HTTP API) — that's the extension's problem, not ours.
- Local-mode (`coding-agents install --local`) is out of scope for SIF wrapping. The extension can call the unwrapped CLI directly.

## 8. What we want back

A research report structured as:
- §6.1–§6.5 answered in detail, with citations.
- A concrete settings-emission table: for each extension, the exact JSON snippet to merge into the user's VSCode `settings.json` to make the extension call `agent-<name>` instead of its bundled binary.
- A list of any extension that fundamentally cannot be wrapped via settings (with the reason and the recommended fallback).
- Any required wrapper-side changes (e.g. "Claude's stream-JSON requires the wrapper to also propagate stdin in a particular mode" — we don't expect any, but flag if you find them).
- A list of tests we should add to verify the wrapping (e.g. "unit-test that `_emit_managed_vscode_settings` writes the four expected keys"; "integration test that opening Claude in VSCode produces an audit-log entry from `agent-claude`").

## 9. Repo state at the time of writing

- Branch: `main` @ `832691c` (or later — pull latest)
- Sprint 1 (MUST-FIX) complete; full suite 169+ tests passing.
- Sprint 1.5 (Claude+Codex bind-mount uniformity) complete.
- The TODO comment in `bundled/templates/wrapper/agent.template.sh` already mentions the future work to relocate `~/.{claude,codex,pi,opencode}` into `<install_dir>/state/<agent>/` via per-agent env vars (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `PI_CODING_AGENT_DIR`, `OPENCODE_CONFIG_DIR`). That relocation would simplify the VSCode integration too — research §6 may want to consider whether to merge the two efforts.

## 10. Minimum acceptance criteria

The research is "done enough" when, for each of the four extensions, we know:

1. ✅ Whether the extension can be wrapped via a settings-only change. **YES / NO.**
2. ✅ If yes: the exact setting key + value type + value to use.
3. ✅ If no: the recommended fallback (binary symlink, LD_PRELOAD, extension fork, …) with risk assessment.
4. ✅ The exact env vars + argv the extension expects, so the wrapper preserves them.
5. ✅ Any additional state directories beyond `~/.<agent>/` that need bind-mounting.

Anything beyond that is bonus.
