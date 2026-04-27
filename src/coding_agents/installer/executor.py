"""Installation executor — runs the actual install steps.

Called from the Review screen. Writes progress to a Textual RichLog widget.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import shutil
import subprocess
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

_log = logging.getLogger("coding-agents")

from coding_agents.agents import AGENTS
from coding_agents.config import (
    BUNDLED_SKILLS,
    GIT_SKILLS,
    HOOK_SCRIPTS,
    HPC_SHARED_SKILLS,
    mark_installed,
    save_config,
)
from coding_agents.dry_run import is_dry_run, would
from coding_agents.installer.fs_ops import (
    dry_run_copy,
    dry_run_copytree,
    dry_run_mkdir,
    dry_run_rmtree,
    dry_run_write_text,
)
from coding_agents.installer.state import InstallerState
from coding_agents.utils import (
    inject_shell_block,
    npm_install,
    run,
    safe_symlink,
    uv_create_venv,
    uv_pip_install,
)

if TYPE_CHECKING:
    from textual.widgets import RichLog


def _bundled_dir() -> Path:
    """Return the path to the bundled/ directory shipped with the package.

    bundled/ lives at src/coding_agents/bundled/ — this works both for
    editable installs and pip-installed packages.
    """
    bundled = Path(__file__).resolve().parent.parent / "bundled"
    if bundled.exists():
        return bundled
    raise FileNotFoundError(f"Cannot find bundled/ directory at {bundled}")


async def _run_in_thread(func, *args, **kwargs):
    """Run a blocking function in a thread."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))


async def execute_install(state: InstallerState, log: "RichLog") -> None:
    """Execute the full installation based on user selections.

    `log` is a textual.widgets.RichLog OR an InstallObserver — both expose
    `.write()`. When the observer is passed, calling its `.start_phase()`
    advances the progress bar in the TUI; when a bare RichLog is passed
    (e.g. from tests) the start_phase calls are no-ops via getattr.
    """
    install_dir = state.install_path
    _log.info("execute_install: mode=%s, install_dir=%s, agents=%s, tools=%s, skills=%s",
              state.mode, install_dir, state.agents, state.tools, state.skills)

    # Compute the visible-phase count up-front so the progress bar can show
    # X / N instead of an indeterminate spinner.
    phases = [
        "backup", "mkdir", "agents", "config", "vscode_ext",
        "shell_rc", "settings_merge", "save_config",
    ]
    if state.tools:           phases.append("tools")
    if state.skills:          phases.append("skills")
    if state.hooks:           phases.append("hooks")
    if state.mode != "local":
        phases.extend(["sandbox_dirs", "wrappers", "policy"])

    set_total = getattr(log, "set_total_phases", None)
    if callable(set_total):
        set_total(len(phases))

    def _phase(name: str) -> None:
        """Advance the progress bar; degrade to a plain header on bare RichLog."""
        starter = getattr(log, "start_phase", None)
        if callable(starter):
            starter(name)
        else:
            log.write(f"\n[bold]{name}[/bold]")

    # --- 0. Backup existing installations ---
    _phase("🔍  Checking for existing installations…")
    await _backup_existing(state.agents, log)

    # --- create dir structure ---
    _phase("📁  Creating directory structure…")
    for subdir in ["bin", "config", "config/mcp", "config/templates", "hooks",
                    "skills", "tools", "tools/bin", "logs", "node_modules"]:
        dry_run_mkdir(install_dir / subdir)

    bundled = _bundled_dir()

    # --- 1. Install agents ---
    _phase("📦  Installing agents…")
    for agent_key in state.agents:
        agent = AGENTS[agent_key]
        log.write(f"  Installing {agent['display_name']}…")
        try:
            await _install_agent(agent_key, agent, install_dir, log)
            log.write(f"  [green]✓[/green] {agent['display_name']}")
        except Exception as exc:
            log.write(f"  [red]✗ {agent['display_name']}: {exc}[/red]")

    # --- 2. Install tools ---
    if state.tools:
        _phase("🔧  Installing tools…")
        await _install_tools(state.tools, install_dir, log)

    # --- 3. Install skills ---
    if state.skills:
        _phase("🧠  Installing skills…")
        await _install_skills(state.skills, install_dir, bundled, log, mode=state.mode)

    # --- 4. Copy hooks ---
    if state.hooks:
        _phase("🪝  Installing hooks…")
        await _install_hooks(state.hooks, install_dir, bundled, log)

    # --- 5. Bootstrap per-user sandbox dirs (HPC only) ---
    if state.mode != "local":
        _phase("🏗️   Bootstrapping per-user sandbox dirs…")
        await _bootstrap_user_dirs(state, log)

    # --- 6. Copy config files (mode-aware AGENTS.md) ---
    _phase("📋  Copying configuration files…")
    await _install_config(install_dir, bundled, log, mode=state.mode)

    # --- 7. VSCode extension recommendations ---
    _phase("🧩  VSCode extensions…")
    await _install_vscode_extensions(state, install_dir, log)

    # --- 8. Create sandbox wrapper scripts (HPC only) ---
    if state.mode != "local":
        _phase("🛡️   Creating sandbox wrapper scripts…")
        await _create_sandbox_wrappers(state, install_dir, log)

    # --- 8a. Emit managed policy files (Claude settings + Codex TOML) ---
    if state.mode != "local":
        _phase("🔐  Emitting managed policy files…")
        await _emit_managed_policy(state, bundled, log)

    # --- 8b. VSCode extension wrappers (stubs + helper + settings.json) ---
    if state.mode != "local":
        _phase("🪟  Wiring VSCode extension wrappers…")
        await _emit_vscode_extension_wrappers(state, install_dir, log)

    # --- 9. Shell integration ---
    _phase("🐚  Setting up shell integration…")
    inject_shim = state.mode != "local" and "opencode" in state.agents
    modified = await _run_in_thread(
        lambda: inject_shell_block(
            install_dir,
            sandbox_sif_path=state.sandbox_sif_path if state.mode != "local" else "",
            sandbox_secrets_dir=state.sandbox_secrets_dir if state.mode != "local" else "",
            sandbox_logs_dir=state.sandbox_logs_dir if state.mode != "local" else "",
            inject_path_shim=inject_shim,
        )
    )
    for f in modified:
        log.write(f"  [green]✓[/green] Updated {f}")

    # --- 10. Smart-merge existing settings ---
    _phase("🔀  Merging settings with existing configs…")
    await _merge_existing_settings(state, install_dir, log)

    # --- 11. Save config ---
    _phase("💾  Saving config…")
    config = state.to_config_dict()
    mark_installed(config)
    log.write(f"  [green]✓[/green] Config saved to ~/.coding-agents.json")

    finisher = getattr(log, "finish_phase", None)
    if callable(finisher):
        finisher()


async def _backup_existing(agents: list[str], log: RichLog) -> None:
    """Back up existing agent config directories to .tar.gz, in parallel.

    Each agent's tarball runs in its own thread (gzip releases the GIL on
    the deflate hot path; tar reads from NFS release the GIL too), so on
    a multi-core box `.claude` and `.codex` finish in roughly the time
    of the slower one rather than the sum. See backup_agent_dir for the
    compresslevel choice.
    """
    _log.debug("backup_existing: scanning for agents=%s", agents)
    from coding_agents.detect_existing import scan_existing, backup_agent_dir

    inventory = scan_existing()
    if not inventory.has_existing:
        log.write("  [dim]No existing installations found[/dim]")
        return

    targets = [inv for inv in inventory.existing_agents if inv.agent_key in agents]
    if not targets:
        log.write("  [dim]No existing installations match selected agents[/dim]")
        return

    for inv in targets:
        log.write(
            f"  {inv.display_name}: {inv.file_count} files "
            f"({inv.human_size()}) in {inv.config_dir}"
        )
        log.write(f"    Files:\n{inv.tree_display(max_files=10)}")

    results = await asyncio.gather(
        *(_run_in_thread(backup_agent_dir, inv) for inv in targets)
    )
    for inv, backup_path in zip(targets, results):
        if backup_path:
            log.write(
                f"  [green]✓[/green] {inv.display_name}: backed up to {backup_path}"
            )
        else:
            log.write(f"  [dim]{inv.display_name}: no backup needed[/dim]")


async def _merge_existing_settings(
    state: InstallerState, install_dir: Path, log: RichLog
) -> None:
    """Smart-merge coding-agents settings into existing agent configs.

    Shows before/after for each merge operation.
    """
    from coding_agents.config import build_hook_entries
    from coding_agents.merge_settings import (
        merge_claude_hooks,
        merge_claude_deny_rules,
        merge_mcp_servers,
    )

    home = Path.home()

    # Merge Claude Code hooks if Claude is selected and hooks are enabled
    if "claude" in state.agents and state.hooks:
        settings_path = home / ".claude" / "settings.json"
        hook_entries = build_hook_entries(install_dir, state.hooks)

        if hook_entries:
            results = await _run_in_thread(merge_claude_hooks, settings_path, hook_entries)
            for r in results:
                log.write(f"  [green]✓[/green] Claude {r.section}: {r.summary()}")
                if r.original is not None:
                    log.write(f"    [dim]Before: {len(r.preserved_keys)} existing entries[/dim]")
                log.write(f"    [dim]After: +{len(r.added_keys)} coding-agents entries[/dim]")

    # Merge deny rules for Claude
    if "claude" in state.agents:
        deny_path = install_dir / "hooks" / "deny_rules.json"
        if deny_path.exists():
            deny_data = json.loads(deny_path.read_text())
            rules = deny_data.get("deny", [])
            if rules:
                settings_path = home / ".claude" / "settings.json"
                r = await _run_in_thread(merge_claude_deny_rules, settings_path, rules)
                log.write(f"  [green]✓[/green] Claude deny rules: {r.summary()}")

    # Merge MCP servers if servers.json exists
    servers_json = install_dir / "config" / "mcp" / "servers.json"
    if servers_json.exists():
        canonical = json.loads(servers_json.read_text())
        servers = canonical.get("servers", {})
        if servers:
            # Claude MCP
            if "claude" in state.agents:
                mcp_path = home / ".mcp.json"
                r = await _run_in_thread(merge_mcp_servers, mcp_path, servers)
                log.write(f"  [green]✓[/green] Claude MCP: {r.summary()}")


async def _install_agent(key: str, agent: dict, install_dir: Path, log: RichLog) -> None:
    """Install a single agent.

    For npm-method agents (codex, opencode, pi) the host npm install is
    skipped — the agent runs from the SIF (which has the binary baked in
    via the SIF build), and the wrapper template at
    ``<install_dir>/bin/agent-<key>`` (created later in phase 8) routes
    the wrapped flow through the SIF. The CODING_AGENTS_NO_WRAP=1 escape
    hatch also goes via the SIF (see runtime/agent_vscode.exec_no_wrap).

    Pi's ``post_install`` extension wiring (pi-ask-user et al.) is now
    handled by the SIF builder + the wrapper template's first-run hook
    (Phase 2b of the no-wrap-via-sif plan); the host post_install loop
    is therefore dropped. No other agent currently uses post_install.
    """
    method = agent["method"]
    _log.info("install_agent: %s (method=%s, package=%s)", key, method, agent.get("package", "N/A"))

    if method == "npm":
        # SIF-baked agents — host install is dead weight after the no-wrap
        # refactor. The wrapper at <install_dir>/bin/agent-<key> (phase 8)
        # routes through the SIF.
        log.write(
            f"    [dim]agent runs from the SIF — skipping host npm install for {agent['display_name']}[/dim]"
        )
        return

    elif method == "curl":
        # Claude Code — install to default location, then symlink
        await _run_in_thread(
            run,
            ["bash", "-c", agent["install_cmd"]],
            shell=False,
            check=False,  # Don't fail if already installed
        )
        claude_bin = Path.home() / ".claude" / "bin" / "claude"
        if claude_bin.exists():
            safe_symlink(claude_bin, install_dir / "bin" / "claude")
        else:
            # Try finding it on PATH
            which = shutil.which("claude")
            if which:
                safe_symlink(Path(which), install_dir / "bin" / "claude")
            else:
                raise FileNotFoundError("Claude Code binary not found after install")

        # Install and configure ccstatusline statusline
        if key == "claude":
            await _install_claude_statusbar(log, install_dir=install_dir)


_CCSTATUSLINE_VERSION = "2.2.10"


async def _install_claude_statusbar(log: RichLog, *, install_dir: Path) -> None:
    """Install ccstatusline + wire the statusLine entry in ~/.claude/settings.json.

    ccstatusline (https://github.com/sirmalloc/ccstatusline, ~3 MB, MIT) is a
    zero-config Claude Code statusline written in TypeScript. When invoked
    non-interactively (i.e. by Claude Code's statusLine.command), it prints
    the statusline to stdout and exits. When invoked interactively from a
    shell, the same `ccstatusline` binary opens a TUI for customisation.

    Replaces the prior `claude-statusbar` (`cs --hide-pet`) flow, which had
    a latent bug in HPC mode: `uv tool install claude-statusbar` installed
    `cs` to the *host* (e.g. ~/.local/bin/cs), but Claude runs inside the
    SIF, where `--no-mount home` makes the host PATH invisible — so the
    statusLine.command was a silent no-op under SLURM. ccstatusline is
    baked into the SIF (bundled/sif/package.json) so the in-SIF binary at
    /opt/agents/node_modules/.bin/ccstatusline resolves cleanly.

    For local mode (and as a host-side fallback for HPC users on a stale
    SIF that hasn't been rebuilt with ccstatusline yet), we additionally
    npm-install ccstatusline into <install_dir>/node_modules so the
    install_dir's node_modules/.bin/ — already on PATH via the shell-rc
    injection — resolves bare `ccstatusline` too.
    """
    log.write(f"    Installing ccstatusline@{_CCSTATUSLINE_VERSION}...")
    try:
        await _run_in_thread(npm_install, install_dir, f"ccstatusline@{_CCSTATUSLINE_VERSION}")
        log.write(f"    [green]✓[/green] ccstatusline@{_CCSTATUSLINE_VERSION} installed under {install_dir}/node_modules")
    except (subprocess.CalledProcessError, OSError, FileNotFoundError) as exc:
        # Non-fatal: in HPC mode the in-SIF copy still works. Just warn.
        log.write(
            f"    [yellow]npm install ccstatusline failed ({exc}); "
            f"statusline still configured (HPC mode falls back to the in-SIF copy at "
            f"/opt/agents/node_modules/.bin/ccstatusline; local mode users will need "
            f"the package on PATH manually).[/yellow]"
        )

    settings_path = Path.home() / ".claude" / "settings.json"
    dry_run_mkdir(settings_path.parent)
    existing: dict = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError):
            existing = {}

    existing["statusLine"] = {
        "type": "command",
        "command": "ccstatusline",
        "padding": 0,
        "refreshInterval": 10,
    }

    from coding_agents.utils import secure_write_text
    secure_write_text(settings_path, json.dumps(existing, indent=2) + "\n")
    log.write(f"    [green]✓[/green] statusLine configured in {settings_path}")
    log.write(
        "    [dim]ccstatusline has zero-config defaults that work out of the box. "
        "Customise interactively by running `ccstatusline` in a terminal — "
        "it auto-detects whether to print (non-TTY, called by Claude) or "
        "open the TUI (TTY, called by you).[/dim]"
    )


async def _install_tools(tools: list[str], install_dir: Path, log: RichLog) -> None:
    """Install supporting tools."""
    venv_path = install_dir / "tools" / ".venv"

    # Python tools need a venv
    python_tools_needed = any(t in tools for t in ["crawl4ai", "linters"])
    if python_tools_needed and not venv_path.exists():
        log.write("  Creating Python tools venv...")
        try:
            await _run_in_thread(uv_create_venv, venv_path)
            log.write("  [green]✓[/green] venv created")
        except Exception as exc:
            log.write(f"  [red]✗ venv creation failed: {exc}[/red]")
            python_tools_needed = False

    if "linters" in tools and python_tools_needed:
        log.write("  Installing linters (ruff, vulture, pyright, yamllint)...")
        try:
            await _run_in_thread(
                uv_pip_install, venv_path, ["ruff", "vulture", "pyright", "yamllint"]
            )
            log.write("  [green]✓[/green] Python linters installed")
        except Exception as exc:
            log.write(f"  [red]✗ Python linters: {exc}[/red]")

    if "crawl4ai" in tools and python_tools_needed:
        log.write("  Installing crawl4ai...")
        try:
            await _run_in_thread(uv_pip_install, venv_path, ["crawl4ai"])
            log.write("  [green]✓[/green] crawl4ai installed")
        except Exception as exc:
            log.write(f"  [red]✗ crawl4ai: {exc}[/red]")

    if "linters" in tools:
        # Node linter: biome
        log.write("  Installing biome...")
        try:
            tools_dir = install_dir / "tools"
            await _run_in_thread(npm_install, tools_dir, "@biomejs/biome")
            log.write("  [green]✓[/green] biome installed")
        except Exception as exc:
            log.write(f"  [red]✗ biome: {exc}[/red]")

        # Static binary: shellcheck
        log.write("  Installing shellcheck v0.11.0...")
        try:
            await _run_in_thread(_install_shellcheck, install_dir)
            log.write("  [green]✓[/green] shellcheck installed")
        except Exception as exc:
            log.write(f"  [yellow]shellcheck: {exc}[/yellow]")

    if "agent-browser" in tools:
        log.write("  Installing agent-browser...")
        try:
            tools_dir = install_dir / "tools"
            await _run_in_thread(npm_install, tools_dir, "agent-browser")
            log.write("  [green]✓[/green] agent-browser installed")
        except Exception as exc:
            log.write(f"  [red]✗ agent-browser: {exc}[/red]")

    if "entire" in tools:
        # Reference: https://github.com/entireio/cli — install.sh is itself
        # non-interactive, but its very last line is
        #   "$install_path" curl-bash-post-install
        # which calls back into the freshly-installed binary for
        # telemetry/auth init. That subprocess has no timeout and reliably
        # hangs on HPCs. We strip that line via sed before piping to bash
        # (Option 1 from the design discussion). The binary still installs
        # to ~/.local/bin and is fully usable; if a feature later needs the
        # post-install hook the user can run `entire <whatever>` manually.
        # On any failure we fall back to a clear "install manually" pointer
        # (Option 4).
        MANUAL = "https://entire.io/  (or https://github.com/entireio/cli)"
        log.write("  Installing entire CLI…")

        # Pre-flight cleanup — install.sh has a "PATH conflict" sanity
        # check at the end that fires (rc != 0) if `command -v entire`
        # resolves to anything other than its own install_path. On a
        # second install run, our own <install_dir>/bin/entire symlink
        # from the previous run shows up first on PATH (we put it there
        # via the shell rc block) and triggers a false conflict. Removing
        # the old symlink up front lets install.sh run clean.
        stale = install_dir / "bin" / "entire"
        if stale.exists() or stale.is_symlink():
            try:
                if is_dry_run():
                    would("symlink", "remove", path=stale, reason="entire pre-install cleanup")
                else:
                    stale.unlink()
                log.write("  [dim]Removed stale <install_dir>/bin/entire symlink[/dim]")
            except OSError as exc:
                log.write(f"  [yellow]could not remove {stale}: {exc}[/yellow]")
        cmd = (
            "set -euo pipefail; "
            # Pre-flight: bail fast if entire.io isn't reachable.
            "if ! curl -sSfI --connect-timeout 10 --max-time 15 "
            "https://entire.io/install.sh >/dev/null; then "
            "  echo 'entire.io unreachable from this node' >&2; exit 99; "
            "fi; "
            # Strip the hanging curl-bash-post-install line, then bash it.
            "timeout 120 bash -c '"
            "curl -fsSL --connect-timeout 15 --max-time 90 "
            "https://entire.io/install.sh "
            "| sed \"/curl-bash-post-install/d\" "
            "| bash"
            "'"
        )
        try:
            result = await _run_in_thread(
                run,
                ["bash", "-c", cmd],
                check=False,
                timeout=150,
            )
            if result.returncode == 99:
                log.write(
                    f"  [yellow]entire: entire.io unreachable from this HPC node. "
                    f"Install manually: {MANUAL}[/yellow]"
                )
            elif result.returncode != 0:
                stderr = (getattr(result, "stderr", "") or "").strip().splitlines()[-3:]
                log.write(
                    f"  [yellow]entire installer exit {result.returncode}: "
                    f"{' / '.join(stderr) or 'no stderr'}. "
                    f"Install manually: {MANUAL}[/yellow]"
                )
            else:
                entire_bin = shutil.which("entire")
                if entire_bin:
                    safe_symlink(Path(entire_bin), install_dir / "bin" / "entire")
                    log.write("  [green]✓[/green] entire CLI installed")
                    log.write(
                        "  [dim]Note: skipped entire's post-install hook (it hangs on "
                        "HPCs without timeouts). The binary is installed and usable. "
                        "If a feature complains about missing setup, run "
                        "[bold]entire login[/bold] (or whatever it asks for) once.[/dim]"
                    )
                else:
                    log.write(
                        f"  [yellow]entire: install script reported success but "
                        f"`entire` not on PATH; install manually: {MANUAL}[/yellow]"
                    )
        except subprocess.TimeoutExpired:
            log.write(
                f"  [yellow]entire: install exceeded 150s hard cap. "
                f"Install manually: {MANUAL}[/yellow]"
            )
        except Exception as exc:
            log.write(
                f"  [yellow]entire: {exc}. Install manually: {MANUAL}[/yellow]"
            )


def _install_shellcheck(install_dir: Path) -> None:
    """Download shellcheck static binary."""
    import platform
    import tarfile
    import tempfile
    import urllib.request

    arch = platform.machine()
    if arch == "x86_64":
        arch = "x86_64"
    elif arch in ("aarch64", "arm64"):
        arch = "aarch64"
    else:
        raise RuntimeError(f"Unsupported architecture for shellcheck: {arch}")

    system = platform.system().lower()
    url = f"https://github.com/koalaman/shellcheck/releases/download/v0.11.0/shellcheck-v0.11.0.{system}.{arch}.tar.xz"

    dest = install_dir / "tools" / "bin" / "shellcheck"

    if is_dry_run():
        # Simulate the full chain: download → extract → copy → chmod.
        would("network", "urlretrieve", url=url, dest="<tmpdir>/shellcheck.tar.xz")
        would("archive", "extract", archive="<tmpdir>/shellcheck.tar.xz", member="shellcheck")
        dry_run_mkdir(dest.parent)
        would("file_copy", "copy2", src="<tmpdir>/shellcheck", dst=dest, bytes=0)
        would("file_chmod", "chmod", path=dest, mode="0o755")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        archive = Path(tmpdir) / "shellcheck.tar.xz"
        # HPC nodes commonly have a non-default CA bundle (RHEL ships its
        # bundle at /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem and
        # the system Python doesn't always pick it up from $SSL_CERT_FILE
        # when it built without certifi). Build an explicit SSL context
        # that consults SSL_CERT_FILE → SSL_CERT_DIR → the well-known
        # RHEL/CentOS bundle, in that order.
        import ssl

        cafile = os.environ.get("SSL_CERT_FILE")
        capath = os.environ.get("SSL_CERT_DIR")
        if not cafile and not capath:
            for candidate in (
                "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",  # RHEL/Rocky
                "/etc/ssl/certs/ca-certificates.crt",                 # Debian/Ubuntu
                "/etc/ssl/cert.pem",                                  # OpenSSL default
            ):
                if Path(candidate).exists():
                    cafile = candidate
                    break
        ctx = ssl.create_default_context(cafile=cafile, capath=capath)
        with urllib.request.urlopen(url, context=ctx, timeout=120) as resp, \
                open(archive, "wb") as fh:
            shutil.copyfileobj(resp, fh)

        with tarfile.open(str(archive), "r:xz") as tar:
            # Extract shellcheck binary — reject symlinks/hardlinks for safety
            for member in tar.getmembers():
                if member.name.endswith("/shellcheck") or member.name == "shellcheck":
                    if not member.isfile():
                        continue  # Reject symlinks, hardlinks (CVE-2007-4559)
                    member.name = "shellcheck"
                    tar.extract(member, path=tmpdir, filter="data")
                    break

        src = Path(tmpdir) / "shellcheck"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dest))
        dest.chmod(0o755)


async def _install_skills(
    skills: list[str], install_dir: Path, bundled: Path, log: RichLog, *, mode: str = "hpc"
) -> None:
    """Install skills — git clone for external, copy for bundled, extract
    from an HPC shared path for skills in HPC_SHARED_SKILLS."""
    skills_dir = install_dir / "skills"
    dry_run_mkdir(skills_dir)

    for skill in skills:
        if skill in GIT_SKILLS:
            target = skills_dir / skill
            if target.exists():
                log.write(f"  [dim]Skill {skill} already exists, skipping clone[/dim]")
                continue
            url = GIT_SKILLS[skill]
            log.write(f"  Cloning {skill}...")
            try:
                await _run_in_thread(
                    run, ["git", "clone", "--depth", "1", url, str(target)], check=True
                )
                log.write(f"  [green]✓[/green] {skill}")
            except Exception as exc:
                log.write(f"  [red]✗ {skill}: {exc}[/red]")

        elif skill in HPC_SHARED_SKILLS:
            if mode != "hpc":
                log.write(
                    f"  [dim]Skipping {skill} (only available in HPC mode)[/dim]"
                )
                continue
            src_archive = Path(HPC_SHARED_SKILLS[skill])
            dest = skills_dir / skill
            if not src_archive.exists():
                log.write(
                    f"  [yellow]HPC-shared skill {skill} not found at {src_archive} — "
                    "are you on the HPC and is the file readable?[/yellow]"
                )
                continue
            log.write(f"  Fetching {skill} from {src_archive}...")
            try:
                if dest.exists():
                    dry_run_rmtree(dest)
                await _run_in_thread(
                    _extract_skill_archive, src_archive, skills_dir, skill
                )
                log.write(f"  [green]✓[/green] {skill} (from HPC share)")
            except Exception as exc:
                log.write(f"  [red]✗ {skill}: {exc}[/red]")

        elif skill in BUNDLED_SKILLS:
            src = bundled / "skills" / skill
            dest = skills_dir / skill
            if src.exists():
                if dest.exists():
                    dry_run_rmtree(dest)
                dry_run_copytree(src, dest)
                log.write(f"  [green]✓[/green] {skill} (bundled)")
            else:
                log.write(f"  [yellow]Bundled skill {skill} not found at {src}[/yellow]")


def _extract_skill_archive(archive: Path, skills_dir: Path, expected_top: str) -> None:
    """Extract a ``.skill`` (zip) archive into ``skills_dir``.

    ``.skill`` files are plain zip archives produced by
    ``scripts/package_skill.py`` (and by Anthropic's skill-creator). The
    archive must contain a single top-level directory matching
    ``expected_top``. Members escaping the target (absolute paths or ``..``
    components) are rejected for safety.
    """
    import zipfile

    if is_dry_run():
        would(
            "archive",
            "extract",
            archive=archive,
            into=skills_dir,
            top=expected_top,
        )
        return

    skills_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(archive), "r") as zf:
        for info in zf.infolist():
            name = info.filename
            norm = os.path.normpath(name)
            if norm.startswith("..") or os.path.isabs(norm):
                raise ValueError(f"Refusing unsafe path in archive: {name}")
            top = norm.split(os.sep, 1)[0]
            if top != expected_top:
                raise ValueError(
                    f"Archive top-level {top!r} does not match expected {expected_top!r}"
                )
        zf.extractall(path=str(skills_dir))


async def _install_hooks(
    hooks: list[str], install_dir: Path, bundled: Path, log: RichLog
) -> None:
    """Copy hook scripts to install dir."""
    hooks_dir = install_dir / "hooks"
    dry_run_mkdir(hooks_dir)

    for hook in hooks:
        script_name = HOOK_SCRIPTS.get(hook)
        if not script_name:
            continue
        src = bundled / "hooks" / script_name
        dest = hooks_dir / script_name
        if src.exists():
            dry_run_copy(src, dest)
            log.write(f"  [green]✓[/green] {script_name}")
        else:
            log.write(f"  [yellow]Hook {script_name} not found at {src}[/yellow]")

    # Also copy deny_rules.json
    deny_src = bundled / "hooks" / "deny_rules.json"
    if deny_src.exists():
        dry_run_copy(deny_src, hooks_dir / "deny_rules.json")
        log.write("  [green]✓[/green] deny_rules.json")


async def _install_config(
    install_dir: Path, bundled: Path, log: RichLog, *, mode: str = "hpc"
) -> None:
    """Copy config files (AGENTS.md, templates, MCP example)."""
    # AGENTS.md — select based on mode
    if mode == "local":
        agents_md_src = bundled / "config" / "AGENTS.md"
    else:
        agents_md_src = bundled / "config" / "AGENTS_HPC.md"
    agents_md_dest = install_dir / "config" / "AGENTS.md"
    if agents_md_src.exists():
        dry_run_copy(agents_md_src, agents_md_dest)
        log.write(f"  [green]✓[/green] AGENTS.md ({mode} version)")

    # Template
    tmpl_src = bundled / "config" / "templates" / "PROJECT_LOCAL_AGENTS_TEMPLATE.md"
    tmpl_dest = install_dir / "config" / "templates" / "PROJECT_LOCAL_AGENTS_TEMPLATE.md"
    dry_run_mkdir(tmpl_dest.parent)
    if tmpl_src.exists():
        dry_run_copy(tmpl_src, tmpl_dest)
        log.write("  [green]✓[/green] PROJECT_LOCAL_AGENTS_TEMPLATE.md")

    # MCP example
    mcp_src = bundled / "config" / "mcp" / "servers.json.example"
    mcp_dest = install_dir / "config" / "mcp" / "servers.json.example"
    dry_run_mkdir(mcp_dest.parent)
    if mcp_src.exists():
        dry_run_copy(mcp_src, mcp_dest)
        # If no servers.json exists yet, create from example
        servers_json = install_dir / "config" / "mcp" / "servers.json"
        if not servers_json.exists():
            dry_run_copy(mcp_src, servers_json)
        log.write("  [green]✓[/green] MCP config")


async def _install_vscode_extensions(
    state: InstallerState, install_dir: Path, log: RichLog
) -> None:
    """Always emit a vscode-extensions.json recommendation file. Optionally
    auto-install via the `code` CLI (only in local mode and only if the user
    opted in via the Switch). On HPC the user installs extensions in their
    local VSCode and Remote-SSH mirrors them."""
    from coding_agents.agents import agents_with_vscode_ext

    exts = agents_with_vscode_ext(state.agents)
    if not exts:
        log.write("  [dim]No selected agents publish a VSCode extension[/dim]")
        return

    # Always write the recommendation file — VSCode reads .vscode/extensions.json
    # and prompts to install missing recommendations on workspace open.
    ext_ids = [ext_id for _, ext_id in exts]
    recommendations = {
        "recommendations": ext_ids,
        "_comment": (
            "Auto-generated by coding-agents installer. To install in your "
            "local VSCode: open Command Palette → 'Extensions: Show "
            "Recommended Extensions', or copy this list into "
            ".vscode/extensions.json in your project root."
        ),
        "_marketplace_urls": [
            f"https://marketplace.visualstudio.com/items?itemName={ext_id}"
            for ext_id in ext_ids
        ],
    }
    ext_json = install_dir / "vscode-extensions.json"
    dry_run_write_text(ext_json, json.dumps(recommendations, indent=2) + "\n")
    log.write(f"  [green]✓[/green] Wrote {ext_json}")

    if not state.vscode_extensions:
        # User opted out (HPC mode always opts out — they install locally).
        log.write(
            "  [dim]Skipping auto-install — install these extensions in your "
            "[bold]local[/bold] VSCode (Remote-SSH mirrors them to the cluster):[/dim]"
        )
        for ext_id in ext_ids:
            log.write(f"    • {ext_id}")
        return

    code_bin = shutil.which("code")
    if not code_bin:
        log.write(
            "  [yellow]`code` not on PATH — wrote recommendation file only.[/yellow]"
        )
        return

    for agent_key, ext_id in exts:
        try:
            await _run_in_thread(
                run, [code_bin, "--install-extension", ext_id], check=False
            )
            log.write(f"  [green]✓[/green] {ext_id} (auto-installed)")
        except Exception as exc:
            log.write(f"  [yellow]{ext_id}: {exc}[/yellow]")


async def _create_sandbox_wrappers(state, install_dir: Path, log: RichLog) -> None:
    """Create agent-<key> Apptainer sandbox wrapper scripts in bin/.

    Renders bundled/templates/wrapper/agent.template.sh per agent. The
    template's variable list is pinned in sandbox_wrappers.WRAPPER_VARS;
    drift between the template and the renderer is detected by tests.
    """
    from coding_agents.installer.sandbox_wrappers import (
        load_template,
        render_wrapper,
    )

    bin_dir = install_dir / "bin"
    dry_run_mkdir(bin_dir)

    template = load_template()
    # Sort for deterministic / idempotent generation order.
    for agent_key in sorted(state.agents):
        agent = AGENTS[agent_key]
        wrapper_name = f"agent-{agent_key}"
        wrapper_path = bin_dir / wrapper_name
        script = render_wrapper(
            template,
            agent_key=agent_key,
            agent_display_name=agent["display_name"],
            agent_binary=agent["binary"],
            default_sif_path=state.sandbox_sif_path,
        )
        dry_run_write_text(wrapper_path, script, mode=0o755)
        log.write(f"  [green]✓[/green] {wrapper_name}")


async def _bootstrap_user_dirs(state, log: RichLog) -> None:
    """Create per-user agent-secrets/ and agent-logs/ dirs (mode 0700) and
    write the SIF sha256 sidecar.

    Resolves $USER into sandbox_secrets_dir/sandbox_logs_dir if blank.
    Computes ${SIF_REAL}.sha256 sidecar so the wrapper hot path skips
    hashing per invocation (perf-oracle finding).
    """
    import getpass
    import hashlib

    user = getpass.getuser()
    if not state.sandbox_secrets_dir:
        state.sandbox_secrets_dir = f"/hpc/compgen/users/{user}/agent-secrets"
    if not state.sandbox_logs_dir:
        state.sandbox_logs_dir = f"/hpc/compgen/users/{user}/agent-logs"

    for label, p in (
        ("secrets", state.sandbox_secrets_path),
        ("logs", state.sandbox_logs_path),
    ):
        try:
            dry_run_mkdir(p, mode=0o700)
            log.write(f"  [green]✓[/green] agent-{label} dir: {p}")
        except OSError as exc:
            log.write(
                f"  [yellow]⚠ agent-{label} dir {p}: {exc} "
                f"(parent must exist; ask hpcsupport if not)[/yellow]"
            )

    # SIF sha256 sidecar (cached at install; wrapper reads in <1ms)
    sif_p = state.sandbox_sif_path_p
    if sif_p.exists():
        from coding_agents.dry_run import is_dry_run, would
        sif_real = sif_p.resolve()
        sidecar = sif_real.with_suffix(sif_real.suffix + ".sha256")
        if is_dry_run():
            would("sif_sha", "sha256_sidecar", path=sidecar, source=sif_real)
        else:
            try:
                digest = hashlib.sha256(sif_real.read_bytes()).hexdigest()
                sidecar.write_text(digest + "\n")
                sidecar.chmod(0o644)
                log.write(f"  [green]✓[/green] SIF sha256 sidecar: {sidecar.name}")
            except (OSError, PermissionError) as exc:
                log.write(
                    f"  [yellow]⚠ Could not write SIF sha sidecar to {sidecar}: "
                    f"{exc}[/yellow]"
                )
    else:
        log.write(
            f"  [yellow]⚠ SIF not yet readable at {sif_p} "
            "(lab admin must build & copy; doctor will verify later)[/yellow]"
        )


async def _emit_managed_policy(state, bundled: Path, log: RichLog) -> None:
    """Emit Claude ~/.claude/settings.json + Codex ~/.codex/config.toml from
    the single-source bundled/hooks/deny_rules.json.

    NOTE: ~/.claude/settings.json is user-overridable, NOT enforced.
    True enforcement requires writing /etc/claude-code/managed-settings.json
    (root needed; v2 D5).
    """
    from coding_agents.installer.policy_emit import (
        install_codex_deny_paths,
        install_managed_claude_settings,
    )

    home = Path.home()
    deny_rules_path = bundled / "hooks" / "deny_rules.json"
    template_path = bundled / "templates" / "managed-claude-settings.json"

    if "claude" in state.agents:
        if template_path.exists() and deny_rules_path.exists():
            target = home / ".claude" / "settings.json"
            install_managed_claude_settings(template_path, deny_rules_path, target)
            log.write(f"  [green]✓[/green] Claude managed settings: {target}")
            # Sprint 1 Task 1.8: surface the user-overridable caveat at
            # install time so users aren't surprised when a project-local
            # .claude/settings.json silently overrides our deny rules.
            # True org-managed enforcement requires
            # /etc/claude-code/managed-settings.json (hpcsupport ticket
            # tracked in docs/v2-deferred.md item D5).
            true_managed = Path("/etc/claude-code/managed-settings.json")
            if not true_managed.exists():
                log.write(
                    "    [yellow]ℹ Note: ~/.claude/settings.json is user-overridable. "
                    "A repo-local .claude/settings.json silently overrides the deny rules emitted "
                    "above. True org-managed enforcement (uneditable from user space) requires the "
                    "lab admin to install /etc/claude-code/managed-settings.json — open a "
                    "hpcsupport ticket if you need that level of lockdown.[/yellow]"
                )
        else:
            log.write("  [yellow]⚠ Claude template or deny_rules missing; skipping[/yellow]")

    if "codex" in state.agents:
        if deny_rules_path.exists():
            target = home / ".codex" / "config.toml"
            install_codex_deny_paths(deny_rules_path, target)
            log.write(f"  [green]✓[/green] Codex sandbox config: {target}")
        # Codex hooks (experimental upstream — feature flag gates them).
        from coding_agents.installer.policy_emit import install_codex_hooks
        hooks_target = install_codex_hooks(state.install_path, state.hooks)
        if hooks_target is not None:
            log.write(f"  [green]✓[/green] Codex hooks: {hooks_target}")

    if "opencode" in state.agents and deny_rules_path.exists():
        # OpenCode v1.1.1+ unified `permission` schema. Apptainer constrains
        # blast radius via bind-mounts; permission rules add prompt-time gates.
        from coding_agents.installer.policy_emit import install_opencode_permissions
        deny_data = json.loads(deny_rules_path.read_text())
        canonical_rules = deny_data.get("deny", [])
        opencode_target = install_opencode_permissions(canonical_rules)
        if opencode_target is not None:
            log.write(f"  [green]✓[/green] OpenCode permissions: {opencode_target}")


async def _emit_vscode_extension_wrappers(
    state, install_dir: Path, log: RichLog
) -> None:
    """Emit per-extension wrapper stubs + the shared agent-vscode helper +
    merge wrapper hooks into the user's VSCode settings.json.

    Wrap-eligible agents are those in ``state.agents`` that intersect with
    the four supported VSCode extensions (Claude, Codex, OpenCode, Pi).
    """
    from coding_agents.installer.policy_emit import emit_managed_vscode_settings
    from coding_agents.installer.wrapper_vscode import (
        emit_agent_vscode_helper,
        emit_extension_stubs,
        emit_path_shim,
    )

    wrappable = {"claude", "codex", "opencode", "pi"}
    agents = sorted(set(state.agents) & wrappable)
    if not agents:
        log.write("  [dim]No wrappable agents in selection — skipping VSCode wrappers[/dim]")
        return

    helper = emit_agent_vscode_helper(install_dir)
    log.write(f"  [green]✓[/green] agent-vscode helper: {helper}")

    written = emit_extension_stubs(install_dir, agents)
    for path in written:
        log.write(f"  [green]✓[/green] {path.name}")

    if "opencode" in agents:
        shim = emit_path_shim(install_dir)
        log.write(f"  [green]✓[/green] OpenCode path-shim: {shim}")

    settings_path = emit_managed_vscode_settings(install_dir, agents)
    if settings_path is None:
        log.write(
            "  [yellow]⚠ No VSCode settings.json found yet — connect VSCode "
            "to this host then run `coding-agents sync` to wire wrapper hooks.[/yellow]"
        )
    else:
        log.write(f"  [green]✓[/green] VSCode wrapper hooks: {settings_path}")
