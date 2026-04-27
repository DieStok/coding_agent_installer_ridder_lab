"""Tests for the relaxed Node.js doctor check."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from coding_agents.commands import doctor


@pytest.fixture
def fake_sif(tmp_path):
    sif = tmp_path / "agent.sif"
    sif.write_bytes(b"\0" * 32)
    return sif


def test_sif_can_run_node_returns_false_when_no_sif_configured(tmp_path):
    assert doctor._sif_can_run_node({}) is False


def test_sif_can_run_node_returns_false_when_sif_missing(tmp_path):
    cfg = {"sandbox_sif_path": str(tmp_path / "nope.sif")}
    assert doctor._sif_can_run_node(cfg) is False


def test_sif_can_run_node_trusts_sif_when_apptainer_unavailable(fake_sif, monkeypatch):
    """Login-node case: apptainer not on PATH, but SIF exists → trust it."""
    monkeypatch.setattr("shutil.which", lambda name: None)
    cfg = {"sandbox_sif_path": str(fake_sif)}
    assert doctor._sif_can_run_node(cfg) is True


def test_sif_can_run_node_picks_up_node_label(fake_sif, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/apptainer")
    fake_inspect = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=json.dumps({
            "data": {"attributes": {"labels": {
                "coding-agents.versions.node": "20.x-LTS",
                "coding-agents.versions.python": "3.12.x",
            }}}
        }),
        stderr="",
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fake_inspect)
    cfg = {"sandbox_sif_path": str(fake_sif)}
    assert doctor._sif_can_run_node(cfg) is True


def test_sif_can_run_node_returns_false_when_no_node_label(fake_sif, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/apptainer")
    fake_inspect = subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout=json.dumps({
            "data": {"attributes": {"labels": {
                "coding-agents.versions.python": "3.12.x",
            }}}
        }),
        stderr="",
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fake_inspect)
    cfg = {"sandbox_sif_path": str(fake_sif)}
    assert doctor._sif_can_run_node(cfg) is False
