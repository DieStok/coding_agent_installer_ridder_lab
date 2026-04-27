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
import os
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


# ---------------------------------------------------------------------------
# Codex hooks emission (https://developers.openai.com/codex/hooks)
# ---------------------------------------------------------------------------
#
# Schema lives at ``~/.codex/hooks.json`` (separate from config.toml so we
# fully own the file — config.toml's TOML array-of-tables nesting for
# inline hooks is cumbersome to merge idempotently).
#
# Maps the existing five Claude-style hooks to Codex events by filename
# convention:
#   on_start_*.py  →  SessionStart  (matcher: startup|resume)
#   on_stop_*.py   →  Stop          (no matcher — runs on every turn end)
#
# The hook scripts themselves were written against Claude's stdin protocol
# but accept arbitrary JSON; they ignore unknown fields. If a script
# misbehaves under Codex's protocol, the user's escape hatch is to set
# ``[features] codex_hooks = false`` in config.toml — Codex then ignores
# the file entirely.

CODEX_HOOK_EVENT_BY_PREFIX = {
    "on_start_": ("SessionStart", "startup|resume"),
    "on_stop_": ("Stop", ""),
}


def build_codex_hooks_config(install_dir: Path, hook_names: list[str]) -> dict[str, Any]:
    """Build the dict written to ``~/.codex/hooks.json``.

    Routes Claude-style ``on_start_*`` / ``on_stop_*`` script names to the
    Codex ``SessionStart`` / ``Stop`` events respectively.
    """
    from coding_agents.config import HOOK_SCRIPTS

    by_event: dict[str, list[dict[str, Any]]] = {}
    for name in hook_names:
        script = HOOK_SCRIPTS.get(name)
        if not script:
            continue
        for prefix, (event, matcher) in CODEX_HOOK_EVENT_BY_PREFIX.items():
            if not script.startswith(prefix):
                continue
            entry: dict[str, Any] = {
                "hooks": [
                    {
                        "type": "command",
                        "command": f"python3 {install_dir / 'hooks' / script}",
                        "timeout": 30 if prefix == "on_stop_" else 10,
                    }
                ],
            }
            if matcher:
                entry["matcher"] = matcher
            by_event.setdefault(event, []).append(entry)
            break
    return {"hooks": by_event} if by_event else {}


def install_codex_hooks(install_dir: Path, hook_names: list[str]) -> Path | None:
    """Write ``~/.codex/hooks.json`` and ensure the feature flag is on.

    Returns the hooks.json path on success, ``None`` if no scripts mapped.
    Idempotent — re-running with the same input produces byte-identical
    output. The feature flag is added as ``[features] codex_hooks = true``
    in ``~/.codex/config.toml`` (a separate, additive merge so the existing
    sandbox config is preserved).
    """
    from coding_agents.dry_run import is_dry_run, would
    from coding_agents.utils import secure_write_text

    config = build_codex_hooks_config(install_dir, hook_names)
    if not config:
        return None

    home = Path.home()
    hooks_path = home / ".codex" / "hooks.json"
    new_content = json.dumps(config, indent=2, sort_keys=True) + "\n"

    if is_dry_run():
        would("policy_emit", "codex_hooks", path=hooks_path, bytes=len(new_content))
    else:
        from coding_agents.installer.fs_ops import dry_run_mkdir
        dry_run_mkdir(hooks_path.parent)
        _backup_if_drifted(hooks_path, new_content)
        secure_write_text(hooks_path, new_content)

    _enable_codex_hooks_feature(home / ".codex" / "config.toml")
    return hooks_path


# ---------------------------------------------------------------------------
# OpenCode permissions emission (https://opencode.ai/docs/permissions)
# ---------------------------------------------------------------------------
#
# OpenCode v1.1.1+ replaced the legacy ``tools`` config with a unified
# ``permission`` block. Three actions per rule: "allow" / "ask" / "deny".
# Last matching pattern wins, so put broader rules first. Wildcards: ``*``
# matches zero-or-more chars, ``?`` matches one.
#
# The lab's deny_rules.json carries shell-command patterns that we want to
# refuse outright. We also lean on Apptainer for filesystem isolation, so
# the "edit" rule stays permissive — the SIF's bind-mounts already constrain
# blast radius to the mounted cwd.

def build_opencode_permissions(deny_rules: list[str]) -> dict[str, Any]:
    """Build the ``permission`` block for ~/.config/opencode/opencode.json.

    Routes the lab's bash deny patterns into ``permission.bash`` with "deny",
    keeps reads permissive (with the standard .env exclusion), asks before
    network tool calls, and lets Apptainer's bind-mounts constrain edits.
    """
    bash: dict[str, str] = {"*": "ask"}
    for pattern in deny_rules:
        # The deny_rules.json entries are shell-snippet patterns; OpenCode
        # uses the same wildcard syntax so we forward verbatim.
        bash[pattern] = "deny"
    # Common safe prefixes — explicit "allow" so users don't get prompted
    # for every git status / ls.
    safe_allows = ("git *", "ls *", "cat *", "grep *", "rg *", "find *", "pwd")
    for pat in safe_allows:
        bash.setdefault(pat, "allow")

    return {
        "*": "ask",
        "read": {
            "*": "allow",
            "*.env": "deny",
            "*.env.*": "deny",
            "*.env.example": "allow",
        },
        "bash": bash,
        "edit": "ask",
        "webfetch": "ask",
        "websearch": "allow",
        "task": "allow",
        "external_directory": "ask",
    }


def install_opencode_permissions(deny_rules: list[str]) -> Path | None:
    """Merge a permission block into ~/.config/opencode/opencode.json.

    Idempotent — re-running yields byte-identical output. Preserves any
    other top-level keys the user has configured.
    """
    from coding_agents.dry_run import is_dry_run, would
    from coding_agents.utils import secure_write_text

    target = Path.home() / ".config" / "opencode" / "opencode.json"
    permission = build_opencode_permissions(deny_rules)

    if target.exists():
        try:
            existing = json.loads(target.read_text())
        except json.JSONDecodeError as exc:
            log.warning("malformed %s; backing up + writing fresh: %s", target, exc)
            backup = target.with_name(f"{target.stem}.backup-{_today_suffix()}{target.suffix}")
            if not is_dry_run():
                backup.write_text(target.read_text())
            existing = {}
    else:
        existing = {}

    existing["$schema"] = "https://opencode.ai/config.json"
    existing["permission"] = permission
    new_content = json.dumps(existing, indent=2, sort_keys=True) + "\n"

    if is_dry_run():
        would("policy_emit", "opencode_permissions", path=target, bytes=len(new_content))
        return target

    from coding_agents.installer.fs_ops import dry_run_mkdir
    dry_run_mkdir(target.parent)
    _backup_if_drifted(target, new_content)
    secure_write_text(target, new_content)
    return target


def _enable_codex_hooks_feature(config_toml_path: Path) -> None:
    """Set ``[features] codex_hooks = true`` in config.toml without disturbing
    other keys (sandbox_workspace_write, etc.)."""
    import tomllib
    from coding_agents.dry_run import is_dry_run, would
    from coding_agents.utils import secure_write_text

    try:
        import tomli_w
    except ImportError:
        log.warning("tomli_w missing; skipping codex_hooks feature flag")
        return

    if config_toml_path.exists():
        try:
            existing = tomllib.loads(config_toml_path.read_text())
        except tomllib.TOMLDecodeError as exc:
            log.warning("malformed %s; skipping feature flag set: %s", config_toml_path, exc)
            return
    else:
        existing = {}

    features = existing.setdefault("features", {})
    if features.get("codex_hooks") is True:
        return  # already on, nothing to do
    features["codex_hooks"] = True
    new_content = tomli_w.dumps(existing)

    if is_dry_run():
        would("policy_emit", "codex_features_flag", path=config_toml_path, bytes=len(new_content))
        return

    from coding_agents.installer.fs_ops import dry_run_mkdir
    dry_run_mkdir(config_toml_path.parent)
    _backup_if_drifted(config_toml_path, new_content)
    secure_write_text(config_toml_path, new_content)


# ---------------------------------------------------------------------------
# VSCode settings.json emission
# ---------------------------------------------------------------------------

# Resolution chain for the user's ``settings.json`` (per brainstorm decision 6).
# First existing path wins.
#
# Both User and Machine settings files are valid emit targets — many of our
# wrapper keys are machine-scoped (chatgpt.cliExecutable, pi-vscode.path,
# terminal.integrated.env.linux), and per the VSCode docs:
#
#     "Machine settings (with machine or machine-overridable scopes) are
#      not synchronized by default, since their values are specific to a
#      given machine."
#
# So when a user has Settings Sync on, the User-scope file on a remote may
# never receive these keys — Machine settings on the remote is the right
# destination. We prefer User if present (some machine-overridable settings
# still take effect there) and fall back to Machine otherwise. The probe
# also handles non-standard layouts: a custom remote.SSH.serverInstallPath
# typically contains a ``.vscode-server/`` (or ``.cursor-server/``) subdir
# that holds the actual data tree.
_VSCODE_SETTINGS_CANDIDATES_ENV_KEY = "VSCODE_AGENT_FOLDER"

_SETTINGS_LEAVES = ("data/User/settings.json", "data/Machine/settings.json")
_SERVER_DIR_NAMES = (
    ".cursor-server",
    ".vscode-server",
    ".vscode-server-insiders",
    ".windsurf-server",
    ".vscodium-server",
)


def _settings_candidates_under(root: Path) -> list[Path]:
    """All plausible settings.json paths under ``root``.

    Probes both ``<root>/data/{User,Machine}/settings.json`` (standard
    layout, where ``root`` is itself a server dir) and
    ``<root>/<server_dir>/data/{User,Machine}/settings.json`` (custom
    serverInstallPath layout, where VSCode creates a ``.vscode-server``
    subdir under the user-chosen root).
    """
    candidates: list[Path] = []
    for leaf in _SETTINGS_LEAVES:
        candidates.append(root / leaf)
    for sub in _SERVER_DIR_NAMES:
        for leaf in _SETTINGS_LEAVES:
            candidates.append(root / sub / leaf)
    return candidates


def _resolve_vscode_settings_path(
    target_settings_path: Path | None = None,
) -> Path | None:
    """Return the first existing VSCode settings.json on the resolution chain.

    Returns ``None`` if no candidate exists; the caller decides whether to
    skip the emit silently or surface a warning.
    """
    if target_settings_path is not None:
        return target_settings_path

    env_root = os.environ.get(_VSCODE_SETTINGS_CANDIDATES_ENV_KEY)
    if env_root:
        for candidate in _settings_candidates_under(Path(env_root).expanduser()):
            if candidate.exists():
                return candidate

    home = Path.home()
    for sub in _SERVER_DIR_NAMES:
        for leaf in _SETTINGS_LEAVES:
            path = home / sub / leaf
            if path.exists():
                return path
    return None


def _vscode_wrapper_keys(install_dir: Path, agents: list[str]) -> dict[str, Any]:
    """Build the wrapper-key dict to merge into the user's settings.json.

    Each phase contributes its own subset of keys; this function gates by
    the agent set so a Phase-1 install only emits Pi keys.
    """
    bin_dir = install_dir / "bin"
    keys: dict[str, Any] = {}

    if "pi" in agents:
        keys["pi-vscode.path"] = str(bin_dir / "agent-pi-vscode")

    if "claude" in agents:
        keys["claudeCode.claudeProcessWrapper"] = str(bin_dir / "agent-claude-vscode")
        # Defends against the wrapper-bypass-when-true gotcha (deep-research §5.5).
        keys["claudeCode.useTerminal"] = False
        keys["claudeCode.disableLoginPrompt"] = True
        keys["claudeCode.initialPermissionMode"] = "acceptEdits"
        # Anthropic claude-code#10217 deletes this key on activation; the env
        # is already injected by agent-vscode via APPTAINERENV_*. Hint only.
        keys["claudeCode.environmentVariables"] = [
            {"name": "CLAUDE_CODE_ENTRYPOINT", "value": "claude-vscode"},
        ]

    if "codex" in agents:
        keys["chatgpt.cliExecutable"] = str(bin_dir / "agent-codex-vscode")
        keys["chatgpt.openOnStartup"] = False

    if "opencode" in agents:
        # Defence-in-depth: integrated terminal also gets the path-shim so a
        # user typing ``opencode`` in a fresh integrated terminal hits our
        # wrapper even before .bashrc is sourced.
        keys["terminal.integrated.env.linux"] = {
            "PATH": f"{bin_dir / 'path-shim'}:${{env:PATH}}",
        }

    return keys


def emit_managed_vscode_settings(
    install_dir: Path,
    agents: list[str],
    *,
    target_settings_path: Path | None = None,
) -> Path | None:
    """Merge wrapper hooks into the user's VSCode settings.json.

    Returns the resolved path on success, ``None`` if no settings.json
    exists yet (user hasn't connected VSCode to this machine yet — caller
    should warn but not fail).
    """
    from coding_agents.dry_run import is_dry_run, would
    from coding_agents.runtime.jsonc_merge import deep_merge_jsonc_settings

    target = _resolve_vscode_settings_path(target_settings_path)
    if target is None:
        log.info("VSCode settings.json not found; skipping wrapper emit")
        return None

    keys = _vscode_wrapper_keys(install_dir, agents)
    if not keys:
        return None

    if is_dry_run():
        would(
            "policy_emit",
            "vscode_wrapper_settings",
            path=target,
            keys=sorted(keys.keys()),
        )
        return target

    deep_merge_jsonc_settings(target, keys)
    return target


def unset_managed_vscode_settings(
    target_settings_path: Path | None = None,
) -> Path | None:
    """Remove our wrapper keys from the user's settings.json (uninstall path).

    Sets each key to ``null`` rather than deleting the line, since VSCode
    treats ``null`` as "key absent" and the merge-on-uninstall is symmetric
    with the merge-on-install. The key list is derived from
    ``_vscode_wrapper_keys`` so adding a new key can't drift the unset path.
    """
    target = _resolve_vscode_settings_path(target_settings_path)
    if target is None or not target.exists():
        return None

    # Use a placeholder install_dir — only the *keys* matter here; values
    # are about to be replaced with null.
    placeholder = Path("/")
    all_keys = _vscode_wrapper_keys(placeholder, ["claude", "codex", "opencode", "pi"])
    null_keys: dict[str, Any] = {key: None for key in all_keys}

    from coding_agents.runtime.jsonc_merge import deep_merge_jsonc_settings
    deep_merge_jsonc_settings(target, null_keys)
    return target
