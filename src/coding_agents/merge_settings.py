"""Marker-based settings merger for agent config files.

Merges coding-agents entries into existing agent configs (hooks, MCP, deny rules)
while preserving user customizations. Uses marker metadata to identify our entries
so they can be cleanly replaced on re-sync.

Provides before/after display for user visibility.
"""
from __future__ import annotations

import copy
import json
import logging

_log = logging.getLogger("coding-agents")
from pathlib import Path
from typing import Any

# Marker used to tag entries managed by coding-agents
MARKER_KEY = "_coding_agents_managed"
MARKER_VALUE = True

# For TOML files (Codex), we use comment markers
TOML_MARKER_START = "# >>> coding-agents >>>"
TOML_MARKER_END = "# <<< coding-agents <<<"


# ---------------------------------------------------------------------------
# JSON merge (Claude Code settings.json, OpenCode, Gemini, Amp, Pi MCP)
# ---------------------------------------------------------------------------


class MergeResult:
    """Captures before/after state of a merge for display."""

    def __init__(self, file_path: Path, section: str):
        self.file_path = file_path
        self.section = section  # e.g., "hooks", "permissions.deny", "mcpServers"
        self.original: Any = None
        self.merged: Any = None
        self.added_keys: list[str] = []
        self.preserved_keys: list[str] = []

    def summary(self) -> str:
        """Human-readable one-line summary."""
        if not self.added_keys and not self.preserved_keys:
            return f"{self.section}: no changes"
        parts = []
        if self.added_keys:
            parts.append(f"added {len(self.added_keys)} entries")
        if self.preserved_keys:
            parts.append(f"preserved {len(self.preserved_keys)} existing")
        return f"{self.section}: {', '.join(parts)}"

def merge_json_section(
    file_path: Path,
    section_path: str,
    our_entries: dict | list,
    *,
    marker_field: str = MARKER_KEY,
) -> MergeResult:
    """Merge our entries into a section of a JSON config file.

    For dict sections (e.g., mcpServers): adds our keys, preserves user keys.
    For list sections (e.g., hooks.SessionStart): appends our entries (marked),
    removes previously-marked entries first.

    Args:
        file_path: Path to the JSON config file.
        section_path: Dot-separated path to the section (e.g., "hooks.SessionStart").
        our_entries: Dict or list of entries to merge in.
        marker_field: Key added to our entries for identification.

    Returns:
        MergeResult with before/after state.
    """
    _log.debug("merge_json_section: file=%s section=%s", file_path, section_path)
    result = MergeResult(file_path, section_path)

    # Load existing file
    existing: dict = {}
    if file_path.exists():
        try:
            existing = json.loads(file_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Navigate to the section
    keys = section_path.split(".")
    parent = existing
    for key in keys[:-1]:
        if key not in parent:
            parent[key] = {}
        parent = parent[key]

    section_key = keys[-1]
    current_value = parent.get(section_key)
    result.original = copy.deepcopy(current_value)

    if isinstance(our_entries, dict):
        # Dict merge (e.g., mcpServers, permissions)
        if current_value is None:
            current_value = {}

        # Remove our previously-managed entries
        cleaned = {
            k: v for k, v in current_value.items()
            if not (isinstance(v, dict) and v.get(marker_field))
        }
        result.preserved_keys = list(cleaned.keys())

        # Add our entries with marker
        for k, v in our_entries.items():
            if isinstance(v, dict):
                v = {**v, marker_field: MARKER_VALUE}
            cleaned[k] = v
            result.added_keys.append(k)

        parent[section_key] = cleaned
        result.merged = copy.deepcopy(cleaned)

    elif isinstance(our_entries, list):
        # List merge (e.g., hooks.SessionStart, permissions.deny)
        if current_value is None:
            current_value = []

        if isinstance(current_value, list):
            if all(isinstance(e, str) for e in current_value):
                # String list (e.g., deny rules) — simple set union
                existing_set = set(current_value)
                result.preserved_keys = list(existing_set)
                for entry in our_entries:
                    if entry not in existing_set:
                        current_value.append(entry)
                        result.added_keys.append(str(entry))
            else:
                # Object list (e.g., hook entries) — remove our marked entries, append new
                cleaned = [
                    e for e in current_value
                    if not (isinstance(e, dict) and e.get(marker_field))
                ]
                result.preserved_keys = [
                    _hook_summary(e) for e in cleaned
                ]
                for entry in our_entries:
                    if isinstance(entry, dict):
                        entry = {**entry, marker_field: MARKER_VALUE}
                    cleaned.append(entry)
                    result.added_keys.append(_hook_summary(entry))
                current_value = cleaned

        parent[section_key] = current_value
        result.merged = copy.deepcopy(current_value)

    # Write back with restricted permissions
    from coding_agents.utils import secure_write_text

    secure_write_text(file_path, json.dumps(existing, indent=2) + "\n")

    return result


def _hook_summary(entry: Any) -> str:
    """Short summary of a hook entry for display."""
    if isinstance(entry, dict):
        hooks = entry.get("hooks", [])
        if hooks and isinstance(hooks[0], dict):
            cmd = hooks[0].get("command", "")
            # Extract script name from command
            parts = cmd.split("/")
            return parts[-1] if parts else cmd
        return str(entry.get("matcher", "unknown"))
    return str(entry)[:40]


# ---------------------------------------------------------------------------
# TOML merge (Codex config.toml)
# ---------------------------------------------------------------------------


def merge_toml_section(
    file_path: Path,
    new_block: str,
) -> MergeResult:
    """Replace the coding-agents marked section in a TOML file.

    Args:
        file_path: Path to the TOML config file.
        new_block: Content to place between markers (without markers themselves).

    Returns:
        MergeResult with before/after state.
    """
    result = MergeResult(file_path, "mcp_servers")

    content = ""
    if file_path.exists():
        content = file_path.read_text()

    # Extract existing marked section for "before" display
    if TOML_MARKER_START in content:
        start_idx = content.index(TOML_MARKER_START)
        end_marker_idx = content.find(TOML_MARKER_END)
        if end_marker_idx != -1:
            old_block = content[start_idx + len(TOML_MARKER_START):end_marker_idx].strip()
            result.original = old_block
            # Remove old section
            before = content[:start_idx]
            after = content[end_marker_idx + len(TOML_MARKER_END):]
            content = before + after
        else:
            result.original = None
    else:
        result.original = None

    # Build new marked block
    marked_block = f"\n{TOML_MARKER_START}\n{new_block}\n{TOML_MARKER_END}\n"
    result.merged = new_block

    if not content.endswith("\n"):
        content += "\n"
    content += marked_block

    from coding_agents.utils import secure_write_text

    secure_write_text(file_path, content)

    result.added_keys = ["coding-agents MCP block"]
    return result


# ---------------------------------------------------------------------------
# High-level merge functions (used by sync.py and executor.py)
# ---------------------------------------------------------------------------


def merge_claude_hooks(
    settings_path: Path,
    hook_entries: list[dict],
) -> list[MergeResult]:
    """Merge coding-agents hooks into Claude Code settings.json.

    Returns a MergeResult per event type.
    """
    results = []

    # Group hooks by event type
    session_start = []
    stop = []
    for entry in hook_entries:
        hooks = entry.get("hooks", [])
        if hooks:
            cmd = hooks[0].get("command", "")
            if "on_start_" in cmd:
                session_start.append(entry)
            elif "on_stop_" in cmd:
                stop.append(entry)

    if session_start:
        r = merge_json_section(settings_path, "hooks.SessionStart", session_start)
        results.append(r)

    if stop:
        r = merge_json_section(settings_path, "hooks.Stop", stop)
        results.append(r)

    return results


def merge_claude_deny_rules(
    settings_path: Path,
    rules: list[str],
) -> MergeResult:
    """Merge deny rules into Claude Code settings.json permissions.deny."""
    return merge_json_section(settings_path, "permissions.deny", rules)


def merge_mcp_servers(
    file_path: Path,
    servers: dict,
    *,
    section_path: str = "mcpServers",
) -> MergeResult:
    """Merge MCP server entries into a JSON config file."""
    return merge_json_section(file_path, section_path, servers)


