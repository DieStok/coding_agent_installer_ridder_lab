# Wrapping four VSCode coding-agent extensions through Apptainer

**Bottom line up front.** Three of the four extensions are wrappable through a single `settings.json` key (`claudeCode.claudeProcessWrapper`, `chatgpt.cliExecutable`, `pi-vscode.path`). **OpenCode is the outlier**: neither the classic `sst-dev.opencode` (which only opens an integrated terminal and runs `opencode` from PATH) nor the closed-source `sst-dev.opencode-v2` (which spawns the binary directly via `child_process.spawn`) exposes a binary-path setting, so OpenCode requires a PATH-prefix fallback strategy that ships its own `opencode` shim earlier on `$PATH` than the npm-installed one. The Apptainer side is benign: `apptainer exec` passes stdin/stdout/stderr through transparently, and with no `--net` flag the container shares the host network namespace so localhost ports work in both directions natively. The implementation lives in `_emit_managed_vscode_settings(install_dir, target_settings_path)` plus a small JSONC merge helper, and ships per-extension wrappers that for Claude/Codex/Pi reuse the existing argv-transparent `agent-<n>` directly, while OpenCode needs an additional `bin/path-shim/opencode` symlink the user prepends to `$PATH` before launching VSCode/Cursor.

This report is organised as the task specifies: per-extension launch mechanism, per-extension wrappability assessment, settings JSON, Apptainer/cluster cross-cutting confirmations, the deliverables (snippet table, wrapper scripts, exec invocations, test checklist, fallbacks), and the implementation plan.

## Part 1 — Per-extension exact launch mechanism

### 1.1 Claude Code (`anthropic.claude-code`)

**Source location.** The extension is closed-source. The bundled JS lives in `<vscode-server>/extensions/anthropic.claude-code-2.1.120-linux-x64/extension/dist/extension.js` with the manifest at `…/package.json`; the spawned binary is the bun-packaged native ELF at `…/resources/native-binary/claude` (245 MB). The internal `CLAUDE_AGENT_SDK_VERSION=0.2.120` env-var leak shows the extension uses the public **Claude Agent SDK**, whose `query()` function spawns the CLI via Node `child_process.spawn(pathToClaudeCodeExecutable, argv, {stdio: ['pipe','pipe','pipe'], env})`. The `pathToClaudeCodeExecutable` field is documented in `anthropics/claude-agent-sdk-typescript#205`, and the Anthropic VSCode extension routes its `claudeCode.claudeProcessWrapper` setting straight into that field (confirmed by error string in `anthropics/claude-code#10491`: `Claude Code native binary not found at ${workspaceFolder}/claudew.bat. Please ensure Claude Code is installed via native installer or specify a valid path with options.pathToClaudeCodeExecutable.`).

**Spawn API.** `child_process.spawn` with `stdio: ['pipe','pipe','pipe']`. No PTY. The SDK calls `fs.existsSync(path)` *before* spawning (`claude-agent-sdk-typescript#205`) — the wrapper path must be a real file with execute bit; PATH lookup is not performed.

**`contributes.configuration` (claudeCode.\* keys).** Confirmed from public issues, the upstream agent-sdk and the docs at `code.claude.com/docs/en/vs-code`:

| Key | Type | Default | Semantics |
|---|---|---|---|
| `claudeCode.claudeProcessWrapper` | string | `""` | Absolute path replacing `argv[0]`. Original argv (`--output-format stream-json …`) is appended verbatim. **No variable substitution** (`#13022`). Existence-checked via `fs.existsSync` (`#205`). |
| `claudeCode.environmentVariables` | array of `{name, value}` | `[]` | Merged into spawned env. **Bug**: deleted from settings on activation in trusted workspaces (`#10217`). |
| `claudeCode.useTerminal` | boolean | `false` | If true, runs `claude` in an integrated VSCode terminal — and **bypasses the wrapper** (`#10500`, `#11647`). |
| `claudeCode.disableLoginPrompt` | boolean | `false` | Suppresses in-pane `/login` modal (`#30132`). |
| `claudeCode.initialPermissionMode` | enum (`default`/`plan`/`acceptEdits`) | `default` | Passed in argv. |

No checksum/signature/auto-update/binary-path setting is present. Any other `claudeCode.*` keys (MCP, plugins, permissions) are not launch-routing relevant.

**Environment variables consumed.** From the live capture and the env-var gist `unkn0wncode/f87295d055dd0f0e8082358a0b5cc467`: the extension sets `CLAUDE_CODE_SSE_PORT=<random>`, `CLAUDE_CODE_ENTRYPOINT=claude-vscode`, `CLAUDECODE=1`, `CLAUDE_AGENT_SDK_VERSION=0.2.120`, `CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING=true`, `MCP_CONNECTION_NONBLOCKING=true`. The CLI also consumes `ANTHROPIC_API_KEY`, `ANTHROPIC_CONFIG_DIR`, `RIPGREP_EMBEDDED=1`, `ENABLE_LSP_TOOL`, `CLAUDE_BASH_NO_PROMPT_IDLE_TIMEOUT_MS`, plus standard `HOME`, `PATH`, `XDG_*`. The wrapper must propagate **all** of these because Apptainer's default behaviour drops most env vars.

**Sidecar processes.** The native binary internally spawns ripgrep (embedded), bash for the bash tool, and any MCP servers configured in `.mcp.json` / `~/.claude/settings.json` (typically via `npx`/`uvx`). It does **not** launch language servers from the extension side. The extension itself does not launch any helper process — only the CLI. The `CLAUDE_CODE_SSE_PORT` HTTP server is hosted by the extension's Node host; the CLI is the **client** that connects out to it (matching the JetBrains analogue in `anthropics/claude-code#16912` and the leaked `bridge/` module description). This means inside the SIF, the CLI needs **outbound** access to host loopback `CLAUDE_CODE_SSE_PORT` — which the default Apptainer netns sharing provides for free.

**State directories.** `~/.claude/.credentials.json`, `~/.claude/.claude.json` (note: separate file at `$HOME` root), `~/.claude/projects/<id>/*.jsonl` (sessions), `~/.claude/settings.json` (user config + hooks), `~/.claude/ide/*.lock` (IDE bridge lockfiles), `~/.claude/plugins/`, `~/.claude/skills/`, `~/.claude/statsig/`. Plus `~/.cache/`, `~/.npm/`, `~/.bun/install/cache/` for MCP-via-npx. No OS keyring on Linux (plain JSON file).

**Authentication.** The credentials file is read by the CLI binary, not the extension. The OAuth flow opens a browser via the extension host (which the user already has working pre-Apptainer); the resulting tokens land in `~/.claude/.credentials.json` and the CLI inside the SIF reads them through the bind-mount.

### 1.2 OpenAI Codex / ChatGPT (`openai.chatgpt`)

**Source location.** Closed-source bundle at `<vscode-server>/extensions/openai.chatgpt-26.422.30944-linux-x64/extension.js`; bundled binary at `…/bin/linux-x86_64/codex` (205 MB Rust). The CLI is open at `github.com/openai/codex`, with the relevant subcommand defined under `codex-rs/app-server/`.

**Spawn API.** Almost certainly `child_process.spawn(cliPath, ['app-server','--analytics-default-enabled'], { stdio: ['pipe','pipe','pipe'], env })` — matches OpenAI's own published example at `developers.openai.com/codex/app-server` which shows `import { spawn } from "node:child_process"` with exactly this argv. No PTY.

**`contributes.configuration` (chatgpt.\* keys).** Pulled from the official docs at `developers.openai.com/codex/ide/settings`:

| Key | Type | Default | Semantics |
|---|---|---|---|
| `chatgpt.cliExecutable` | string | `""` | **Path to codex CLI.** Empty → bundled. Absolute path → spawned verbatim. Marked "development only" but works on Linux (`#9744`, `#14875`). |
| `chatgpt.commentCodeLensEnabled` | boolean | `true` | Show CodeLens above to-do comments. |
| `chatgpt.localeOverride` | string | `""` | UI locale override. |
| `chatgpt.openOnStartup` | boolean | varies | Focus Codex sidebar on startup. |
| `chatgpt.runCodexInWindowsSubsystemForLinux` | boolean | (Windows-only) | Spawn through WSL on Windows. |

Only `chatgpt.cliExecutable` is launch-routing.

**`app-server` IPC protocol.** From `codex-rs/app-server/README.md`: default transport is `stdio://` — newline-delimited JSON-RPC 2.0 with the `"jsonrpc":"2.0"` header omitted on the wire. Other transports (`ws://`, `unix://`) exist but are not used by the VSCode extension (the spawn argv has no `--listen` flag). Handshake is `initialize` → `initialized` → `thread/start` → `turn/start`, with the extension self-identifying as `clientInfo.name = "codex_vscode"` (matching the env `CODEX_INTERNAL_ORIGINATOR_OVERRIDE=codex_vscode`). **This means stdio passthrough through Apptainer is the entire protocol — no sockets, no port binding, no `/tmp/*.sock`.**

**Environment variables consumed.** From `codex-rs/core` and `docs/config.md`: `CODEX_HOME` (overrides `~/.codex`), `CODEX_SQLITE_HOME`, `CODEX_CA_CERTIFICATE`, `CODEX_INTERNAL_ORIGINATOR_OVERRIDE`, `CODEX_API_KEY`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `RUST_LOG`, `LOG_FORMAT`, `DEBUG`, `TMPDIR`, `XDG_CONFIG_HOME`. The wrapper must explicitly propagate these.

**Sidecar processes.** From upstream issues (`#43`, `#1205`, `#13542`, `#19271`): the codex binary expects `rg` (ripgrep), `bash`, `git`, optionally `bwrap` for inner sandboxing, and `apply_patch`/`codex-linux-sandbox`/`codex-execve-wrapper` self-supplied via the arg0-dispatch trick from `~/.codex/tmp/arg0/codex-arg0XXX/`. The arg0 trick is implemented in `codex-rs/arg0/src/lib.rs:246-273` (verified): it creates `~/.codex/tmp/arg0/`, makes a per-run temp dir under it via `tempfile::Builder::new().prefix("codex-arg0").tempdir_in(...)`, and creates a `.lock` file via `fcntl::flock`. The temp dir is then prepended to the inner shell's PATH so child shells can invoke `apply_patch` directly. **Critical**: `~/.codex/tmp/` must be writable inside the SIF.

**State directories.** `~/.codex/auth.json`, `~/.codex/config.toml`, `~/.codex/logs_2.sqlite{,-shm,-wal}`, `~/.codex/tmp/arg0/codex-arg0<RAND>/`, `~/.codex/sessions/`, `~/.codex/history.jsonl`. All owned by the Rust binary, not the extension JS.

**Authentication.** `auth.json` is owned by the codex binary (per `developers.openai.com/codex/auth`); the extension shells out to `codex login` for first-time setup. OS keyring is optional via `auth.preferred_auth_method = "keyring"|"file"|"auto"` in `config.toml` (default `file` is what we want — bind-mountable).

### 1.3 OpenCode (`sst-dev.opencode`)

**Critical disambiguation.** Two extensions exist on the marketplace under the same publisher:

- **`sst-dev.opencode`** (the classic, ~352k installs) — a *thin terminal launcher*. Source in the monorepo at `github.com/sst/opencode/tree/dev/sdks/vscode/`. The spawn is `vscode.window.createTerminal({...})` followed by `terminal.sendText("opencode")` (issue `sst/opencode#2220` references `sdks/vscode/src/extension.ts#L60`). It does **not** start a server, does **not** pass `--port`, does **not** set `OPENCODE_CALLER`, and inherits the integrated terminal's full env from the user shell.
- **`sst-dev.opencode-v2`** (Beta, ~15k installs) — a sidebar-chat panel extension that **does** spawn `opencode` headlessly via `child_process.spawn` with `--port <random>` and sets `OPENCODE_CALLER=vscode` and `_EXTENSION_OPENCODE_PORT=<port>`. The source was previously in `sdks/vscode-v2/` but **has been removed from the public repo** (issue `sst/opencode#13501` is the open ticket complaining about this); only the bundled `dist/extension.js` inside the installed `.vsix` remains. Issue `#6066` cites the decompiled bundle at `~/.vscode/extensions/sst-dev.opencode-v2-0.1.1/dist/extension.js`.

The user's live capture (`node /hpc/.../node_modules/.bin/opencode --port 21337` with `OPENCODE_CALLER=vscode`, `_EXTENSION_OPENCODE_PORT=21337`) **matches v2's behaviour, not classic's**. Whichever extension is installed must be confirmed via `code --list-extensions | grep opencode` on the HPC host. **The implementation must handle both cases** because the user has stated the live capture is real.

**`contributes.configuration` (classic).** The classic extension's `package.json` has **no `contributes.configuration` block at all**. Only commands (`opencode.openTerminal`, `opencode.openNewTerminal`, `opencode.addFilepathToTerminal`), keybindings, and a single editor-title menu entry. **No binary-path setting exists.**

**`contributes.configuration` (Beta v2).** The marketplace README does not document any user-facing settings beyond model selection and chat session list. The decompiled bundle (`#6066`) shows `loadOpenCodeConfig()` reads `~/.opencode/auth.json`, `~/.local/share/opencode/auth.json`, `~/.config/opencode/auth.json` — but no `opencode.binaryPath`/`opencode.executable` setting is referenced. **No binary-path setting exists in v2 either.**

**Spawn API.** Classic: `vscode.window.createTerminal({...}); terminal.sendText("opencode")`. Beta v2: `child_process.spawn("opencode", ["--port", String(port), ...])` with `env: { ...process.env, OPENCODE_CALLER: "vscode", _EXTENSION_OPENCODE_PORT: String(port) }` — inferred from issue `sst/opencode#18792` which shows the analogous SDK pattern `spawn opencode … serve --hostname=127.0.0.1 --port=0`. PATH-based binary lookup confirmed by the live capture resolving to `node_modules/.bin/opencode`.

**Two-layer launch.** The npm package `opencode-ai` ships a JS shim (`bin/opencode`) that re-execs the platform-native Go binary at `node_modules/opencode-ai/bin/.opencode`. So spawning `opencode` triggers `node node_modules/.bin/opencode → .opencode` (Go). The wrapper must intercept at the outer `opencode` PATH-lookup layer.

**HTTP IPC.** The Go binary exposes a Hono REST + SSE API. Routes documented in `packages/sdk/openapi.json`: `GET /` (server info), `GET /event` (SSE stream), `POST /session`, `GET /session`, `POST /session/{id}/message`, `GET /file/*`, `POST /tui/...`. No WebSocket. No Host-header check; CORS configurable in `opencode.json`. **No auth on the local HTTP API by default** — anyone with loopback access can hit it. Reachability through Apptainer is fine because the host netns is shared.

**Environment variables consumed.** `OPENCODE_CALLER` is a soft hint (telemetry/UX). `_EXTENSION_OPENCODE_PORT` is consumed by extension-side webview and by JS plugins, not by the Go binary itself. `OPENCODE_INSTALL_DIR`, `OPENCODE_HOST`, `OPENCODE_SKIP_START`, `OPENCODE_CONFIG`. Standard `XDG_*`, `HOME`, `PATH`.

**Sidecars.** `bun` runtime (embedded in opencode for the JS-plugin runtime), user-installed LSPs (gopls, typescript-language-server, clangd, pyright), MCP servers per `~/.config/opencode/opencode.json`, `bash`/`/bin/sh` for the bash tool, `git`. All spawned **inside** the SIF if our wrapper covers the outer `opencode` process — Apptainer's PID namespace keeps descendants in.

**State directories.** `~/.config/opencode/auth.json`, `~/.config/opencode/opencode.json`, `~/.local/share/opencode/sessions.db` (Drizzle ORM), `~/.local/share/opencode/<project>/`, `~/.cache/opencode/node_modules/` (bun-installed plugins), and per-project `.opencode/`.

### 1.4 Pi (`pi0.pi-vscode`)

**Repo identification.** The extension is at **`github.com/pithings/pi-vscode`** (the `pi0` GitHub user is the author's old handle; the repo redirected to `pithings/`). The CLI it spawns (`@mariozechner/pi-coding-agent`) lives in `github.com/badlogic/pi-mono` (the `mariozechner` npm scope is owned by the `badlogic` GitHub account). The task brief's `mariozechner/pi-mono` lookup will redirect.

**Source location.** `src/extension.ts` registers commands; `src/terminal.ts` (94 lines, main branch) is the spawn site; `src/pi.ts` contains the binary-detection helper `ensurePiBinary()`.

**Spawn API.** **`vscode.window.createTerminal({ shellPath: piPath, shellArgs, env, cwd, isTransient: true })`** — i.e. a VSCode integrated PTY terminal, not `child_process.spawn`. From `src/terminal.ts`:

```ts
const piPath = await ensurePiBinary();
const shellArgs = createPiShellArgs(options.extensionUri, { extraArgs, contextLines });
const baseEnv = createPiEnvironment(options.bridgeConfig);
const env = options.terminalId ? { ...baseEnv, PI_VSCODE_TERMINAL_ID: options.terminalId } : baseEnv;
const terminal = vscode.window.createTerminal({
  name: TERMINAL_TITLE, shellPath: piPath,
  shellArgs: shellArgs.length > 0 ? shellArgs : undefined,
  location: { viewColumn }, isTransient: true, cwd, env,
});
```

VSCode spawns `shellPath` directly via `node-pty` in the terminal host; **the user shell is not in the loop**, so a PATH prefix in `~/.bashrc` would not work. The setting `pi-vscode.path` is the only override surface.

**Binary detection (`ensurePiBinary`).** Order: (1) read `pi-vscode.path` setting; if non-empty and existing, use it; (2) probe a hardcoded list of common install dirs (`~/.bun/bin/pi`, `~/.local/bin/pi`, `~/.npm-global/bin/pi`); (3) `which pi` / PATH walk on POSIX; on Windows, auto-probe `.cmd`/`.exe`/`.ps1` extensions. If none resolve, the user-observed error "couldn't find binary on any of the paths it searched" is shown.

**Settings.** Only one user-facing setting:

| Key | Type | Default | Semantics |
|---|---|---|---|
| `pi-vscode.path` | string | `""` | Absolute path to pi executable. Highest precedence. **The wrapper hook.** |

No env / extraArgs / cwd / sandbox / login settings are exposed.

**Environment variables consumed.** Extension injects `PI_VSCODE_BRIDGE_URL` (extension-hosted HTTP bridge), `PI_VSCODE_BRIDGE_TOKEN` (bearer auth for bridge), `PI_VSCODE_TERMINAL_ID`. The CLI consumes `PI_PACKAGE_DIR`, `PI_SMOL_MODEL`, `PI_SLOW_MODEL`, `PI_PLAN_MODEL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_CLOUD_PROJECT[_ID]`, `GOOGLE_CLOUD_API_KEY`.

**IPC.** Two channels: (1) PTY stdin/stdout (terminal interactive use); (2) HTTP bridge — extension hosts a localhost server with bearer-token auth, the bundled "pi-side extension" inside the CLI calls `vscode_*` tools (get_selection, get_diagnostics, apply_workspace_edit, etc.). For the `@pi` chat participant, pi runs in **`pi --rpc`** mode (LF-delimited JSONL over stdio, strict framing per pi-mono README).

**Sidecars.** No standalone LSPs or daemons. Pi can spawn bash, optionally Puppeteer-controlled Chromium, and a second `pi --rpc` instance for chat. Bridge HTTP runs in extension host, not as a separate binary.

**State directories.** `~/.pi/agent/auth.json`, `~/.pi/agent/models.json`, `~/.pi/agent/sessions/`, `~/.pi/packages/` (auto-loaded plugins), `~/.pi/extensions/`, `~/.pi/skills/`, `~/.pi/prompts/`, `~/.pi/themes/`. Plus the **bundled pi-side-extension that the CLI loads from the VSCode extension's install dir** (`<vscode-server>/extensions/pi0.pi-vscode-*/...`) — this dir must be readable inside the SIF.

## Part 2 — Per-extension wrappability assessment

| Concern | Claude | Codex | OpenCode (classic) | OpenCode (v2) | Pi |
|---|---|---|---|---|---|
| Settings-only override | **YES** (`claudeProcessWrapper`, conditional on `useTerminal=false`) | **YES** (`chatgpt.cliExecutable`) | **NO** (no settings at all) | **NO** | **YES** (`pi-vscode.path`) |
| Stdio passthrough survives wrapper | YES (pipes; `apptainer exec` passes through) | YES (pipes; JSON-RPC framing intact) | N/A (HTTP IPC) | N/A (HTTP IPC) | YES with PTY (createTerminal); RPC mode needs raw pipes |
| Localhost ports survive wrapper | YES (default netns shared; CLI connects out to `CLAUDE_CODE_SSE_PORT`) | N/A (stdio) | YES (terminal-spawned binary on host loopback) | YES (CLI binds 127.0.0.1:21337, host extension connects) | YES (CLI connects out to `PI_VSCODE_BRIDGE_URL`) |
| All required state reachable | YES with `~/.claude` + `~/.cache` + `~/.bun` + `~/.npm` binds; `~/.claude.json` is a separate file | YES with `~/.codex` bind (covers auth, sqlite, tmp/arg0); needs `/tmp` writable | YES with `~/.config/opencode` + `~/.local/share/opencode` + `~/.cache/opencode` | Same as classic | YES with `~/.pi` + extension-install-dir read-only bind |
| Binary checksum/signature | None observed | None observed (version handshake is on protocol, not binary hash) | None | None | None |
| Auto-update behaviour | Extension updates replace bundled binary path; wrapper external to extension dir survives. **Bug**: `environmentVariables` deleted on activation in trusted ws (`#10217`) | Extension updates replace bundled binary; wrapper that resolves bundled binary dynamically stays in sync | Extension does not auto-install opencode | Same | Extension does not auto-install pi |

**Verdicts.** Claude Code and Codex are clean settings-only wrappable on Linux. Pi is settings-only wrappable. OpenCode (either flavour) requires PATH-prefix injection.

**Source citations for verdicts**: Claude — `anthropic/claude-code#10491` (binary-not-found error string proves `claudeProcessWrapper` is plumbed into SDK's `pathToClaudeCodeExecutable`), `#10500`/`#11647` (wrapper bypass when `useTerminal=true`), `#13022` (no variable substitution), `#10217` (env-vars deletion bug), `claude-agent-sdk-typescript#205` (`existsSync` gate). Codex — `developers.openai.com/codex/ide/settings` (cliExecutable docs), `openai/codex#9744` (cliExecutable on Windows), `#14875` (cliExecutable on Linux/WSL), `codex-rs/app-server/README.md` (stdio JSON-RPC). OpenCode — `sst/opencode/sdks/vscode/package.json` (no contributes.configuration), `#13501` (v2 source removed), `#6066` (auth.json reader path). Pi — `pithings/pi-vscode/src/terminal.ts` (createTerminal call), `pithings/pi-vscode/src/pi.ts` (ensurePiBinary auto-detect order), README for `pi-vscode.path`.

## Part 3 — Concrete settings-emission JSON for each extension

### 3.1 Settings-snippet table

| Agent | Settings.json key | Type | Semantics | Sample value | Additional env-var settings | Fallback if primary key absent |
|---|---|---|---|---|---|---|
| Claude | `claudeCode.claudeProcessWrapper` | string | Replaces argv[0]; original argv appended | `<install_dir>/bin/agent-claude` | `claudeCode.useTerminal: false`, `claudeCode.disableLoginPrompt: true` | None viable other than tmpfs-over-binary or symlink-replace |
| Codex | `chatgpt.cliExecutable` | string | Path to codex binary (replaces `argv[0]`, codex argv `app-server …` appended) | `<install_dir>/bin/agent-codex` | (none required; wrapper handles env) | Symlink replace bundled binary with wrapper (risk: extension auto-update overwrites) |
| OpenCode | none | n/a | n/a | n/a | (set `terminal.integrated.env.linux.PATH` prefix; require user to launch VSCode/Cursor with PATH-prefixed wrapper dir) | PATH-prefix shim is the primary strategy, not a fallback |
| Pi | `pi-vscode.path` | string | Path to pi executable (used as `shellPath` in createTerminal) | `<install_dir>/bin/agent-pi` | (none) | Drop symlink at `~/.local/bin/pi` (second-priority auto-detect path) |

### 3.2 Concrete `settings.json` block emitted by `_emit_managed_vscode_settings`

```jsonc
{
  // Claude Code — anthropic.claude-code
  "claudeCode.claudeProcessWrapper": "<install_dir>/bin/agent-claude",
  "claudeCode.useTerminal": false,
  "claudeCode.disableLoginPrompt": true,
  "claudeCode.initialPermissionMode": "acceptEdits",
  "claudeCode.environmentVariables": [
    { "name": "CLAUDE_CODE_ENTRYPOINT", "value": "claude-vscode" }
  ],

  // OpenAI Codex — openai.chatgpt
  "chatgpt.cliExecutable": "<install_dir>/bin/agent-codex",
  "chatgpt.openOnStartup": false,

  // OpenCode — sst-dev.opencode / sst-dev.opencode-v2
  // No binary-path setting exists. Best-effort PATH prefix for terminal-spawned
  // and (when VSCode/Cursor is launched with this PATH prefix) extension-host-spawned binaries.
  "terminal.integrated.env.linux": {
    "PATH": "<install_dir>/bin/path-shim:${env:PATH}"
  },

  // Pi — pi0.pi-vscode
  "pi-vscode.path": "<install_dir>/bin/agent-pi"
}
```

### 3.3 Per-extension wrapper-script template

The existing argv-transparent `agent-<n>` is **almost sufficient for all four**, but each agent needs targeted modifications to (a) explicitly forward extension-set env vars that Apptainer would otherwise drop and (b) bind-mount the agent-specific state dir. Recommended approach: keep `agent-<n>` unchanged for terminal CLI use, and add a thin per-extension shim `agent-<n>-vscode` that the settings.json points at; the shim sets the right env-passthrough flags and then exec's `agent-<n> "$@"`. Reasoning: the existing `agent-<n>` already has the tested SLURM-gating and audit-log emission; the VSCode shim only adds env-passthrough.

**`<install_dir>/bin/agent-claude-vscode`** (new):

```bash
#!/usr/bin/env bash
# Routes anthropic.claude-code's `claude` spawn through agent-claude (Apptainer SIF).
# Preserves CLAUDE_CODE_SSE_PORT and other extension-host env vars that Apptainer's
# default --containall would otherwise scrub.
set -euo pipefail
export APPTAINERENV_CLAUDE_CODE_SSE_PORT="${CLAUDE_CODE_SSE_PORT:-}"
export APPTAINERENV_CLAUDE_CODE_ENTRYPOINT="${CLAUDE_CODE_ENTRYPOINT:-claude-vscode}"
export APPTAINERENV_CLAUDECODE="${CLAUDECODE:-1}"
export APPTAINERENV_CLAUDE_AGENT_SDK_VERSION="${CLAUDE_AGENT_SDK_VERSION:-}"
export APPTAINERENV_CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING="${CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING:-true}"
export APPTAINERENV_MCP_CONNECTION_NONBLOCKING="${MCP_CONNECTION_NONBLOCKING:-true}"
export APPTAINERENV_ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"
exec "$(dirname "$0")/agent-claude" "$@"
```

**`<install_dir>/bin/agent-codex-vscode`** (new):

```bash
#!/usr/bin/env bash
set -euo pipefail
export APPTAINERENV_CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
export APPTAINERENV_CODEX_INTERNAL_ORIGINATOR_OVERRIDE="${CODEX_INTERNAL_ORIGINATOR_OVERRIDE:-codex_vscode}"
export APPTAINERENV_RUST_LOG="${RUST_LOG:-warn}"
export APPTAINERENV_DEBUG="${DEBUG:-release}"
export APPTAINERENV_OPENAI_API_KEY="${OPENAI_API_KEY:-}"
export APPTAINERENV_OPENAI_BASE_URL="${OPENAI_BASE_URL:-}"
export APPTAINERENV_CODEX_API_KEY="${CODEX_API_KEY:-}"
export APPTAINERENV_CODEX_CA_CERTIFICATE="${CODEX_CA_CERTIFICATE:-}"
export APPTAINERENV_CODEX_SQLITE_HOME="${CODEX_SQLITE_HOME:-}"
exec "$(dirname "$0")/agent-codex" "$@"
```

**`<install_dir>/bin/path-shim/opencode`** (new — symlink/script for PATH-prefix):

```bash
#!/usr/bin/env bash
# Resolves before the npm-installed opencode on PATH.
# Forwards the extension-set env vars (OPENCODE_CALLER, _EXTENSION_OPENCODE_PORT)
# that the v2 extension's spawn relies on for handshake.
set -euo pipefail
export APPTAINERENV_OPENCODE_CALLER="${OPENCODE_CALLER:-}"
export APPTAINERENV__EXTENSION_OPENCODE_PORT="${_EXTENSION_OPENCODE_PORT:-}"
export APPTAINERENV_OPENCODE_CONFIG="${OPENCODE_CONFIG:-}"
export APPTAINERENV_ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"
export APPTAINERENV_OPENAI_API_KEY="${OPENAI_API_KEY:-}"
exec "$(dirname "$(dirname "$0")")/agent-opencode" "$@"
```

**`<install_dir>/bin/agent-pi-vscode`** (new):

```bash
#!/usr/bin/env bash
set -euo pipefail
# Pi spawns via createTerminal, so the wrapper must keep PTY semantics.
# Bridge HTTP env must reach the CLI inside the SIF.
export APPTAINERENV_PI_VSCODE_BRIDGE_URL="${PI_VSCODE_BRIDGE_URL:-}"
export APPTAINERENV_PI_VSCODE_BRIDGE_TOKEN="${PI_VSCODE_BRIDGE_TOKEN:-}"
export APPTAINERENV_PI_VSCODE_TERMINAL_ID="${PI_VSCODE_TERMINAL_ID:-}"
export APPTAINERENV_PI_PACKAGE_DIR="${PI_PACKAGE_DIR:-}"
export APPTAINERENV_ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"
export APPTAINERENV_OPENAI_API_KEY="${OPENAI_API_KEY:-}"
export APPTAINERENV_GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-}"
export APPTAINERENV_GOOGLE_CLOUD_API_KEY="${GOOGLE_CLOUD_API_KEY:-}"
exec "$(dirname "$0")/agent-pi" "$@"
```

The settings.json then points at `agent-claude-vscode`, `agent-codex-vscode`, etc. **The existing argv-transparent `agent-<n>` is unchanged.**

If the maintainer prefers no per-extension shims, an alternative is to extend `agent-<n>` itself to whitelist the additional env vars when the calling extension is detected (e.g., by inspecting `$CLAUDE_CODE_ENTRYPOINT == claude-vscode`). The shim approach is recommended because it keeps the terminal use-case wrapper minimal and audit-compatible.

## Part 4 — Apptainer/cluster cross-cutting confirmations

### 4.1 Stdio passthrough

Confirmed from the Apptainer Admin Quick Start (https://apptainer.org/docs/admin/latest/admin_quickstart.html): *"All standard input, output, errors, pipes, IPC, and other communication pathways used by locally running programs are synchronized with the applications running locally within the container"*. The `apptainer exec --help` output (https://apptainer.org/docs/user/latest/cli/apptainer_exec.html) shows **no `--no-tty` or `--tty` flag exists** — Apptainer never allocates a PTY itself. The child inherits whatever stdio fds the parent hands it: a pipe stays a pipe, a tty stays a tty. The canonical example `cat hello_world.py | apptainer exec /tmp/debian.sif python` confirms pipe passthrough works for line-buffered protocols. For the line-buffered stream-JSON contracts of Claude and Codex, the child's libc will buffer based on whether stdout is a tty (line) or a pipe (block) — exactly as if the binary ran directly on the host. **No special flag is needed.**

### 4.2 Network namespace default

Confirmed from https://apptainer.org/docs/user/main/security.html: *"By default only the mount and user namespaces are isolated for containers… The process ID space, network etc. are not isolated in separate namespaces by default"*. From https://apptainer.org/docs/user/latest/networking.html: *"Passing the --net flag will cause the container to join a new network namespace"*. `--containall` per `apptainer exec --help`: *"contain not only file systems, but also PID, IPC, and environment"* — no netns. For non-root users, `--net` is generally unavailable (requires setuid mode + `allow net users/groups` in `apptainer.conf`).

Therefore, **with `--containall --no-mount home,tmp` and no `--net`**, a SIF binary doing `bind("127.0.0.1:N")` and a host process doing `connect("127.0.0.1:N")` share the same loopback. The reverse direction also works. Issue `apptainer/apptainer#2118` ("Loopback SSH inside container") explicitly confirms: *"connecting to localhost from within a container… connects back to the actual machine"*. This is exactly what's needed for `CLAUDE_CODE_SSE_PORT` (CLI→host), OpenCode HTTP server (CLI bind, host connect), and Pi bridge (CLI→host).

### 4.3 Settings-file location convention across forks

| Product | Local desktop (Linux) | Remote server |
|---|---|---|
| VSCode Stable | `~/.config/Code/User/settings.json` | `~/.vscode-server/data/User/settings.json` |
| VSCode Insiders | `~/.config/Code - Insiders/User/settings.json` | `~/.vscode-server-insiders/data/User/settings.json` |
| Cursor | SQLite (`state.vscdb`) | `~/.cursor-server/data/User/settings.json` |
| Windsurf | `~/.config/Windsurf/User/settings.json` | `~/.windsurf-server/data/User/settings.json` |
| VSCodium | `~/.config/VSCodium/User/settings.json` | `~/.vscodium-server/data/User/settings.json` |
| Code-OSS | `~/.config/Code - OSS/User/settings.json` | `~/.vscode-oss-server/data/User/settings.json` |

`VSCODE_AGENT_FOLDER` is confirmed as the official override hook in `microsoft/vscode-remote-release#8673`: *"allow the VSCODE_AGENT_FOLDER environment variable to be set dynamically… The script or command would be expected to output the path to the directory to be used for the VS Code Server"*. **`<VSCODE_AGENT_FOLDER>/data/User/settings.json` is canonical when the variable is set**, and is honored by all forks that did not rename the variable. The lab's custom remote-server install at `/hpc/compgen/users/dstoker/Software/cursor_and_vscode_remote_server/.vscode-server/data/User/settings.json` follows the convention exactly — and Cursor's remote-server reuses upstream VSCode's remote-server bundle, so the `data/User/settings.json` layout is identical (the difference between Cursor desktop and Cursor remote-server is only that desktop uses SQLite, remote uses JSON).

The implementation should resolve the settings file in this order: (1) explicit caller-provided `target_settings_path`; (2) `${VSCODE_AGENT_FOLDER}/data/User/settings.json`; (3) probe known prefixes `~/.cursor-server`, `~/.vscode-server`, `~/.vscode-server-insiders`, `~/.windsurf-server`, `~/.vscodium-server`. The user's lab path is captured by (1).

### 4.4 settings.json merge semantics

VSCode's `settings.json` is **JSONC** (JSON with `//` and `/* */` comments and trailing commas; VSCode ships its own `jsonc-parser` on npm). Python options:

| Library | Comments | Trailing commas | Round-trip preserves comments |
|---|---|---|---|
| `commentjson` | ✓ | ✗ | ✗ |
| `json5` | ✓ | ✓ | ✗ |
| `pyjson5` | ✓ | ✓ | ✗ |
| `json-five` | ✓ | ✓ | ✓ via `ModelLoader` |
| stdlib `json` + comment-strip regex | partial | partial | ✗ |

**Recommendation**: parse with `json5.loads` for tolerance to existing JSONC, deep-merge our keys on top of the existing dict (recursing into nested objects, never overwriting unknown keys), write back with `json.dumps(indent=2)`. Comments are lost but data is preserved. Always `tempfile + os.replace()` for atomicity, and write a `.bak` before the first edit. If preserving comments is a hard requirement, `json-five`'s model API is the fallback. Scope writes to a small namespaced subset: only the keys this report enumerates, never adjacent user keys.

### 4.5 Apptainer bind/exec specifics

- `--bind "$PWD:$PWD"` — correct idiom; identical src/dest preserves absolute path stability for tools.
- `--writable-tmpfs` — provides a tmpfs overlay over the *entire* container rootfs; `/tmp` becomes writable. Default size cap is **64 MiB** (admin sets `sessiondir max size`); flag for raise-on-need. With `--no-mount tmp`, the host `/tmp` is suppressed and writes go to the in-memory overlay (per `apptainer.conf` defaults).
- `--containall` — file systems + PID + IPC + env wipe + minimal `/dev`. Does **not** add `--net`.
- `--no-privs` — drops in-container root caps; for unprivileged invocations it's effectively a safety belt. Apptainer always mounts the rootfs `nosuid` and starts processes with `PR_NO_NEW_PRIVS`, so setuid binaries inside the SIF cannot elevate regardless. No effect on networking.
- `--cleanenv` — drops env. **Critical**: combined with `--containall` (which wipes env), all required env vars must be re-injected via `--env KEY=VALUE` or `APPTAINERENV_KEY` exported before invocation. The wrappers above use the `APPTAINERENV_*` mechanism for exactly this reason.

### 4.6 Multi-extension coexistence

- **Shared host loopback**: All four wrapped agents see the same `127.0.0.1`; ephemeral-port collisions are no worse than running natively. The kernel allocator handles it.
- **`~/.claude/.credentials.json` and analogous files**: With `--no-mount home,tmp`, none of `~/.<agent>/` is auto-bound. **Each wrapper must explicitly `--bind` its agent's state dir**. Concurrent reads are safe; concurrent writes (re-auth refresh) are protected by per-agent lock files (Anthropic uses `.credentials.json.lock`); ensure the home dir is on a POSIX-locking filesystem (most networked HPC homes are; some autofs/NFSv3 setups have stale-lock issues — flag for testing).
- **SQLite WAL on `~/.codex/logs_2.sqlite`**: Multi-process WAL mode requires `fcntl()` byte-range locking. PID-namespace isolation under `--containall` does **not** affect `fcntl` byte-range locks (those are per-inode, not per-PID-ns). Safe on local disk and most cluster filesystems; potentially problematic on Lustre/GPFS without `flock` support — flag for testing.
- **MCP servers**: Each agent spawns its own; under `--containall` they live in the agent's PID namespace and die with it. No cross-agent contention.
- **Per-agent SIFs with overlapping `--bind` targets**: Safe; bind mounts are per-namespace.
- **Genuine conflict to watch**: any agent that writes a single global PID/lock at a fixed path and refuses to start a second instance — but this is an agent-level concern, not a containerization one.

## Part 5 — Concrete deliverables

### 5.1 Per-extension JSON snippet table

(See §3.1 above.)

### 5.2 Concrete wrapper script template per agent

(See §3.3 above. The existing `agent-<n>` stays argv-transparent and is reused; thin `agent-<n>-vscode` shims add the env-passthrough.)

### 5.3 Apptainer exec invocation per agent

The base invocation in the existing `agent-<n>` is `apptainer exec --containall --no-mount home,tmp --writable-tmpfs --bind "$PWD:$PWD" --pwd "$PWD" --no-privs <bind-mounts...> <SIF> <agent-binary> "$@"`. Bind-mount additions for VSCode use:

**agent-claude** — required binds (verify currently configured in installer):
- `$HOME/.claude:$HOME/.claude` (rw — credentials, sessions, lockfiles)
- `$HOME/.claude.json:$HOME/.claude.json` (rw — separate file, NOT inside `.claude/`)
- `$HOME/.cache:$HOME/.cache:ro` (bun cache, npm cache for MCP via npx)
- `$HOME/.npm:$HOME/.npm:ro` and `$HOME/.bun:$HOME/.bun:ro` (if MCP servers use them)
- `/etc/ssl/certs:/etc/ssl/certs:ro`, `/etc/pki:/etc/pki:ro` (TLS)
- `/etc/resolv.conf`, `/etc/hosts` (DNS)
- `$HOME/.gitconfig:$HOME/.gitconfig:ro` (git tool)
- The extension's bundled binary path if reused: `<vscode-server>/extensions/anthropic.claude-code-*-linux-x64/resources/native-binary/:...:ro` (only needed if the wrapper bind-mounts the host's bundled binary into the SIF rather than shipping its own)

**agent-codex** — required binds:
- `$HOME/.codex:$HOME/.codex` (rw — auth.json, config.toml, logs_2.sqlite + WAL, tmp/arg0 lockdir, sessions, history)
- `/tmp:/tmp` (rw — codex spawns shells writing temp files)
- `/dev/shm:/dev/shm` (rw — SQLite WAL spillover)
- `/etc/ssl/certs:/etc/ssl/certs:ro`, `/etc/pki:/etc/pki:ro`
- `/etc/resolv.conf`, `/etc/hosts`

**agent-opencode** — required binds:
- `$HOME/.config/opencode:$HOME/.config/opencode` (rw — auth.json, opencode.json)
- `$HOME/.local/share/opencode:$HOME/.local/share/opencode` (rw — sessions DB, project metadata)
- `$HOME/.cache/opencode:$HOME/.cache/opencode` (rw — bun-installed plugins)
- `$HOME/.opencode:$HOME/.opencode:ro` (legacy auth fallback)
- `/tmp:/tmp` (rw — bun tmpdir, IPC sockets if any plugins use them)
- `/etc/ssl/certs:/etc/ssl/certs:ro`, `/etc/pki:/etc/pki:ro`
- `$HOME/.gitconfig:$HOME/.gitconfig:ro`
- The npm shim path (host-side `node_modules/`) if the wrapper keeps the Node-shim layer outside the SIF: bind the entire `coding_agents` install root.

**agent-pi** — required binds:
- `$HOME/.pi:$HOME/.pi` (rw — auth.json, models.json, sessions, packages, extensions, skills)
- `<vscode-server>/extensions/pi0.pi-vscode-<version>:<same>:ro` (the bundled pi-side extension that the CLI loads — **critical**, missing this is a fail-fast)
- `/tmp:/tmp` (rw — atomic writes)
- `/etc/ssl/certs:/etc/ssl/certs:ro`, `/etc/pki:/etc/pki:ro`
- `$HOME/.gitconfig:$HOME/.gitconfig:ro`

### 5.4 Test checklist

Add to `tests/test_policy_emit.py` and an integration test suite:

1. **`test_emit_managed_vscode_settings_writes_four_keys`** — instantiate a temp settings.json, call `_emit_managed_vscode_settings(install_dir, target)`, assert the four primary keys are present with values pointing at `<install_dir>/bin/agent-<n>(-vscode)?` and that `terminal.integrated.env.linux.PATH` is prefixed with `<install_dir>/bin/path-shim`.
2. **`test_emit_preserves_unrelated_keys`** — pre-populate the settings.json with `{"editor.fontSize": 14, "files.autoSave": "afterDelay"}`; after emit, assert those keys are unchanged.
3. **`test_emit_is_idempotent`** — call twice; assert no key duplication, no list growth, byte-identical second-call output.
4. **`test_emit_rewrites_stale_install_dir`** — pre-populate with an old `<install_dir>` value; assert it's replaced with the new one (deep equality on the four keys).
5. **`test_emit_handles_jsonc_input`** — feed input with `//` comments and trailing commas; assert it parses and writes valid JSON output.
6. **`test_emit_atomic_write`** — patch `os.replace` to raise; assert the original file is untouched and a `.bak` exists.
7. **Integration: Claude audit-log** — open Claude in VSCode, send a single message, assert an entry appears in the audit log emitted by `agent-claude` with the expected timestamp and PID.
8. **Integration: Codex app-server through wrapper** — open Codex sidebar, click "New thread", assert the JSON-RPC `initialize` → `initialized` → `thread/start` sequence completes (verify by tailing extension logs in the IDE's Output panel — VSCode `View → Output` or Cursor's equivalent).
9. **Integration: OpenCode HTTP reachability** — start OpenCode v2 sidebar, assert `curl -s http://127.0.0.1:$_EXTENSION_OPENCODE_PORT/` returns the server-info JSON, confirming the SIF-bound port is reachable from the host.
10. **Integration: Pi binary location** — open Pi panel; assert no "couldn't find binary" error; verify the spawned process command line in `ps -ef | grep agent-pi`.
11. **Apptainer netns confirmation** — inside the SIF, run `apptainer exec ... bash -c 'ss -tnl'`; assert host-bound ports are visible (proves shared netns).
12. **Stdio framing test for Codex** — pipe a known JSON-RPC `initialize` request into `agent-codex app-server` via stdio; assert byte-exact response framing on stdout (no buffering corruption).

### 5.5 Known limitations and fallback strategies

**OpenCode (both flavours)** — no settings-only wrap. Recommended fallback strategy in priority order:

(d) **PATH-prefix shim** — primary strategy. Place `<install_dir>/bin/path-shim/opencode` first on `$PATH`. The classic extension's terminal-spawned process inherits the user shell's PATH, so the shim wins automatically once `~/.bashrc` (or `terminal.integrated.env.linux.PATH` in the IDE settings) prepends `<install_dir>/bin/path-shim`. **For v2's extension-host spawn, the user must launch the IDE itself with the prefixed PATH** (e.g., `PATH=<install_dir>/bin/path-shim:$PATH code .` for VSCode, or the equivalent `cursor .` for Cursor), because the extension host inherits PATH from the IDE process at launch and the `terminal.integrated.env.*` setting only affects terminals. Risk: medium — relies on user discipline to launch the IDE correctly. Mitigation: ship a `code-wrapped` (and `cursor-wrapped` for Cursor users) launcher in `<install_dir>/bin/` that sets PATH and execs the real IDE binary; document it in the install README.

(a) **Symlink replacement** — fallback if PATH-prefix is undesirable. Replace `node_modules/.bin/opencode` (the npm shim) with a symlink to `<install_dir>/bin/agent-opencode`. Risk: high — `npm install` / `bun install` overwrites the symlink; auto-update of `opencode-ai` package wipes it. Mitigation: protect with file flags (chattr +i) on supported filesystems, or a post-install hook.

(b) **Tmpfs over binary path** — last resort if neither (d) nor (a) is workable. Mount a tmpfs over the npm shim path containing the wrapper binary. Tied to VSCode session lifetime; complex; not recommended.

(c) **LD_PRELOAD shim** — not viable. OpenCode is a Go binary; Go's runtime does its own syscall-level execve and largely ignores LD_PRELOAD interceptors for `execve` from within the runtime. Even for the Node shim layer, intercepting `execve` to rewrite the binary path is fragile across libc versions.

(e) **Forking the extension** — marketplace-violating. Avoid.

**Claude — `useTerminal=true` users**: If a user toggles `claudeCode.useTerminal: true`, `claudeProcessWrapper` is bypassed (`#10500`, `#11647`). Mitigation: emit `claudeCode.useTerminal: false` in our managed settings, document the conflict, and add a probe in the installer that detects the override and warns.

**Claude — `environmentVariables` deletion bug (`#10217`)**: in trusted workspaces, the extension may delete this key. Mitigation: don't put load-bearing env in `claudeCode.environmentVariables`; put it in the wrapper script (`agent-claude-vscode`) instead. Our snippet emits a single non-critical entry there.

**Codex — bundled binary auto-update version drift**: if the wrapper points at a frozen copy of the codex binary, an extension update may bump the protocol and the `assertSupportedCodexAppServerVersion` check fails. Mitigation: in `agent-codex-vscode`, dynamically resolve the bundled binary path at runtime (`ls -d $HOME/.vscode-server/extensions/openai.chatgpt-*-linux-x64/bin/linux-x86_64/codex | sort -V | tail -n1`) and pass it as the SIF target; the SIF only contains the runtime libs (glibc, rg, git, bash), and the binary itself is bind-mounted from the extension dir.

**Pi — closed-source RPC mode framing**: the `@pi` chat participant uses `pi --rpc` with strict LF-delimited JSONL. Wrapper must not buffer or translate line endings. Use `exec apptainer exec` (no shell wrapping after); the wrapper must `exec` (preserve PID/PTY), not fork. The pi-side bundled extension dir under the VSCode extension's install path **must** be bind-mounted read-only — missing this fails fast with a runtime path error.

## Implementation plan for `_emit_managed_vscode_settings`

**Files to create or modify**

1. **`src/coding_agents/installer/policy_emit.py`** — add `_emit_managed_vscode_settings`.
2. **`src/coding_agents/merge_settings.py`** — new module for JSONC-tolerant deep-merge with atomic write.
3. **`src/coding_agents/installer/wrapper_vscode.py`** — new module that emits the four `agent-<n>-vscode` shim scripts and the `path-shim/opencode` script.
4. **`tests/test_policy_emit.py`** — extend with the cases in §5.4.
5. **`tests/test_merge_settings.py`** — new test file for the merge module.
6. **`docs/vscode_integration.md`** — operator-facing guide covering the OpenCode PATH-prefix caveat and the IDE-wrapped launcher (`code-wrapped` for VSCode users; `cursor-wrapped` for Cursor users).
7. **`bin/code-wrapped`** (and an analogous `bin/cursor-wrapped`) — new launchers that set `PATH=<install_dir>/bin/path-shim:$PATH` and exec the user's actual `code` / `cursor` binary respectively.

**Function signatures**

```python
# src/coding_agents/merge_settings.py
def deep_merge_jsonc_settings(
    target_path: pathlib.Path,
    new_keys: dict[str, Any],
    *,
    backup: bool = True,
) -> None:
    """Atomically merge `new_keys` into the JSONC file at `target_path`.

    Reads with json5 for tolerance to comments and trailing commas. Performs a
    recursive deep-merge: nested dicts are merged key-by-key; lists are
    replaced wholesale; scalars are overwritten. Preserves unrelated top-level
    keys. Writes via tempfile + os.replace() with fsync. If `backup=True`,
    writes <target_path>.bak before first replace.

    Raises:
        FileNotFoundError: if the parent directory does not exist.
        ValueError: if the existing file is unparseable as JSONC/JSON5.
    """

# src/coding_agents/installer/policy_emit.py
def _emit_managed_vscode_settings(
    install_dir: pathlib.Path,
    target_settings_path: pathlib.Path,
) -> None:
    """Write the four managed VSCode settings keys to the user's settings.json.

    Resolves wrapper script paths under `<install_dir>/bin/` and merges the
    following keys into `target_settings_path`:
      - claudeCode.claudeProcessWrapper -> <install_dir>/bin/agent-claude-vscode
      - claudeCode.useTerminal -> false
      - claudeCode.disableLoginPrompt -> true
      - claudeCode.initialPermissionMode -> "acceptEdits"
      - claudeCode.environmentVariables -> [{"name": "CLAUDE_CODE_ENTRYPOINT", "value": "claude-vscode"}]
      - chatgpt.cliExecutable -> <install_dir>/bin/agent-codex-vscode
      - chatgpt.openOnStartup -> false
      - terminal.integrated.env.linux.PATH -> <install_dir>/bin/path-shim:${env:PATH}
      - pi-vscode.path -> <install_dir>/bin/agent-pi-vscode

    Idempotent. Preserves unrelated user keys. Atomic write via
    deep_merge_jsonc_settings. Creates parent directories as needed.

    Raises:
        FileNotFoundError: if `target_settings_path` parent directory does not
        exist and cannot be created.
    """

def _resolve_vscode_settings_path() -> pathlib.Path | None:
    """Locate the active VSCode/Cursor remote-server settings.json.

    Resolution order:
      1. $VSCODE_SETTINGS_OVERRIDE if set (operator escape hatch)
      2. $VSCODE_AGENT_FOLDER/data/User/settings.json if VSCODE_AGENT_FOLDER set
      3. ~/.cursor-server/data/User/settings.json
      4. ~/.vscode-server/data/User/settings.json
      5. ~/.vscode-server-insiders/data/User/settings.json
      6. ~/.windsurf-server/data/User/settings.json
      7. ~/.vscodium-server/data/User/settings.json

    Returns the first existing path, or None if none exist.
    """
```

**Test cases (assertion semantics)**

```python
def test_emits_four_primary_keys(tmp_path):
    install = tmp_path / "install"
    settings = tmp_path / "settings.json"
    settings.write_text("{}")
    _emit_managed_vscode_settings(install, settings)
    data = json.loads(settings.read_text())
    assert data["claudeCode.claudeProcessWrapper"] == str(install / "bin" / "agent-claude-vscode")
    assert data["claudeCode.useTerminal"] is False
    assert data["chatgpt.cliExecutable"] == str(install / "bin" / "agent-codex-vscode")
    assert data["pi-vscode.path"] == str(install / "bin" / "agent-pi-vscode")
    assert data["terminal.integrated.env.linux"]["PATH"].startswith(str(install / "bin" / "path-shim"))

def test_preserves_unrelated_keys(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"editor.fontSize": 14, "files.autoSave": "afterDelay"}))
    _emit_managed_vscode_settings(tmp_path / "install", settings)
    data = json.loads(settings.read_text())
    assert data["editor.fontSize"] == 14
    assert data["files.autoSave"] == "afterDelay"

def test_idempotent(tmp_path):
    settings = tmp_path / "settings.json"; settings.write_text("{}")
    _emit_managed_vscode_settings(tmp_path / "install", settings)
    first = settings.read_text()
    _emit_managed_vscode_settings(tmp_path / "install", settings)
    assert settings.read_text() == first

def test_rewrites_stale_install_dir(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"claudeCode.claudeProcessWrapper": "/old/path/agent-claude-vscode"}))
    _emit_managed_vscode_settings(tmp_path / "newinstall", settings)
    data = json.loads(settings.read_text())
    assert "/old/path" not in data["claudeCode.claudeProcessWrapper"]

def test_handles_jsonc_input(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text('// comment\n{\n  "editor.fontSize": 14,\n}\n')
    _emit_managed_vscode_settings(tmp_path / "install", settings)
    data = json.loads(settings.read_text())  # output must be plain JSON
    assert data["editor.fontSize"] == 14
    assert "claudeCode.claudeProcessWrapper" in data

def test_atomic_write_on_failure(tmp_path, monkeypatch):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"editor.fontSize": 14}))
    monkeypatch.setattr("os.replace", lambda *a, **k: (_ for _ in ()).throw(OSError))
    with pytest.raises(OSError):
        _emit_managed_vscode_settings(tmp_path / "install", settings)
    assert json.loads(settings.read_text()) == {"editor.fontSize": 14}
    assert (tmp_path / "settings.json.bak").exists()
```

**Order of implementation (priority)**

1. **Land Pi first.** Smallest surface area, settings-only override, single key, no env-passthrough complexity beyond bridge URL/token/terminal-id, no auto-update concern. Manual verification: open the Pi sidebar in VSCode/Cursor, send `@pi help`, observe a session in `~/.pi/agent/sessions/` and confirm `ps -ef | grep agent-pi` shows the wrapped process.
2. **Land Claude second.** High-leverage and the user already has plumbing for `~/.claude/`. Watch out for `useTerminal=false` and `environmentVariables` bug; emit them defensively. Manual verification: open Claude pane, `/init`, send a message, confirm audit-log entry from `agent-claude`.
3. **Land Codex third.** Slightly more complex due to env list and dynamic bundled-binary resolution; SQLite + arg0 lockdir bind. Manual verification: open Codex sidebar, click "New thread", confirm `initialize` handshake completes (IDE Output panel: "OpenAI ChatGPT" channel).
4. **Land OpenCode last.** Highest risk and only partial coverage (PATH-prefix only works for extension-host spawns when the IDE is launched with the prefix). Ship the `code-wrapped` (VSCode) and `cursor-wrapped` (Cursor) launchers and document the limitation. Manual verification: launch via the appropriate IDE-wrapped script, open OpenCode sidebar, hit `curl http://127.0.0.1:$_EXTENSION_OPENCODE_PORT/` from the host shell, confirm the sandboxed binary is the one listening (via `ss -tlnp`).

**Manual verification per agent (operator runbook)**

For each agent: (1) open the corresponding VSCode/Cursor panel; (2) `ps -ef | grep agent-<n>` to confirm the wrapper process is in the chain; (3) `cat /proc/<pid>/cgroup` and `readlink /proc/<pid>/ns/mnt` on the inner agent process to confirm it's in a different mount namespace from the extension host; (4) check the per-agent state dir for fresh writes (e.g., `stat ~/.codex/logs_2.sqlite`); (5) trigger the agent's primary action (send message, run command) and confirm the response renders in the panel.

**Conclusion.** Three of the four extensions are straightforward: emit the right key into settings.json, point at a thin `agent-<n>-vscode` shim that adds env-passthrough, and reuse the existing `agent-<n>` for the actual Apptainer exec. OpenCode is the architectural outlier and needs PATH-prefix injection plus an operator runbook for launching the IDE (VSCode or Cursor) with the prefix in scope. Apptainer's defaults — shared netns, transparent stdio, writable-tmpfs — are the unsung hero: every assumption about IPC working through the SIF holds without any additional flags. The implementation is one Python module of ~150 lines plus four small bash shims; the test surface is enumerated and tractable; the rollout order is Pi → Claude → Codex → OpenCode in increasing risk.