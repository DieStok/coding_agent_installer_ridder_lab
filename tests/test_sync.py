"""Tests for convert_mcp.py and sync logic."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def test_convert_mcp_creates_claude_format():
    from coding_agents.convert_mcp import convert_mcp

    with tempfile.TemporaryDirectory() as tmpdir:
        servers_json = Path(tmpdir) / "servers.json"
        servers_json.write_text(json.dumps({
            "servers": {
                "test-server": {
                    "command": "npx",
                    "args": ["-y", "test-pkg"],
                    "env": {"TOKEN": "abc"},
                    "transport": "stdio",
                }
            }
        }))

        fake_home = Path(tmpdir) / "home"
        fake_home.mkdir()

        with patch("coding_agents.convert_mcp.Path.home", return_value=fake_home):
            written = convert_mcp(servers_json, ["claude"])

        mcp_file = fake_home / ".mcp.json"
        assert mcp_file.exists()
        data = json.loads(mcp_file.read_text())
        assert "mcpServers" in data
        assert "test-server" in data["mcpServers"]
        srv = data["mcpServers"]["test-server"]
        assert srv["type"] == "stdio"
        assert srv["command"] == "npx"


def test_convert_mcp_pi_format():
    from coding_agents.convert_mcp import convert_mcp

    with tempfile.TemporaryDirectory() as tmpdir:
        servers_json = Path(tmpdir) / "servers.json"
        servers_json.write_text(json.dumps({
            "servers": {
                "gh": {
                    "command": "npx",
                    "args": ["-y", "@mcp/server-github"],
                    "transport": "stdio",
                }
            }
        }))

        fake_home = Path(tmpdir) / "home"
        fake_home.mkdir()

        with patch("coding_agents.convert_mcp.Path.home", return_value=fake_home):
            convert_mcp(servers_json, ["pi"])

        pi_mcp = fake_home / ".pi" / "agent" / "mcp.json"
        assert pi_mcp.exists()
        data = json.loads(pi_mcp.read_text())
        assert "settings" in data
        assert data["mcpServers"]["gh"]["lifecycle"] == "lazy"


def test_convert_mcp_empty_servers():
    from coding_agents.convert_mcp import convert_mcp

    with tempfile.TemporaryDirectory() as tmpdir:
        servers_json = Path(tmpdir) / "servers.json"
        servers_json.write_text(json.dumps({"servers": {}}))

        result = convert_mcp(servers_json, ["claude"])
        assert result == []


def test_convert_mcp_missing_file():
    from coding_agents.convert_mcp import convert_mcp

    result = convert_mcp(Path("/nonexistent/servers.json"), ["claude"])
    assert result == []
