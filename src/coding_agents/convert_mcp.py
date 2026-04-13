"""MCP format converter — ported from convert-mcp.js to pure Python.

Reads canonical MCP server definitions from servers.json and writes
agent-specific config formats. No Node.js dependency.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

_log = logging.getLogger("coding-agents")

from coding_agents.agents import AGENTS
from coding_agents.installer.fs_ops import dry_run_mkdir
from coding_agents.utils import secure_write_text


def _merge_json(file_path: Path, data: dict) -> None:
    """Shallow-merge data into an existing JSON file (or create it)."""
    existing = {}
    if file_path.exists():
        try:
            existing = json.loads(file_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    merged = {**existing, **data}
    secure_write_text(file_path, json.dumps(merged, indent=2) + "\n")


def _build_entry(srv: dict) -> dict:
    """Build the common MCP server entry dict from a canonical server definition."""
    entry: dict = {}
    if srv.get("command"):
        entry["command"] = srv["command"]
        entry["args"] = srv.get("args", [])
    if srv.get("url"):
        entry["url"] = srv["url"]
    if srv.get("env"):
        entry["env"] = srv["env"]
    return entry


def convert_mcp(servers_json: Path, agent_keys: list[str] | None = None) -> list[str]:
    """Convert canonical MCP servers to agent-specific formats.

    Returns list of files written.
    """
    if not servers_json.exists():
        return []

    canonical = json.loads(servers_json.read_text())
    servers = canonical.get("servers", {})
    if not servers:
        return []

    home = Path.home()
    written: list[str] = []

    if agent_keys is None:
        agent_keys = list(AGENTS.keys())

    # Dispatch table — each format maps to a writer function
    writers = {
        "claude": _write_claude,
        "codex": _write_codex,
        "pi": _write_pi,
        "opencode": lambda s, h: _write_json_mcp(s, h, h / ".config/opencode/opencode.json", "mcp"),
        "gemini": lambda s, h: _write_json_mcp(s, h, h / ".gemini/settings.json", "mcpServers"),
        "amp": lambda s, h: _write_json_mcp(s, h, h / ".config/amp/settings.json", "mcpServers"),
    }

    for key in agent_keys:
        if key not in AGENTS:
            continue
        fmt = AGENTS[key]["mcp_format"]
        writer = writers.get(fmt)
        if writer:
            _log.debug("convert_mcp: writing format=%s for agent=%s", fmt, key)
            written.extend(writer(servers, home))

    return list(set(written))


# ---------------------------------------------------------------------------
# Format-specific writers
# ---------------------------------------------------------------------------


def _write_json_mcp(
    servers: dict, home: Path, config_path: Path, top_key: str
) -> list[str]:
    """Generic writer for agents that use JSON with a top-level key for MCP servers."""
    mcp_servers = {name: _build_entry(srv) for name, srv in servers.items()}
    _merge_json(config_path, {top_key: mcp_servers})
    return [str(config_path)]


def _write_claude(servers: dict, home: Path) -> list[str]:
    """Claude Code uses mcpServers with a 'type' field."""
    mcp_servers = {}
    for name, srv in servers.items():
        entry = _build_entry(srv)
        entry["type"] = srv.get("transport", "stdio")
        mcp_servers[name] = entry

    path = home / ".mcp.json"
    _merge_json(path, {"mcpServers": mcp_servers})
    return [str(path)]


def _write_codex(servers: dict, home: Path) -> list[str]:
    """Codex CLI uses TOML with marker-based sections."""
    config_path = home / ".codex" / "config.toml"
    dry_run_mkdir(config_path.parent)

    marker_start = "# >>> coding-agents MCP >>>"
    marker_end = "# <<< coding-agents MCP <<<"

    lines = [marker_start]
    for name, srv in servers.items():
        lines.append(f"\n[mcp_servers.{name}]")
        if srv.get("command"):
            cmd_list = json.dumps([srv["command"]] + srv.get("args", []))
            lines.append(f"command = {cmd_list}")
        if srv.get("url"):
            lines.append(f'url = "{srv["url"]}"')
        if srv.get("env"):
            pairs = ", ".join(f'"{k}" = "{v}"' for k, v in srv["env"].items())
            lines.append(f"env = {{ {pairs} }}")
        lines.append("enabled = true")
    lines.append(marker_end)
    new_block = "\n".join(lines) + "\n"

    content = ""
    if config_path.exists():
        content = config_path.read_text()
        if marker_start in content:
            before = content[: content.index(marker_start)]
            after_marker = content.find(marker_end)
            after = content[after_marker + len(marker_end):] if after_marker != -1 else ""
            content = before + after

    if not content.endswith("\n"):
        content += "\n"
    content += "\n" + new_block
    secure_write_text(config_path, content)
    return [str(config_path)]


def _write_pi(servers: dict, home: Path) -> list[str]:
    """Pi uses mcp.json with settings and lifecycle: lazy."""
    mcp_servers = {}
    for name, srv in servers.items():
        entry = _build_entry(srv)
        entry["lifecycle"] = "lazy"
        mcp_servers[name] = entry

    path = home / ".pi" / "agent" / "mcp.json"
    data = {
        "settings": {"toolPrefix": "mcp", "idleTimeout": 10},
        "mcpServers": mcp_servers,
    }
    # Pi MCP is fully managed by us — overwrite
    secure_write_text(path, json.dumps(data, indent=2) + "\n")
    return [str(path)]
