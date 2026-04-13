"""Dry-run machinery for coding-agents.

When dry-run is active, mutating utilities short-circuit: they log what
*would* have happened (via `would()`) and return a mock result of the
shape the caller expects. All logging flows through the same
`coding-agents` logger used by --debug, so the stderr RichHandler and
file handler both render dry-run lines without any additional plumbing.

This module deliberately has NO runtime imports from other
``coding_agents.*`` modules — ``utils.py`` imports from here, so a back
import would create a cycle.
"""
from __future__ import annotations

import hashlib
import logging
import subprocess
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_log = logging.getLogger("coding-agents")
_DRY_RUN: bool = False


def is_dry_run() -> bool:
    """Return True if dry-run mode is active."""
    return _DRY_RUN


def set_dry_run(enabled: bool) -> None:
    """Enable or disable dry-run mode (process-wide)."""
    global _DRY_RUN
    _DRY_RUN = enabled


# ---------------------------------------------------------------------------
# Recorder
# ---------------------------------------------------------------------------


@dataclass
class DryRunRecorder:
    """Collects the actions that WOULD have happened during a dry-run.

    ``actions`` is a list of ``(category, action, fields)`` triples.
    """

    actions: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, category: str, action: str, **fields: Any) -> None:
        with self._lock:
            self.actions.append((category, action, fields))

    def counts(self) -> dict[str, int]:
        with self._lock:
            c: dict[str, int] = defaultdict(int)
            for cat, _, _ in self.actions:
                c[cat] += 1
        return dict(c)

    def reset(self) -> None:
        with self._lock:
            self.actions.clear()


_RECORDER = DryRunRecorder()


def get_recorder() -> DryRunRecorder:
    """Return the module-level recorder singleton (for tests)."""
    return _RECORDER


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------


def _fmt(value: Any) -> str:
    """Format a field value for structured log lines."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return repr(list(value))
    s = str(value)
    if len(s) > 200:
        return s[:200] + f"...({len(s)}c)"
    return s


def would(category: str, action: str, **fields: Any) -> None:
    """Log and record an action that WOULD happen in a real run.

    Args:
        category: Coarse bucket for the summary (e.g. ``subprocess``,
            ``file_write``, ``symlink``, ``mkdir``, ``shell_rc``,
            ``json_merge``, ``backup``, ``network``, ``prompt``,
            ``config_save``, ``file_copy``, ``file_delete``, ``archive``).
        action: Specific operation name (e.g. ``run``, ``create``,
            ``copy2``, ``rmtree``).
        **fields: Structured key/value details logged and recorded.
    """
    field_str = " ".join(f"{k}={_fmt(v)}" for k, v in fields.items())
    _log.info("[DRY-RUN] %s :: %s %s", category, action, field_str)
    _RECORDER.record(category, action, **fields)


def emit_summary() -> None:
    """Emit an end-of-run grouped summary via the coding-agents logger."""
    total = len(_RECORDER.actions)
    if total == 0:
        _log.warning("DRY-RUN SUMMARY — no actions were recorded")
        return

    _log.warning("=" * 60)
    _log.warning("DRY-RUN SUMMARY — %d actions would have been performed", total)
    for category, count in sorted(_RECORDER.counts().items()):
        _log.warning("  %-15s %4d", category, count)
    _log.warning("=" * 60)
    # Full detail — renders in the file log and (at DEBUG level) in stderr.
    for cat, action, fields in _RECORDER.actions:
        detail = " ".join(f"{k}={_fmt(v)}" for k, v in fields.items())
        _log.debug("  [%s] %s %s", cat, action, detail)


# ---------------------------------------------------------------------------
# Helpers for callers
# ---------------------------------------------------------------------------


def content_fingerprint(content: str | bytes) -> str:
    """Return the 8-char sha256 prefix of ``content`` — for logging identity
    without leaking the content itself."""
    data = content.encode() if isinstance(content, str) else content
    return hashlib.sha256(data).hexdigest()[:8]


def fake_completed_process(
    cmd: list[str] | str,
    *,
    capture: bool = True,
    returncode: int = 0,
) -> subprocess.CompletedProcess:
    """Return a ``subprocess.CompletedProcess`` with shape matching a real run.

    When ``capture`` is True, stdout/stderr are empty strings (text mode);
    otherwise they are None (the real subprocess API returns None when the
    streams weren't captured).
    """
    return subprocess.CompletedProcess(
        args=cmd,
        returncode=returncode,
        stdout="" if capture else None,
        stderr="" if capture else None,
    )
