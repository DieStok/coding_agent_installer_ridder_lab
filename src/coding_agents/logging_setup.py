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


def configure_logging(debug: bool, log_dir: Path | None = None) -> Path | None:
    """Configure the coding-agents logger.

    Args:
        debug: If True, enable DEBUG level with stderr + file handlers.
        log_dir: Directory for log files. Falls back to ~/.coding-agents-debug-*.log.

    Returns:
        Path to the debug log file if debug=True, else None.
    """
    logger = logging.getLogger("coding-agents")
    logger.handlers.clear()
    logger.propagate = False

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
    log_file: Path
    if log_dir and log_dir.exists():
        log_file = log_dir / f"debug-{timestamp}.log"
    else:
        log_file = Path.home() / f".coding-agents-debug-{timestamp}.log"

    from coding_agents.utils import secure_write_text

    # Create the file with 0o600 permissions, then open for appending
    secure_write_text(log_file, "")
    file_handler = logging.FileHandler(str(log_file))
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s.%(msecs)03d %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(file_handler)

    logger.info("Debug logging enabled — writing to %s", log_file)
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
