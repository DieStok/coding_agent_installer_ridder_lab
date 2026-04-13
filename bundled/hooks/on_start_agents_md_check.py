#!/usr/bin/env python3
"""
SessionStart Hook: AGENTS.md Check

If the current working directory has no AGENTS.md (or CLAUDE.md),
creates a minimal one from the PROJECT_LOCAL_AGENTS_TEMPLATE.md template.

Non-blocking — informs the agent that the file was created.
"""
import json
import os
import sys
from pathlib import Path


def get_template_path():
    """Find the template file."""
    install_dir = os.environ.get("CODING_AGENT_INSTALL_DIR", "")
    if install_dir:
        p = Path(install_dir) / "config" / "templates" / "PROJECT_LOCAL_AGENTS_TEMPLATE.md"
        if p.exists():
            return p
    return None


def main():
    cwd = Path.cwd()

    # Check if AGENTS.md or CLAUDE.md already exists
    for name in ["AGENTS.md", "CLAUDE.md", "agents.md"]:
        if (cwd / name).exists():
            return None  # Already exists, nothing to do

    # Find template
    template_path = get_template_path()
    if not template_path:
        return None  # No template available, skip silently

    # Read template and fill placeholders
    template = template_path.read_text()
    project_name = cwd.name
    username = os.environ.get("USER", "unknown")

    content = template.replace("{PROJECT_NAME}", project_name)
    content = content.replace("{USERNAME}", username)

    # Write AGENTS.md
    agents_md = cwd / "AGENTS.md"
    try:
        agents_md.write_text(content)
    except PermissionError:
        return None  # Can't write here, skip

    # Create CLAUDE.md symlink for Claude Code compatibility
    claude_md = cwd / "CLAUDE.md"
    if not claude_md.exists():
        try:
            claude_md.symlink_to("AGENTS.md")
        except (PermissionError, OSError):
            pass  # Non-critical

    return {
        "decision": "approve",
        "reason": (
            f"📝 Created AGENTS.md in {cwd} from template.\n"
            f"Edit it to describe your project's conventions and structure."
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
