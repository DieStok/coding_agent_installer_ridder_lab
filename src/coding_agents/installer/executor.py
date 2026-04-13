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


async def execute_install(state: InstallerState, log: RichLog) -> None:
    """Execute the full installation based on user selections."""
    install_dir = state.install_path
    _log.info("execute_install: mode=%s, install_dir=%s, agents=%s, tools=%s, skills=%s",
              state.mode, install_dir, state.agents, state.tools, state.skills)

    # --- 0. Backup existing installations ---
    log.write("[bold]Checking for existing installations...[/bold]")
    await _backup_existing(state.agents, log)

    # Create directory structure
    log.write("\n[bold]Creating directory structure...[/bold]")
    for subdir in ["bin", "config", "config/mcp", "config/templates", "hooks",
                    "jai", "skills", "tools", "tools/bin", "logs", "node_modules"]:
        dry_run_mkdir(install_dir / subdir)

    bundled = _bundled_dir()

    # --- 1. Install agents ---
    log.write("\n[bold]Installing agents...[/bold]")
    for agent_key in state.agents:
        agent = AGENTS[agent_key]
        log.write(f"  Installing {agent['display_name']}...")
        try:
            await _install_agent(agent_key, agent, install_dir, log)
            log.write(f"  [green]✓[/green] {agent['display_name']}")
        except Exception as exc:
            log.write(f"  [red]✗ {agent['display_name']}: {exc}[/red]")

    # --- 2. Install tools ---
    if state.tools:
        log.write("\n[bold]Installing tools...[/bold]")
        await _install_tools(state.tools, install_dir, log)

    # --- 3. Install skills ---
    if state.skills:
        log.write("\n[bold]Installing skills...[/bold]")
        await _install_skills(state.skills, install_dir, bundled, log)

    # --- 4. Copy hooks ---
    if state.hooks:
        log.write("\n[bold]Installing hooks...[/bold]")
        await _install_hooks(state.hooks, install_dir, bundled, log)

    # --- 5. Copy jai configs (HPC only) ---
    if state.jai_enabled and state.mode != "local":
        log.write("\n[bold]Preparing jai sandbox configs...[/bold]")
        await _install_jai(state.agents, install_dir, bundled, log)
    elif state.mode == "local":
        log.write("\n[dim]Skipping jai sandbox (local mode)[/dim]")

    # --- 6. Copy config files (mode-aware AGENTS.md) ---
    log.write("\n[bold]Copying configuration files...[/bold]")
    await _install_config(install_dir, bundled, log, mode=state.mode)

    # --- 7. VSCode extensions ---
    if state.vscode_extensions:
        log.write("\n[bold]Installing VSCode extensions...[/bold]")
        await _install_vscode_extensions(state.agents, install_dir, log)

    # --- 8. Create jai wrapper scripts (HPC only) ---
    if state.mode != "local":
        log.write("\n[bold]Creating jai wrapper scripts...[/bold]")
        await _create_jai_wrappers(state.agents, install_dir, log)

    # --- 9. Shell integration ---
    log.write("\n[bold]Setting up shell integration...[/bold]")
    modified = await _run_in_thread(inject_shell_block, install_dir)
    for f in modified:
        log.write(f"  [green]✓[/green] Updated {f}")

    # --- 10. Smart-merge existing settings ---
    log.write("\n[bold]Merging settings with existing configs...[/bold]")
    await _merge_existing_settings(state, install_dir, log)

    # --- 11. Save config ---
    config = state.to_config_dict()
    mark_installed(config)
    log.write(f"\n[green]✓[/green] Config saved to ~/.coding-agents.json")


async def _backup_existing(agents: list[str], log: RichLog) -> None:
    """Back up existing agent config directories to .tar.gz."""
    _log.debug("backup_existing: scanning for agents=%s", agents)
    from coding_agents.detect_existing import scan_existing, backup_agent_dir

    inventory = scan_existing()
    if not inventory.has_existing:
        log.write("  [dim]No existing installations found[/dim]")
        return

    for inv in inventory.existing_agents:
        if inv.agent_key in agents:
            log.write(
                f"  {inv.display_name}: {inv.file_count} files "
                f"({inv.human_size()}) in {inv.config_dir}"
            )
            log.write(f"    Files:\n{inv.tree_display(max_files=10)}")
            backup_path = await _run_in_thread(backup_agent_dir, inv)
            if backup_path:
                log.write(f"    [green]✓[/green] Backed up to {backup_path}")
            else:
                log.write(f"    [dim]No backup needed[/dim]")


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
    """Install a single agent."""
    method = agent["method"]
    _log.info("install_agent: %s (method=%s, package=%s)", key, method, agent.get("package", "N/A"))

    if method == "npm":
        await _run_in_thread(npm_install, install_dir, agent["package"])
        # Verify binary exists
        bin_path = install_dir / "node_modules" / ".bin" / agent["binary"]
        if not bin_path.exists():
            raise FileNotFoundError(f"Binary not found after install: {bin_path}")

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

        # Install and configure claude-statusbar status line
        if key == "claude":
            await _install_claude_statusbar(log)

    # Post-install actions (e.g., Pi extensions)
    for cmd_str in agent.get("post_install", []):
        try:
            await _run_in_thread(run, shlex.split(cmd_str), check=False)
            log.write(f"    [dim]post-install: {cmd_str}[/dim]")
        except Exception:
            log.write(f"    [yellow]post-install skipped: {cmd_str}[/yellow]")


async def _install_claude_statusbar(log: RichLog) -> None:
    """Install claude-statusbar via uv tool, install its deps, and wire up
    the statusLine entry in ~/.claude/settings.json."""
    log.write("    Installing claude-statusbar...")
    try:
        await _run_in_thread(run, ["uv", "tool", "install", "claude-statusbar"], check=False)
    except Exception as exc:
        log.write(f"    [yellow]uv tool install claude-statusbar: {exc}[/yellow]")
        return

    try:
        await _run_in_thread(run, ["cs", "--install-deps"], check=False)
    except Exception as exc:
        log.write(f"    [yellow]cs --install-deps: {exc}[/yellow]")

    settings_path = Path.home() / ".claude" / "settings.json"
    dry_run_mkdir(settings_path.parent)
    existing: dict = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError):
            existing = {}

    existing["statusLine"] = {"type": "command", "command": "cs --hide-pet"}

    from coding_agents.utils import secure_write_text
    secure_write_text(settings_path, json.dumps(existing, indent=2) + "\n")
    log.write(f"    [green]✓[/green] statusLine configured in {settings_path}")


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
        log.write("  Installing entire CLI...")
        try:
            await _run_in_thread(
                run,
                ["bash", "-c", "curl -fsSL https://entire.io/install.sh | bash"],
                check=False,
            )
            # Disable telemetry
            entire_bin = shutil.which("entire")
            if entire_bin:
                await _run_in_thread(run, ["entire", "enable", "--telemetry=false"], check=False)
                safe_symlink(Path(entire_bin), install_dir / "bin" / "entire")
            log.write("  [green]✓[/green] entire CLI installed")
        except Exception as exc:
            log.write(f"  [yellow]entire: {exc}[/yellow]")


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
        urllib.request.urlretrieve(url, str(archive))

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
    skills: list[str], install_dir: Path, bundled: Path, log: RichLog
) -> None:
    """Install skills — git clone for external, copy for bundled."""
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


async def _install_jai(
    agents: list[str], install_dir: Path, bundled: Path, log: RichLog
) -> None:
    """Copy jai config files."""
    jai_dir = install_dir / "jai"
    dry_run_mkdir(jai_dir)

    # Copy .defaults
    defaults_src = bundled / "jai" / ".defaults"
    if defaults_src.exists():
        dry_run_copy(defaults_src, jai_dir / ".defaults")
        log.write("  [green]✓[/green] .defaults")

    # Copy per-agent configs
    for agent_key in agents:
        conf_name = AGENTS[agent_key]["jai_conf"]
        src = bundled / "jai" / conf_name
        if src.exists():
            dry_run_copy(src, jai_dir / conf_name)
            log.write(f"  [green]✓[/green] {conf_name}")


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
    agents: list[str], install_dir: Path, log: RichLog
) -> None:
    """Install VSCode extensions via code CLI or write extensions.json."""
    from coding_agents.agents import agents_with_vscode_ext

    exts = agents_with_vscode_ext(agents)
    if not exts:
        return

    code_bin = shutil.which("code")
    if code_bin:
        for agent_key, ext_id in exts:
            try:
                await _run_in_thread(
                    run, [code_bin, "--install-extension", ext_id], check=False
                )
                log.write(f"  [green]✓[/green] {ext_id}")
            except Exception as exc:
                log.write(f"  [yellow]{ext_id}: {exc}[/yellow]")
    else:
        log.write("  [yellow]`code` not on PATH — writing extensions.json for manual install[/yellow]")


async def _create_jai_wrappers(agents: list[str], install_dir: Path, log: RichLog) -> None:
    """Create jai-<agent> wrapper scripts in bin/."""
    bin_dir = install_dir / "bin"
    dry_run_mkdir(bin_dir)

    for agent_key in agents:
        agent = AGENTS[agent_key]
        wrapper_name = f"jai-{agent_key}"
        wrapper_path = bin_dir / wrapper_name
        binary = agent["binary"]
        jai_conf = agent["jai_conf"]

        script = f"""#!/usr/bin/env bash
# jai wrapper for {agent['display_name']}
# Falls back to running without sandbox if jai is not available.
if command -v jai &>/dev/null; then
    exec jai -c "$JAI_CONFIG_DIR/{jai_conf}" -- {binary} "$@"
else
    echo "⚠️  jai not available — running {binary} without sandbox" >&2
    exec {binary} "$@"
fi
"""
        dry_run_write_text(wrapper_path, script, mode=0o755)
        log.write(f"  [green]✓[/green] {wrapper_name}")
