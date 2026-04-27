"""Tests for detect_existing.py — pre-flight scanner and backup."""
import json
import tarfile
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def test_agent_inventory_human_size():
    from coding_agents.detect_existing import AgentInventory

    inv = AgentInventory("claude", "Claude Code", Path("/tmp/test"))
    inv.total_size = 0
    assert inv.human_size() == "0 B"
    inv.total_size = 512
    assert inv.human_size() == "512 B"
    inv.total_size = 2048
    assert "KB" in inv.human_size()
    inv.total_size = 5 * 1024 * 1024
    assert "MB" in inv.human_size()


def test_agent_inventory_tree_display():
    from coding_agents.detect_existing import AgentInventory

    inv = AgentInventory("claude", "Claude Code", Path("/tmp/test"))
    inv.files = ["settings.json", "CLAUDE.md", "skills/test/SKILL.md"]
    tree = inv.tree_display()
    assert "settings.json" in tree
    assert "CLAUDE.md" in tree


def test_agent_inventory_tree_truncation():
    from coding_agents.detect_existing import AgentInventory

    inv = AgentInventory("claude", "Claude Code", Path("/tmp/test"))
    inv.files = [f"file_{i}.txt" for i in range(50)]
    tree = inv.tree_display(max_files=5)
    assert "... and 45 more files" in tree


def test_global_inventory_existing_agents():
    from coding_agents.detect_existing import GlobalInventory, AgentInventory

    inv = GlobalInventory()
    inv.agents = [
        AgentInventory("claude", "Claude Code", Path("/tmp"), exists=True, files=["a"]),
        AgentInventory("codex", "Codex CLI", Path("/tmp"), exists=False),
    ]
    existing = inv.existing_agents
    assert len(existing) == 1
    assert existing[0].display_name == "Claude Code"


def test_global_inventory_has_existing():
    from coding_agents.detect_existing import GlobalInventory, AgentInventory

    inv = GlobalInventory()
    inv.agents = [AgentInventory("claude", "Claude Code", Path("/tmp"), exists=False)]
    inv.global_files = {}
    assert not inv.has_existing

    inv.agents[0].exists = True
    assert inv.has_existing


def test_backup_agent_dir():
    from coding_agents.detect_existing import AgentInventory, backup_agent_dir

    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / ".claude"
        config_dir.mkdir()
        (config_dir / "settings.json").write_text('{"test": true}')
        (config_dir / "CLAUDE.md").write_text("# Test")

        inv = AgentInventory("claude", "Claude Code", config_dir, exists=True)
        backup_path = backup_agent_dir(inv)

        assert backup_path is not None
        assert backup_path.exists()
        assert backup_path.suffix == ".gz"
        assert ".backup-" in backup_path.name

        # Verify archive contents
        with tarfile.open(str(backup_path), "r:gz") as tar:
            names = tar.getnames()
            assert any("settings.json" in n for n in names)
            assert any("CLAUDE.md" in n for n in names)


def test_backup_uses_gzip_level_below_max():
    """Regression: tarfile.open(\"w:gz\") defaults to compresslevel=9 which
    is 2-3x slower than level 6 for ~1-2% smaller output. Recovery
    snapshots don't need maximum compression — keep the default below 9.

    We can't directly read the level back from the gzip stream, but we
    can write a known-large repeating payload and assert the resulting
    tarball is at least slightly larger than what level 9 would produce
    on the same input — proving we're not on level 9. (We compare against
    a level-9 tarball produced inline.)"""
    import tarfile as _tf
    from coding_agents.detect_existing import AgentInventory, backup_agent_dir

    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / ".claude"
        config_dir.mkdir()
        # Repeating but not-trivially-compressible payload so level 9
        # actually beats level 6 by a measurable amount.
        payload = ("the quick brown fox jumps over the lazy dog\n" * 5000)
        (config_dir / "transcript.jsonl").write_text(payload)

        inv = AgentInventory("claude", "Claude Code", config_dir, exists=True)
        actual = backup_agent_dir(inv)
        assert actual is not None

        # Reference: same payload at level 9.
        ref = Path(tmpdir) / "ref.tar.gz"
        with _tf.open(str(ref), "w:gz", compresslevel=9) as tar:
            tar.add(str(config_dir), arcname=config_dir.name)

        actual_size = actual.stat().st_size
        ref_size = ref.stat().st_size
        assert actual_size > ref_size, (
            f"backup at {actual_size} bytes is no larger than the "
            f"level-9 reference at {ref_size} — backup may still be on "
            f"level 9, which is 2-3x slower than necessary"
        )


def test_backup_skips_nonexistent():
    from coding_agents.detect_existing import AgentInventory, backup_agent_dir

    inv = AgentInventory("claude", "Claude Code", Path("/nonexistent"), exists=False)
    assert backup_agent_dir(inv) is None


def test_backup_skips_node_modules():
    from coding_agents.detect_existing import AgentInventory, backup_agent_dir

    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / ".codex"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text("# test")
        nm = config_dir / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("module.exports = {}")

        inv = AgentInventory("codex", "Codex CLI", config_dir, exists=True)
        backup_path = backup_agent_dir(inv)

        assert backup_path is not None
        with tarfile.open(str(backup_path), "r:gz") as tar:
            names = tar.getnames()
            assert not any("node_modules" in n for n in names)


def test_scan_project_existing():
    from coding_agents.detect_existing import scan_project_existing

    with tempfile.TemporaryDirectory() as tmpdir:
        project = Path(tmpdir)
        (project / ".claude").mkdir()
        (project / ".claude" / "settings.json").write_text("{}")
        (project / "AGENTS.md").write_text("# Test")

        found = scan_project_existing(project)
        assert ".claude" in found["agent_configs"]
        assert "AGENTS.md" in found["instruction_files"]


def test_scan_project_empty():
    from coding_agents.detect_existing import scan_project_existing

    with tempfile.TemporaryDirectory() as tmpdir:
        found = scan_project_existing(Path(tmpdir))
        assert not found["agent_configs"]
        assert not found["instruction_files"]
