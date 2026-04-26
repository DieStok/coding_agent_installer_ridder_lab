"""Emit per-agent policy files from the single-source deny_rules.json.

Two consumers:
- Claude Code: ``~/.claude/settings.json`` (managed-default, NOT enforced —
  v2 D5 will write to ``/etc/claude-code/managed-settings.json`` for true
  enforcement; until then the user can override).
- Codex CLI: ``~/.codex/config.toml`` ``[sandbox]`` ``deny_paths``.

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
    to ``path.with_suffix(f".backup-{today}{path.suffix}")``. Idempotent."""
    if not path.exists():
        return None
    existing = path.read_text()
    if existing == new_content:
        return None
    backup = path.with_name(f"{path.stem}.backup-{_today_suffix()}{path.suffix}")
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


def merge_codex_deny_paths(existing_toml: dict[str, Any], deny_paths: list[str]) -> dict[str, Any]:
    """Pure: merge deny_paths into existing_toml's [sandbox].deny_paths.

    Preserves all other keys in the user's existing TOML.
    """
    out = json.loads(json.dumps(existing_toml))  # deep copy
    sandbox = out.setdefault("sandbox", {})
    existing_paths = list(sandbox.get("deny_paths", []))
    seen = set(existing_paths)
    for p in deny_paths:
        if p not in seen:
            existing_paths.append(p)
            seen.add(p)
    sandbox["deny_paths"] = existing_paths
    return out


def install_managed_claude_settings(
    template_path: Path,
    deny_rules_path: Path,
    target: Path,
) -> Path:
    """Read template + deny_rules, merge, write to target. Backs up drift."""
    from coding_agents.dry_run import is_dry_run, would
    from coding_agents.utils import secure_write_text

    template = json.loads(template_path.read_text())
    deny_rules = json.loads(deny_rules_path.read_text())
    merged = merge_claude_settings(template, deny_rules)
    new_content = json.dumps(merged, indent=2) + "\n"

    if is_dry_run():
        would("policy_emit", "claude_settings", path=target, bytes=len(new_content))
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    _backup_if_drifted(target, new_content)
    secure_write_text(target, new_content)
    return target


def install_codex_deny_paths(
    deny_rules_path: Path,
    target: Path,
) -> Path:
    """Read deny_rules, merge into ~/.codex/config.toml [sandbox].deny_paths."""
    import tomllib
    from coding_agents.dry_run import is_dry_run, would
    from coding_agents.utils import secure_write_text

    try:
        import tomli_w
    except ImportError as exc:
        log.warning("tomli_w not installed; skipping Codex config emit: %s", exc)
        return target

    deny_rules = json.loads(deny_rules_path.read_text())
    deny_paths = deny_rules.get("codex_config_toml_deny_paths", [])
    if not deny_paths:
        return target

    if target.exists():
        try:
            existing = tomllib.loads(target.read_text())
        except tomllib.TOMLDecodeError as exc:
            log.warning("User's %s is malformed TOML; backing up + writing fresh: %s", target, exc)
            backup = target.with_name(f"{target.stem}.backup-{_today_suffix()}{target.suffix}")
            backup.write_text(target.read_text())
            existing = {}
    else:
        existing = {}

    merged = merge_codex_deny_paths(existing, deny_paths)
    new_content = tomli_w.dumps(merged)

    if is_dry_run():
        would("policy_emit", "codex_config", path=target, bytes=len(new_content))
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    _backup_if_drifted(target, new_content)
    secure_write_text(target, new_content)
    return target
