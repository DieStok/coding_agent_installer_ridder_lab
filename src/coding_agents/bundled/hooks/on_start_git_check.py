#!/usr/bin/env python3
"""
SessionStart Hook: Git Repo Check

If `entire` is installed and the current directory is not inside a git
repository, informs the agent so it can offer to initialize one.

Non-blocking.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def is_git_repo():
    """Check if CWD is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def entire_installed():
    """Check if entire CLI is available."""
    return shutil.which("entire") is not None


def main():
    if not entire_installed():
        return None  # entire not installed, skip

    if is_git_repo():
        return None  # Already in a git repo, nothing to do

    return {
        "decision": "approve",
        "reason": (
            "⚠️ No git repository detected in the current directory.\n"
            "`entire` session recording requires a git repo.\n"
            "Consider running `git init` to enable session recording,\n"
            "or ignore this if you don't need session tracking here."
        ),
    }


if __name__ == "__main__":
    import io
    from contextlib import redirect_stdout, redirect_stderr

    captured_out = io.StringIO()
    captured_err = io.StringIO()

    result = None
    try:
        with redirect_stdout(captured_out), redirect_stderr(captured_err):
            result = main()
    except Exception:
        sys.exit(0)

    if result is not None:
        print(json.dumps(result))

    sys.exit(0)
