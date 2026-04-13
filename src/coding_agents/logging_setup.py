"""Logging configuration for coding-agents.

When --debug is active: comprehensive logging to stderr (Rich) + timestamped file.
When --debug is off: logger at WARNING with no handlers (zero overhead).
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler


def configure_logging(
    debug: bool,
    log_dir: Path | None = None,
    dry_run: bool = False,
) -> Path | None:
    """Configure the coding-agents logger.

    Args:
        debug: If True, enable DEBUG level with stderr + file handlers.
        log_dir: Directory for log files. Falls back to
            ``~/.coding-agents-debug-*.log`` (or ``~/.coding-agents-dry-run-*.log``
            when ``dry_run=True``).
        dry_run: If True, force debug-level logging on, switch the filename
            prefix to ``dry-run-*.log`` so real-run and dry-run logs are never
            confused, and emit a prominent ``DRY-RUN MODE`` banner.

    Returns:
        Path to the log file if debug/dry-run is active, else None.
    """
    logger = logging.getLogger("coding-agents")
    logger.handlers.clear()
    logger.propagate = False

    # Dry-run always implies comprehensive logging — the whole point is
    # observability of the simulated run.
    if dry_run:
        debug = True

    if not debug:
        logger.setLevel(logging.WARNING)
        return None

    logger.setLevel(logging.DEBUG)

    # Handler 1: Rich stderr (human-readable, colorized)
    stderr_console = Console(stderr=True, force_terminal=True)
    rich_handler = RichHandler(
        level=logging.DEBUG,
        console=stderr_console,
        show_path=False,
        show_time=True,
        markup=True,
        rich_tracebacks=True,
        tracebacks_show_locals=True,
    )
    rich_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(rich_handler)

    # Handler 2: File (machine-parseable, agent-feedable)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    prefix = "dry-run" if dry_run else "debug"
    log_file: Path
    if log_dir and log_dir.exists():
        log_file = log_dir / f"{prefix}-{timestamp}.log"
    else:
        log_file = Path.home() / f".coding-agents-{prefix}-{timestamp}.log"

    # Create the log file directly with 0o600. We don't route through
    # secure_write_text because that is dry-run-aware and would refuse to
    # create the file we need to write to.
    import os as _os

    log_file.parent.mkdir(parents=True, exist_ok=True)
    fd = _os.open(str(log_file), _os.O_WRONLY | _os.O_CREAT | _os.O_TRUNC, 0o600)
    _os.close(fd)

    file_handler = logging.FileHandler(str(log_file))
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s.%(msecs)03d %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(file_handler)

    if dry_run:
        logger.warning("DRY-RUN MODE — NO CHANGES WILL BE MADE")
    logger.info("%s logging enabled — writing to %s",
                "Dry-run" if dry_run else "Debug", log_file)
    return log_file


@contextmanager
def log_timing(operation: str):
    """Log how long an operation takes (debug level)."""
    logger = logging.getLogger("coding-agents")
    start = time.monotonic()
    logger.debug("%s: starting", operation)
    try:
        yield
    finally:
        elapsed = time.monotonic() - start
        logger.debug("%s: completed in %.1fs", operation, elapsed)
