"""Phase 5: Doctor --scan-cron / --scan-systemd + path-shim/no-wrap checks."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from coding_agents.commands import doctor_vscode


# --------------------------------------------------------------------------- #
# scan_crontab
# --------------------------------------------------------------------------- #

def _fake_crontab(stdout: str, returncode: int = 0):
    return subprocess.CompletedProcess(
        args=["crontab", "-l"], returncode=returncode, stdout=stdout, stderr=""
    )


def test_scan_cron_warns_on_bare_claude(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: _fake_crontab("0 9 * * * claude --check\n"),
    )
    rows = doctor_vscode.scan_crontab()
    assert len(rows) == 1
    name, status, fix = rows[0]
    assert "claude" in name
    assert status == "warn"
    assert "agent-claude" in fix


def test_scan_cron_passes_on_absolute_path(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: _fake_crontab(
            "0 9 * * * /hpc/coding_agents/bin/agent-claude --check\n"
        ),
    )
    assert doctor_vscode.scan_crontab() == []


def test_scan_cron_skips_comment_lines(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: _fake_crontab("# do not run claude here\n"),
    )
    assert doctor_vscode.scan_crontab() == []


def test_scan_cron_handles_no_crontab(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: _fake_crontab("", returncode=1),
    )
    assert doctor_vscode.scan_crontab() == []


def test_scan_cron_finds_all_four_agents(monkeypatch):
    crontab = (
        "0 1 * * * claude --check\n"
        "0 2 * * * codex audit\n"
        "0 3 * * * opencode index\n"
        "0 4 * * * pi tick\n"
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _fake_crontab(crontab))
    rows = doctor_vscode.scan_crontab()
    assert len(rows) == 4


def test_scan_cron_does_not_match_substrings(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: _fake_crontab(
            "0 9 * * * /usr/local/bin/claudette --check\n"  # not the bare 'claude'
        ),
    )
    assert doctor_vscode.scan_crontab() == []


# --------------------------------------------------------------------------- #
# scan_systemd_units
# --------------------------------------------------------------------------- #

def test_scan_systemd_warns_on_bare_codex(monkeypatch):
    list_out = "codex-watcher.service enabled\n"

    def fake_run(cmd, *a, **kw):
        if "list-unit-files" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=list_out, stderr="")
        if "cat" in cmd:
            return subprocess.CompletedProcess(
                args=cmd, returncode=0,
                stdout="[Service]\nExecStart=codex --watch\n",
                stderr="",
            )
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    rows = doctor_vscode.scan_systemd_units()
    assert len(rows) == 1
    name, status, fix = rows[0]
    assert "codex-watcher" in name
    assert status == "warn"


def test_scan_systemd_passes_on_absolute_path(monkeypatch):
    list_out = "watcher.service enabled\n"

    def fake_run(cmd, *a, **kw):
        if "list-unit-files" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=list_out, stderr="")
        if "cat" in cmd:
            return subprocess.CompletedProcess(
                args=cmd, returncode=0,
                stdout="[Service]\nExecStart=/hpc/.../bin/agent-claude --check\n",
                stderr="",
            )
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert doctor_vscode.scan_systemd_units() == []


def test_scan_systemd_handles_no_systemctl(monkeypatch):
    def boom(cmd, *a, **kw):
        raise FileNotFoundError("no systemctl")
    monkeypatch.setattr(subprocess, "run", boom)
    assert doctor_vscode.scan_systemd_units() == []


# --------------------------------------------------------------------------- #
# CODING_AGENTS_NO_WRAP acknowledgement
# --------------------------------------------------------------------------- #

def test_no_wrap_check_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("CODING_AGENTS_NO_WRAP", raising=False)
    assert doctor_vscode.no_wrap_acknowledgement() is None


def test_no_wrap_check_warns_when_set(monkeypatch):
    monkeypatch.setenv("CODING_AGENTS_NO_WRAP", "1")
    row = doctor_vscode.no_wrap_acknowledgement()
    assert row is not None
    name, status, fix = row
    assert status == "warn"
    assert "unsandboxed" in fix
