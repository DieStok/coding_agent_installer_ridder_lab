"""Tests for merge_settings.py — marker-based JSON/TOML merge."""
import json
import tempfile
from pathlib import Path

import pytest


def test_merge_json_dict_adds_entries():
    from coding_agents.merge_settings import merge_json_section

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)

    try:
        # Start with empty file
        path.write_text("{}")

        result = merge_json_section(
            path, "mcpServers", {"github": {"command": "npx", "args": []}}
        )

        data = json.loads(path.read_text())
        assert "mcpServers" in data
        assert "github" in data["mcpServers"]
        assert data["mcpServers"]["github"]["_coding_agents_managed"] is True
        assert "github" in result.added_keys
    finally:
        path.unlink(missing_ok=True)


def test_merge_json_preserves_user_entries():
    from coding_agents.merge_settings import merge_json_section

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)

    try:
        # Existing user config
        path.write_text(json.dumps({
            "mcpServers": {
                "my-custom-server": {"command": "node", "args": ["server.js"]}
            }
        }))

        result = merge_json_section(
            path, "mcpServers", {"github": {"command": "npx"}}
        )

        data = json.loads(path.read_text())
        # User entry preserved
        assert "my-custom-server" in data["mcpServers"]
        # Our entry added
        assert "github" in data["mcpServers"]
        assert "my-custom-server" in result.preserved_keys
        assert "github" in result.added_keys
    finally:
        path.unlink(missing_ok=True)


def test_merge_json_replaces_our_old_entries():
    from coding_agents.merge_settings import merge_json_section, MARKER_KEY

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)

    try:
        # Existing config with our old managed entry
        path.write_text(json.dumps({
            "mcpServers": {
                "old-server": {"command": "old", MARKER_KEY: True},
                "user-server": {"command": "user"},
            }
        }))

        result = merge_json_section(
            path, "mcpServers", {"new-server": {"command": "new"}}
        )

        data = json.loads(path.read_text())
        # Old managed entry removed
        assert "old-server" not in data["mcpServers"]
        # User entry preserved
        assert "user-server" in data["mcpServers"]
        # New entry added
        assert "new-server" in data["mcpServers"]
    finally:
        path.unlink(missing_ok=True)


def test_merge_json_list_appends():
    from coding_agents.merge_settings import merge_json_section

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)

    try:
        # Existing deny rules
        path.write_text(json.dumps({
            "permissions": {
                "deny": ["Read(./.env)", "Read(./secrets/*)"]
            }
        }))

        result = merge_json_section(
            path, "permissions.deny", ["Read(./.env)", "Read(./build)"]
        )

        data = json.loads(path.read_text())
        deny = data["permissions"]["deny"]
        # No duplicates
        assert deny.count("Read(./.env)") == 1
        # New entry added
        assert "Read(./build)" in deny
        assert "Read(./build)" in result.added_keys
    finally:
        path.unlink(missing_ok=True)


def test_unmerge_marked_entries_dict():
    from coding_agents.merge_settings import unmerge_marked_entries, MARKER_KEY

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)

    try:
        path.write_text(json.dumps({
            "mcpServers": {
                "ours": {"command": "x", MARKER_KEY: True},
                "user": {"command": "y"},
            }
        }))

        result = unmerge_marked_entries(path, "mcpServers")
        assert result is not None
        assert "ours" in result.added_keys  # removed
        assert "user" in result.preserved_keys

        data = json.loads(path.read_text())
        assert "ours" not in data["mcpServers"]
        assert data["mcpServers"]["user"] == {"command": "y"}
    finally:
        path.unlink(missing_ok=True)


def test_unmerge_marked_entries_object_list():
    from coding_agents.merge_settings import unmerge_marked_entries, MARKER_KEY

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)

    try:
        path.write_text(json.dumps({
            "hooks": {
                "SessionStart": [
                    {"matcher": "ours", "hooks": [{"command": "x"}], MARKER_KEY: True},
                    {"matcher": "user", "hooks": [{"command": "y"}]},
                ]
            }
        }))

        result = unmerge_marked_entries(path, "hooks.SessionStart")
        assert result is not None and len(result.added_keys) == 1

        data = json.loads(path.read_text())
        remaining = data["hooks"]["SessionStart"]
        assert len(remaining) == 1
        assert remaining[0]["matcher"] == "user"
    finally:
        path.unlink(missing_ok=True)


def test_unmerge_marked_entries_string_list():
    from coding_agents.merge_settings import unmerge_marked_entries

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)

    try:
        path.write_text(json.dumps({
            "permissions": {
                "deny": ["Read(./.env)", "Read(./secrets/*)", "user-rule"]
            }
        }))

        result = unmerge_marked_entries(
            path,
            "permissions.deny",
            string_entries_to_remove=["Read(./.env)", "Read(./secrets/*)"],
        )
        assert result is not None
        assert len(result.added_keys) == 2

        data = json.loads(path.read_text())
        assert data["permissions"]["deny"] == ["user-rule"]
    finally:
        path.unlink(missing_ok=True)


def test_unmerge_marked_entries_missing_file():
    from coding_agents.merge_settings import unmerge_marked_entries

    assert unmerge_marked_entries(Path("/no/such/file.json"), "anything") is None


def test_merge_toml_section():
    from coding_agents.merge_settings import merge_toml_section, TOML_MARKER_START, TOML_MARKER_END

    with tempfile.NamedTemporaryFile(suffix=".toml", delete=False, mode="w") as f:
        path = Path(f.name)
        f.write("# User config\nmodel = 'gpt-4'\n")

    try:
        result = merge_toml_section(path, '[mcp_servers.test]\ncommand = ["npx"]')

        content = path.read_text()
        # User content preserved
        assert "model = 'gpt-4'" in content
        # Our section added
        assert TOML_MARKER_START in content
        assert TOML_MARKER_END in content
        assert "mcp_servers.test" in content
    finally:
        path.unlink(missing_ok=True)


def test_merge_toml_replaces_old_section():
    from coding_agents.merge_settings import merge_toml_section, TOML_MARKER_START, TOML_MARKER_END

    with tempfile.NamedTemporaryFile(suffix=".toml", delete=False, mode="w") as f:
        path = Path(f.name)
        f.write(f"# User config\n{TOML_MARKER_START}\nold stuff\n{TOML_MARKER_END}\n")

    try:
        merge_toml_section(path, "new stuff")

        content = path.read_text()
        assert "old stuff" not in content
        assert "new stuff" in content
        # Only one pair of markers
        assert content.count(TOML_MARKER_START) == 1
    finally:
        path.unlink(missing_ok=True)


def test_merge_result_summary():
    from coding_agents.merge_settings import MergeResult

    r = MergeResult(Path("/test"), "hooks")
    r.added_keys = ["hook1", "hook2"]
    r.preserved_keys = ["user_hook"]
    assert "added 2" in r.summary()
    assert "preserved 1" in r.summary()


def test_merge_creates_missing_file():
    from coding_agents.merge_settings import merge_json_section

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "subdir" / "settings.json"
        assert not path.exists()

        merge_json_section(path, "mcpServers", {"test": {"command": "echo"}})

        assert path.exists()
        data = json.loads(path.read_text())
        assert "test" in data["mcpServers"]


def test_merge_result_has_correct_fields():
    from coding_agents.merge_settings import MergeResult

    r = MergeResult(Path("/test/settings.json"), "hooks.SessionStart")
    r.original = [{"matcher": "", "hooks": [{"command": "old"}]}]
    r.merged = [{"matcher": "", "hooks": [{"command": "old"}]}, {"matcher": "", "hooks": [{"command": "new"}]}]
    r.added_keys = ["new"]
    r.preserved_keys = ["old"]

    assert "hooks.SessionStart" in r.summary()
    assert "added 1" in r.summary()
    assert "preserved 1" in r.summary()


def test_merge_json_dict_entries_into_empty_existing_list():
    """Regression: empty existing list passed `all(isinstance(e, str))`
    vacuously, routing dict-shaped hook entries into the set-union path
    where `dict in set()` raised "unhashable type: dict"."""
    from coding_agents.merge_settings import merge_json_section

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)

    try:
        path.write_text(json.dumps({"hooks": {"SessionStart": []}}))
        hook_entries = [
            {
                "matcher": "",
                "hooks": [{"type": "command", "command": "/path/to/on_start_hook.sh"}],
            }
        ]

        result = merge_json_section(path, "hooks.SessionStart", hook_entries)

        data = json.loads(path.read_text())
        assert len(data["hooks"]["SessionStart"]) == 1
        assert data["hooks"]["SessionStart"][0]["_coding_agents_managed"] is True
        assert len(result.added_keys) == 1
    finally:
        path.unlink(missing_ok=True)
