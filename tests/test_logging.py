"""Tests for logging_setup.py — debug logging configuration."""
import logging
import tempfile
from pathlib import Path

import pytest


def test_configure_logging_off():
    from coding_agents.logging_setup import configure_logging

    result = configure_logging(debug=False)
    assert result is None
    logger = logging.getLogger("coding-agents")
    assert logger.level == logging.WARNING
    assert len(logger.handlers) == 0


def test_configure_logging_on_creates_file():
    from coding_agents.logging_setup import configure_logging

    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = configure_logging(debug=True, log_dir=Path(tmpdir))
        try:
            assert log_file is not None
            assert log_file.exists()
            assert "debug-" in log_file.name
            assert log_file.suffix == ".log"

            logger = logging.getLogger("coding-agents")
            assert logger.level == logging.DEBUG
            assert len(logger.handlers) == 2  # RichHandler + FileHandler
        finally:
            # Clean up handlers to avoid leaking into other tests
            configure_logging(debug=False)


def test_configure_logging_fallback_to_home():
    from coding_agents.logging_setup import configure_logging

    # Pass a non-existent log_dir to trigger fallback
    log_file = configure_logging(debug=True, log_dir=Path("/nonexistent/dir"))
    try:
        assert log_file is not None
        assert str(Path.home()) in str(log_file)
    finally:
        if log_file and log_file.exists():
            log_file.unlink()
        configure_logging(debug=False)


def test_configure_logging_writes_to_file():
    from coding_agents.logging_setup import configure_logging

    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = configure_logging(debug=True, log_dir=Path(tmpdir))
        try:
            logger = logging.getLogger("coding-agents")
            logger.info("test message from test_logging")

            # Flush handlers
            for h in logger.handlers:
                h.flush()

            content = log_file.read_text()
            assert "test message from test_logging" in content
            assert "INFO" in content
        finally:
            configure_logging(debug=False)


def test_log_timing():
    import time
    from coding_agents.logging_setup import configure_logging, log_timing

    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = configure_logging(debug=True, log_dir=Path(tmpdir))
        try:
            with log_timing("test_operation"):
                time.sleep(0.05)

            for h in logging.getLogger("coding-agents").handlers:
                h.flush()

            content = log_file.read_text()
            assert "test_operation: starting" in content
            assert "test_operation: completed in" in content
        finally:
            configure_logging(debug=False)


def test_configure_logging_clears_previous_handlers():
    from coding_agents.logging_setup import configure_logging

    with tempfile.TemporaryDirectory() as tmpdir:
        # Call twice — should not accumulate handlers
        configure_logging(debug=True, log_dir=Path(tmpdir))
        configure_logging(debug=True, log_dir=Path(tmpdir))

        logger = logging.getLogger("coding-agents")
        assert len(logger.handlers) == 2  # Still just 2, not 4
        configure_logging(debug=False)
