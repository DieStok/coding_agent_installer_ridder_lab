"""Emit per-agent policy files from the single-source deny_rules.json.

Two consumers:
- Claude Code: ``~/.claude/settings.json`` (managed-default, NOT enforced —
  v2 D5 will write to ``/etc/claude-code/managed-settings.json`` for true
  enforcement; until then the user can override).
- Codex CLI: ``~/.codex/config.toml`` — ``sandbox_mode = "workspace-write"``
  plus the ``[sandbox_workspace_write]`` table. Synthesis §3.7 / Sprint 1
  Task 1.4: the previous emit wrote ``[sandbox] deny_paths``, which is a
  fictional key (no such schema exists in any 2026 Codex version); Codex
  silently ignored it. The real schema gates network access via
  ``network_access`` (boolean) and exposes ``exclude_tmpdir_env_var`` /
  ``exclude_slash_tmp`` for /tmp control. ``writable_roots`` is automatic
  for the cwd; no extras needed for normal HPC use.

The Claude path uses pure JSON; the Codex path uses ``tomllib`` (read) +
``tomli_w`` (write) so existing user keys are preserved across re-emit.

Both emitters back up the existing file with a ``.backup-YYYY-MM-DD``
suffix when its content differs from the about-to-write content. This
matches the behaviour described in the plan §4.1 Phase 3.
"""
from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("coding-agents")


def _today_suffix() -> str:
    return datetime.date.today().isoformat()


def _backup_if_drifted(path: Path, new_content: str) -> Path | None:
    """If ``path`` exists and content differs from ``new_content``, copy it
    to ``path.with_suffix(f".backup-{today}{path.suffix}")``. Idempotent.

    Honors dry-run: in dry-run, logs the would-be backup instead of writing.
    """
    from coding_agents.dry_run import is_dry_run, would

    if not path.exists():
        return None
    existing = path.read_text()
    if existing == new_content:
        return None
    backup = path.with_name(f"{path.stem}.backup-{_today_suffix()}{path.suffix}")
    if is_dry_run():
        would("file_write", "policy_backup", path=backup, source=path, bytes=len(existing))
        return backup
    backup.write_text(existing)
    log.info("Backed up drifted %s → %s", path, backup)
    return backup


def merge_claude_settings(template: dict[str, Any], deny_rules: dict[str, Any]) -> dict[str, Any]:
    """Pure: merge deny_rules into template's permissions.deny."""
    out = json.loads(json.dumps(template))  # deep copy via JSON round-trip
    out.pop("_comment", None)
    deny = deny_rules.get("claude_code_permissions", {}).get("deny", [])
    out.setdefault("permissions", {}).setdefault("deny", [])
    # Preserve order, dedupe
    seen = set(out["permissions"]["deny"])
    for entry in deny:
        if entry not in seen:
            out["permissions"]["deny"].append(entry)
            seen.add(entry)
    return out


def merge_codex_sandbox_config(existing_toml: dict[str, Any]) -> dict[str, Any]:
    """Pure: ensure existing_toml has the canonical Codex sandbox schema.

    Writes ``sandbox_mode = "workspace-write"`` (the typical agent-edit
    use-case; alternatives are ``"read-only"`` for full lockdown and
    ``"danger-full-access"`` for unsandboxed) plus the
    ``[sandbox_workspace_write]`` table with:
      - ``network_access = true`` — agents routinely need outbound HTTP for
        npm install, pip install, model API calls. Apptainer's --containall
        does not block egress at the kernel level either, so a `false` here
        would create a useless inconsistency. (User decision 2026-04-27;
        users wanting full network lockdown should set
        ``sandbox_mode = "read-only"``.)
      - ``exclude_tmpdir_env_var = false`` — keep $TMPDIR writable
      - ``exclude_slash_tmp = false`` — keep /tmp writable

    Preserves all other top-level keys in the user's existing TOML and
    any custom keys inside ``[sandbox_workspace_write]`` we don't manage.

    The legacy ``[sandbox] deny_paths = [...]`` key — written by previous
    versions of this code — is silently dropped on re-emit since it has
    no effect in any real Codex version (synthesis §3.7).
    """
    out = json.loads(json.dumps(existing_toml))  # deep copy

    # Drop the fictional [sandbox] deny_paths if present (legacy cleanup).
    legacy_sandbox = out.get("sandbox")
    if isinstance(legacy_sandbox, dict) and "deny_paths" in legacy_sandbox:
        legacy_sandbox.pop("deny_paths", None)
        # If the [sandbox] table is now empty, drop it entirely so we
        # don't leave a vestigial section.
        if not legacy_sandbox:
            out.pop("sandbox", None)

    out["sandbox_mode"] = "workspace-write"
    sws = out.setdefault("sandbox_workspace_write", {})
    sws.setdefault("network_access", True)
    sws.setdefault("exclude_tmpdir_env_var", False)
    sws.setdefault("exclude_slash_tmp", False)
    return out


# Back-compat alias so any external callers don't break before they migrate.
# Drop this in the next minor release.
def merge_codex_deny_paths(existing_toml: dict[str, Any], _deny_paths: list[str]) -> dict[str, Any]:
    """Deprecated: emits the canonical sandbox schema regardless of deny_paths.

    The deny_paths argument is ignored — synthesis §3.7 documented that
    [sandbox] deny_paths is not a real Codex key. This shim exists for one
    release for backward compatibility and will be removed in the next
    minor version. Use ``merge_codex_sandbox_config`` directly.
    """
    return merge_codex_sandbox_config(existing_toml)


def install_managed_claude_settings(
    template_path: Path,
    deny_rules_path: Path,
    target: Path,
) -> Path:
    """Read template + deny_rules, merge, write to target. Backs up drift."""
    from coding_agents.dry_run import is_dry_run, would
    from coding_agents.installer.fs_ops import dry_run_mkdir
    from coding_agents.utils import secure_write_text

    template = json.loads(template_path.read_text())
    deny_rules = json.loads(deny_rules_path.read_text())
    merged = merge_claude_settings(template, deny_rules)
    new_content = json.dumps(merged, indent=2) + "\n"

    if is_dry_run():
        # Surface what we would do — including the parent-dir create + drift backup
        would("mkdir", "policy_parent_dir", path=target.parent)
        _backup_if_drifted(target, new_content)
        would("policy_emit", "claude_settings", path=target, bytes=len(new_content))
        return target

    dry_run_mkdir(target.parent)
    _backup_if_drifted(target, new_content)
    secure_write_text(target, new_content)
    return target


def install_codex_sandbox_config(
    _deny_rules_path: Path,
    target: Path,
) -> Path:
    """Write the canonical Codex sandbox schema to ``~/.codex/config.toml``.

    Reads the existing TOML (if any) so user-managed keys are preserved,
    then ensures ``sandbox_mode = "workspace-write"`` and the
    ``[sandbox_workspace_write]`` table are set. Drops any legacy
    ``[sandbox] deny_paths`` (synthesis §3.7).

    The ``deny_rules_path`` argument is unused since the sandbox schema
    is fixed; it's retained so the caller signature matches the install
    path's other policy emitters and so legacy callers don't break.
    """
    import tomllib
    from coding_agents.dry_run import is_dry_run, would
    from coding_agents.utils import secure_write_text

    try:
        import tomli_w
    except ImportError as exc:
        log.warning("tomli_w not installed; skipping Codex config emit: %s", exc)
        return target

    if target.exists():
        try:
            existing = tomllib.loads(target.read_text())
        except tomllib.TOMLDecodeError as exc:
            log.warning("User's %s is malformed TOML; backing up + writing fresh: %s", target, exc)
            backup = target.with_name(f"{target.stem}.backup-{_today_suffix()}{target.suffix}")
            if is_dry_run():
                would("file_write", "policy_backup_malformed", path=backup, source=target)
            else:
                backup.write_text(target.read_text())
            existing = {}
    else:
        existing = {}

    merged = merge_codex_sandbox_config(existing)
    new_content = tomli_w.dumps(merged)

    if is_dry_run():
        from coding_agents.dry_run import would as _would
        _would("mkdir", "policy_parent_dir", path=target.parent)
        _backup_if_drifted(target, new_content)
        would("policy_emit", "codex_config", path=target, bytes=len(new_content))
        return target

    from coding_agents.installer.fs_ops import dry_run_mkdir
    dry_run_mkdir(target.parent)
    _backup_if_drifted(target, new_content)
    secure_write_text(target, new_content)
    return target


# Back-compat alias for one release; remove in next minor.
install_codex_deny_paths = install_codex_sandbox_config
