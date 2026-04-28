"""uninstall command — clean removal of all installed components."""
from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from coding_agents.agents import AGENTS
from coding_agents.config import CONFIG_PATH, load_config, get_install_dir
from coding_agents.dry_run import is_dry_run, would
from coding_agents.installer.fs_ops import dry_run_rmtree, dry_run_unlink
from coding_agents.utils import remove_shell_block

console = Console()


def _restore_backup(target: Path) -> bool:
    """Rename ``<target>.bak`` back to ``target`` if it exists.

    ``safe_symlink`` creates the .bak when it replaces a real file with a
    symlink, so this is the inverse for any agent's instruction file
    (CLAUDE.md, AGENTS.md, GEMINI.md). Returns True if a backup was
    restored.
    """
    backup = target.with_suffix(target.suffix + ".bak")
    if not backup.exists():
        return False
    if is_dry_run():
        would("file_rename", "restore_backup", src=backup, dst=target)
        return True
    if target.exists() or target.is_symlink():
        # Symlink should already be gone by this point in uninstall, but
        # guard against re-entry: don't clobber a real file the user put
        # back themselves.
        if target.is_symlink():
            target.unlink()
        else:
            return False
    backup.rename(target)
    return True


# Template-introduced top-level keys that ``install_managed_claude_settings``
# writes from ``bundled/templates/managed-claude-settings.json``. On
# uninstall we delete each one *only when its current value still matches
# the install-time default* — if the user changed the value post-install,
# leave their edit alone. The ``_comment`` field is a prefix-match because
# the exact wording can drift across releases. Update this list in lockstep
# with the template.
_TEMPLATE_KEY_DEFAULTS: list[tuple[str, object]] = [
    ("_comment", "Default Claude Code settings emitted by coding-agents installer"),
    ("allowManagedMcpServersOnly", True),
    ("permissions.disableBypassPermissionsMode", "disable"),
    ("sandbox.failIfUnavailable", True),
]


def _restore_oldest_settings_backup() -> Path | None:
    """Restore the oldest ``~/.claude/settings.backup-YYYY-MM-DD.json``.

    ``policy_emit._backup_if_drifted`` writes one dated backup per day
    before overwriting ``~/.claude/settings.json`` from the template. The
    *oldest* dated backup is the user's pre-install version (later
    backups are post-install re-installs); restoring it is the most
    faithful inverse of install. Returns the source path if restored,
    ``None`` if no backup exists.

    The other dated backups are left in place so the user can inspect
    them if curious; cleaning them up would be guesswork.
    """
    home = Path.home()
    target = home / ".claude" / "settings.json"
    backups = sorted((home / ".claude").glob("settings.backup-*.json"))
    if not backups:
        return None
    oldest = backups[0]
    if is_dry_run():
        would("file_rename", "restore_settings_backup", src=oldest, dst=target)
        return oldest
    target.write_text(oldest.read_text())
    oldest.unlink()
    return oldest


def _strip_template_keys(path: Path) -> int:
    """Remove template-introduced keys whose value still matches install
    defaults. Returns the count removed.

    Surgical inverse of ``install_managed_claude_settings`` for the case
    where no dated backup exists (user had no ``settings.json`` before
    install, so the install path wrote a fresh file from the template
    rather than backing one up).
    """
    if not path.exists():
        return 0
    try:
        data: dict = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return 0

    removed = 0
    for key_path, expected in _TEMPLATE_KEY_DEFAULTS:
        parts = key_path.split(".")
        parent: object = data
        for p in parts[:-1]:
            if not isinstance(parent, dict) or p not in parent:
                parent = None
                break
            parent = parent[p]
        if not isinstance(parent, dict):
            continue
        leaf = parts[-1]
        if leaf not in parent:
            continue
        actual = parent[leaf]
        if key_path == "_comment":
            # Prefix match — the exact wording may drift across releases.
            matches = isinstance(actual, str) and isinstance(expected, str) \
                and actual.startswith(expected)
        else:
            matches = actual == expected
        if matches:
            del parent[leaf]
            removed += 1

    if removed == 0:
        return 0

    if is_dry_run():
        would("json_merge", "strip_template_keys", path=path, removed=removed)
        return removed

    from coding_agents.utils import secure_write_text
    secure_write_text(path, json.dumps(data, indent=2) + "\n")
    return removed


def _unmerge_settings_json(install_dir: Path) -> None:
    """Revert coding-agents writes to user JSON config files.

    Three layers of cleanup, in order:
      1. If ``~/.claude/settings.backup-YYYY-MM-DD.json`` exists, restore
         the oldest one — that's the user's pre-install settings.json. Skip
         the marker-strip + template-key strip for that file since the
         restored content predates both.
      2. Otherwise, strip marker-tagged entries (hooks, deny rules) and
         null template-introduced keys whose values still match defaults.
      3. Always strip marker-tagged ``mcpServers`` from ``~/.mcp.json``.
    """
    from coding_agents.merge_settings import unmerge_marked_entries

    home = Path.home()
    settings_path = home / ".claude" / "settings.json"
    mcp_path = home / ".mcp.json"

    restored = _restore_oldest_settings_backup()
    if restored:
        console.print(
            f"  [green]✓[/green] Restored {restored.name} → {settings_path.name}"
        )

    deny_strings: list[str] | None = None
    deny_path = install_dir / "hooks" / "deny_rules.json"
    if deny_path.exists():
        try:
            deny_data = json.loads(deny_path.read_text())
            deny_strings = deny_data.get("deny", []) or None
        except (json.JSONDecodeError, OSError):
            deny_strings = None

    targets: list[tuple[Path, str, list[str] | None]] = [
        (mcp_path, "mcpServers", None),
    ]
    if not restored:
        targets.extend([
            (settings_path, "hooks.SessionStart", None),
            (settings_path, "hooks.Stop", None),
            (settings_path, "permissions.deny", deny_strings),
        ])

    for path, section, strings in targets:
        result = unmerge_marked_entries(
            path, section, string_entries_to_remove=strings
        )
        if result and result.added_keys:
            console.print(
                f"  [green]✓[/green] {path.name} {section}: "
                f"removed {len(result.added_keys)}, "
                f"preserved {len(result.preserved_keys)}"
            )

    if not restored:
        stripped = _strip_template_keys(settings_path)
        if stripped:
            console.print(
                f"  [green]✓[/green] {settings_path.name}: "
                f"removed {stripped} template-introduced keys"
            )


def run_uninstall() -> None:
    """Remove all coding-agents components, symlinks, and shell integration."""
    config = load_config()
    if not config.get("install_dir"):
        console.print("[yellow]No installation found (no ~/.coding-agents.json).[/yellow]")
        return

    install_dir = get_install_dir(config)
    agents = config.get("agents", [])
    home = Path.home()

    console.print("[bold]Uninstalling coding-agents...[/bold]\n")

    # 1. Remove symlinks from agent config dirs
    console.print("[bold]Removing agent config symlinks...[/bold]")
    for key in agents:
        agent = AGENTS.get(key)
        if not agent:
            continue

        config_dir = Path(agent["config_dir"]).expanduser()
        instr_file = config_dir / agent["instruction_file"]
        if instr_file.is_symlink():
            dry_run_unlink(instr_file)
            console.print(f"  [green]✓[/green] Removed {instr_file}")
        if _restore_backup(instr_file):
            console.print(
                f"  [green]✓[/green] Restored {instr_file}.bak → {instr_file.name}"
            )

        # Remove skill symlinks
        if agent.get("skills_dir"):
            skills_pattern = agent["skills_dir"]
            # Check for our symlinks in the skills dir
            skills_parent = Path(skills_pattern.split("{name}")[0]).expanduser()
            if skills_parent.exists():
                for item in skills_parent.iterdir():
                    if item.is_symlink() and str(install_dir) in str(item.resolve()):
                        dry_run_unlink(item)
                        console.print(f"  [green]✓[/green] Removed skill symlink {item}")

    # 2. Remove agent-* sandbox wrapper shims
    console.print("[bold]Removing agent-* sandbox wrappers...[/bold]")
    bin_dir = install_dir / "bin"
    if bin_dir.exists():
        for item in bin_dir.iterdir():
            if item.name.startswith("agent-") and item.is_file():
                dry_run_unlink(item)
                console.print(f"  [green]✓[/green] Removed {item}")

    # 2b. Strip coding-agents-managed entries from user JSON config files.
    # Done before the install-dir prompt so we can still read the canonical
    # deny_rules.json (string entries in permissions.deny can't carry markers).
    console.print("[bold]Removing managed settings entries...[/bold]")
    _unmerge_settings_json(install_dir)

    # 3. Remove shell integration
    console.print("[bold]Removing shell integration...[/bold]")
    modified = remove_shell_block()
    for f in modified:
        console.print(f"  [green]✓[/green] Cleaned {f}")

    # 3b. VSCode wrapper hook cleanup — settings.json keys + jobid cache.
    # The user's settings.json keeps their non-managed keys; we set ours to
    # null so VSCode treats them as unset. The jobid cache + any live SLURM
    # session is cleared via the same path as `vscode-reset`.
    console.print("[bold]Removing VSCode wrapper hooks...[/bold]")
    try:
        from coding_agents.installer.policy_emit import unset_managed_vscode_settings
        from coding_agents.commands.vscode_reset import run_vscode_reset
        cleared = unset_managed_vscode_settings()
        if cleared is not None:
            console.print(f"  [green]✓[/green] Cleared wrapper keys in {cleared}")
        run_vscode_reset()
    except Exception as exc:
        console.print(f"  [yellow]⚠ VSCode wrapper cleanup partial: {exc}[/yellow]")

    # 4. Prompt to delete install dir (requires interactive terminal)
    import sys

    console.print(f"\n[bold yellow]Delete {install_dir}?[/bold yellow]")
    console.print("This removes all agents, tools, skills, and node_modules.")
    if is_dry_run():
        would(
            "prompt",
            "confirm_delete_install_dir",
            question="Type 'yes' to confirm",
            would_answer="no (dry-run default)",
        )
        answer = ""
    elif not sys.stdin.isatty():
        console.print("  [dim]Non-interactive — skipping install dir deletion[/dim]")
        answer = ""
    else:
        try:
            answer = input("Type 'yes' to confirm: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""

    if answer == "yes":
        console.print(f"Removing {install_dir} (this may take a moment for node_modules)...")
        try:
            dry_run_rmtree(install_dir)
            console.print(f"  [green]✓[/green] Deleted {install_dir}")
        except Exception as exc:
            console.print(f"  [red]✗ Failed to delete: {exc}[/red]")
    else:
        console.print(f"  [dim]Skipped — {install_dir} retained[/dim]")

    # 5. Remove config file
    if CONFIG_PATH.exists():
        dry_run_unlink(CONFIG_PATH)
        console.print(f"  [green]✓[/green] Removed {CONFIG_PATH}")

    console.print("\n[green bold]Uninstall complete.[/green bold]")
    console.print(
        "[dim]Note: Claude Code at ~/.claude/bin/ was not removed — "
        "run `claude uninstall` separately if needed.[/dim]"
    )
    console.print(
        "[dim]Project-level configs (.claude/settings.json in project dirs) "
        "were not removed — they may contain your customizations.[/dim]"
    )
