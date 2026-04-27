"""Tests for the JSONC-tolerant deep-merge used to emit VSCode settings.json."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from coding_agents.runtime.jsonc_merge import deep_merge_jsonc_settings, _deep_merge


def test_deep_merge_disjoint_keys():
    out = _deep_merge({"a": 1}, {"b": 2})
    assert out == {"a": 1, "b": 2}


def test_deep_merge_nested_dicts():
    existing = {"foo": {"a": 1, "shared": "old"}}
    new = {"foo": {"b": 2, "shared": "new"}}
    out = _deep_merge(existing, new)
    assert out == {"foo": {"a": 1, "b": 2, "shared": "new"}}


def test_deep_merge_list_replacement():
    out = _deep_merge({"x": [1, 2, 3]}, {"x": [9]})
    assert out == {"x": [9]}


def test_deep_merge_scalar_overwrites_dict():
    out = _deep_merge({"k": {"deep": 1}}, {"k": "scalar"})
    assert out == {"k": "scalar"}


def test_emit_into_fresh_file(tmp_path):
    target = tmp_path / "settings.json"
    deep_merge_jsonc_settings(target, {"pi-vscode.path": "/x"})
    assert target.exists()
    parsed = json.loads(target.read_text())
    assert parsed == {"pi-vscode.path": "/x"}


def test_emit_preserves_existing_keys(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"editor.fontSize": 14, "files.encoding": "utf8"}))
    deep_merge_jsonc_settings(target, {"pi-vscode.path": "/x"})
    parsed = json.loads(target.read_text())
    assert parsed["editor.fontSize"] == 14
    assert parsed["files.encoding"] == "utf8"
    assert parsed["pi-vscode.path"] == "/x"


def test_emit_with_jsonc_input(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text(
        '{\n'
        '  // human comment\n'
        '  "editor.fontSize": 14,\n'
        '  "files.exclude": {\n'
        '    "**/.git": true,\n'
        '  },\n'
        '}\n'
    )
    deep_merge_jsonc_settings(target, {"pi-vscode.path": "/x"})
    parsed = json.loads(target.read_text())
    assert parsed["editor.fontSize"] == 14
    assert parsed["files.exclude"] == {"**/.git": True}
    assert parsed["pi-vscode.path"] == "/x"


def test_emit_idempotent(tmp_path):
    target = tmp_path / "settings.json"
    deep_merge_jsonc_settings(target, {"pi-vscode.path": "/x"})
    first = target.read_text()
    deep_merge_jsonc_settings(target, {"pi-vscode.path": "/x"})
    second = target.read_text()
    assert first == second


def test_emit_creates_bak_when_target_exists(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"original": True}))
    deep_merge_jsonc_settings(target, {"pi-vscode.path": "/x"})
    bak = target.with_name(target.name + ".bak")
    assert bak.exists()
    assert json.loads(bak.read_text()) == {"original": True}


def test_emit_no_bak_for_fresh_file(tmp_path):
    target = tmp_path / "settings.json"
    deep_merge_jsonc_settings(target, {"pi-vscode.path": "/x"})
    bak = target.with_name(target.name + ".bak")
    assert not bak.exists()


def test_emit_atomic_failure_keeps_target(tmp_path, monkeypatch):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"original": True}))

    def boom(*a, **kw):
        raise OSError("simulated rename failure")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        deep_merge_jsonc_settings(target, {"pi-vscode.path": "/x"})
    # Target unchanged
    assert json.loads(target.read_text()) == {"original": True}
    # .bak was created before the failed replace
    bak = target.with_name(target.name + ".bak")
    assert bak.exists()


def test_emit_nested_merge_into_existing(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"terminal.integrated.env.linux": {"OTHER": "1"}}))
    deep_merge_jsonc_settings(
        target,
        {"terminal.integrated.env.linux": {"PATH": "/shim:${env:PATH}"}},
    )
    parsed = json.loads(target.read_text())
    assert parsed["terminal.integrated.env.linux"] == {
        "OTHER": "1",
        "PATH": "/shim:${env:PATH}",
    }


def test_emit_handles_empty_file(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text("")
    deep_merge_jsonc_settings(target, {"pi-vscode.path": "/x"})
    parsed = json.loads(target.read_text())
    assert parsed == {"pi-vscode.path": "/x"}
