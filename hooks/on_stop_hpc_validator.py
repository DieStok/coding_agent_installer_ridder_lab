#!/usr/bin/env python3
"""
HPC Folder Structure Validator - Stop Hook

Validates that any files created/modified during the coding agent session
follow the mandatory HPC project directory structure.

Structure required:
    /hpc/compgen/projects/<project>/
        <subproject>/
            raw/
            analysis/<username>/
        raw/  (optional)

Runs at the end of each agent conversation turn (Stop event).

v2: Scoped to CWD (not /hpc/compgen/projects/), uses git first, capped at 100 files.
"""
import json
import sys
import os
import re
import subprocess
from pathlib import Path
from datetime import datetime, timedelta


def get_username():
    """Get current HPC username."""
    return os.environ.get("USER", "unknown")


def get_recent_files(minutes=10):
    """Find files changed by the agent. Scoped to CWD, not entire /hpc/."""
    cwd = Path.cwd()

    # Strategy 1: Use git (fast, accurate)
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, timeout=10, cwd=cwd
        )
        if result.returncode == 0 and result.stdout.strip():
            files = [str(cwd / f.strip()) for f in result.stdout.strip().split("\n")]
            # Also untracked
            result2 = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                capture_output=True, text=True, timeout=10, cwd=cwd
            )
            if result2.returncode == 0 and result2.stdout.strip():
                files.extend(str(cwd / f.strip()) for f in result2.stdout.strip().split("\n") if f.strip())
            return [f for f in files if Path(f).exists()]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Strategy 2: find within CWD only (NOT /hpc/compgen/projects/)
    try:
        result = subprocess.run(
            ["find", str(cwd), "-maxdepth", "5", "-type", "f", "-mmin", f"-{minutes}",
             "-not", "-path", "*/.git/*"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()][:100]  # Cap at 100 files
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return []


def validate_path(filepath, username):
    """
    Validate if a file path follows the HPC structure.

    Valid locations:
    - /hpc/compgen/projects/<project>/<subproject>/raw/...
    - /hpc/compgen/projects/<project>/<subproject>/analysis/<username>/...
    - /hpc/compgen/projects/<project>/raw/...
    - /hpc/compgen/users/<username>/...

    Returns: (is_valid, error_message)
    """
    path = Path(filepath)
    parts = path.parts

    # Check if it's in /hpc/compgen/
    if not filepath.startswith("/hpc/compgen/"):
        return True, None  # Not in our managed area, skip

    # /hpc/compgen/users/<username>/ is always OK
    if filepath.startswith("/hpc/compgen/users/"):
        return True, None

    # Must be in /hpc/compgen/projects/
    if not filepath.startswith("/hpc/compgen/projects/"):
        return False, f"File outside allowed areas: {filepath}"

    # Parse the path: /hpc/compgen/projects/<project>/...
    # parts = ('/', 'hpc', 'compgen', 'projects', '<project>', ...)
    try:
        if len(parts) < 6:
            return False, f"Path too short, missing project structure: {filepath}"

        project = parts[4]  # <project>
        remaining = parts[5:]  # Everything after <project>

        if len(remaining) == 0:
            return False, f"Files cannot be directly in project root: {filepath}"

        first_dir = remaining[0]

        # Case 1: /hpc/compgen/projects/<project>/raw/...
        if first_dir == "raw":
            return True, None

        # Case 2: /hpc/compgen/projects/<project>/<subproject>/...
        subproject = first_dir

        if len(remaining) < 2:
            return False, f"Files cannot be directly in subproject root: {filepath}"

        second_dir = remaining[1]

        # Case 2a: /hpc/compgen/projects/<project>/<subproject>/raw/...
        if second_dir == "raw":
            return True, None

        # Case 2b: /hpc/compgen/projects/<project>/<subproject>/analysis/<username>/...
        if second_dir == "analysis":
            if len(remaining) < 3:
                return False, f"Files cannot be directly in analysis/: {filepath}"

            analysis_user = remaining[2]

            # Check if it's the current user's directory
            if analysis_user != username:
                return False, (
                    f"Writing to another user's analysis directory!\n"
                    f"  File: {filepath}\n"
                    f"  Expected: analysis/{username}/\n"
                    f"  Found: analysis/{analysis_user}/"
                )

            return True, None

        # Invalid: not in raw/ or analysis/
        return False, (
            f"Invalid location in project structure.\n"
            f"  File: {filepath}\n"
            f"  Files must be in:\n"
            f"    - <project>/raw/\n"
            f"    - <project>/<subproject>/raw/\n"
            f"    - <project>/<subproject>/analysis/{username}/"
        )

    except Exception as e:
        return False, f"Error parsing path {filepath}: {e}"


def check_naming_conventions(filepath):
    """
    Check for naming convention violations.
    Returns: (is_valid, warning_message)
    """
    path = Path(filepath)
    warnings = []

    # Only check project structure directories, not files inside analysis/<user>/
    if "/analysis/" in filepath:
        # Extract path up to and including the username dir
        match = re.match(r"(.*/analysis/[^/]+)", filepath)
        if match:
            structure_path = match.group(1)
        else:
            structure_path = filepath
    else:
        structure_path = filepath

    # Check for spaces in directory structure
    structure_parts = Path(structure_path).parts
    for part in structure_parts:
        if " " in part and part not in [".", ".."]:
            warnings.append(f"Space in directory name: '{part}'")

    # Check for dots in directory names (not files)
    for part in structure_parts[:-1]:  # Exclude filename
        if "." in part and not part.startswith("."):
            warnings.append(f"Dot in directory name: '{part}'")

    # Check for uppercase in project/subproject names
    if filepath.startswith("/hpc/compgen/projects/"):
        parts = Path(filepath).parts
        if len(parts) > 4:
            project = parts[4]
            if project != project.lower():
                warnings.append(f"Uppercase in project name: '{project}' (use lowercase)")
        if len(parts) > 5 and parts[5] not in ["raw", "analysis"]:
            subproject = parts[5]
            if subproject != subproject.lower():
                warnings.append(f"Uppercase in subproject name: '{subproject}' (use lowercase)")

    if warnings:
        return False, "\n".join(warnings)
    return True, None


def main():
    """Main hook logic."""
    username = get_username()

    # Get recently modified files
    recent_files = get_recent_files(minutes=10)

    if not recent_files:
        return None  # No files to check

    errors = []
    warnings = []

    for filepath in recent_files:
        # Skip hidden files and common temp files
        if "/.git/" in filepath or "/__pycache__/" in filepath:
            continue
        if filepath.endswith(".pyc") or filepath.endswith(".swp"):
            continue

        # Validate structure
        is_valid, error = validate_path(filepath, username)
        if not is_valid:
            errors.append(error)

        # Check naming conventions
        naming_ok, warning = check_naming_conventions(filepath)
        if not naming_ok:
            warnings.append(f"{filepath}:\n  {warning}")

    # Build response
    if errors or warnings:
        message_parts = []

        if errors:
            message_parts.append("❌ HPC STRUCTURE VIOLATIONS:")
            message_parts.extend(errors)
            message_parts.append("")
            message_parts.append("Required structure:")
            message_parts.append("  /hpc/compgen/projects/<project>/<subproject>/raw/")
            message_parts.append(f"  /hpc/compgen/projects/<project>/<subproject>/analysis/{username}/")

        if warnings:
            message_parts.append("")
            message_parts.append("⚠️ NAMING CONVENTION WARNINGS:")
            message_parts.extend(warnings)

        # Return as feedback to the agent (not blocking, just informative)
        return {
            "decision": "block",
            "reason": "\n".join(message_parts),
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": (
                    "Files were created outside the allowed HPC directory structure. "
                    "Please move them to the correct location or explain why this deviation is necessary."
                )
            }
        }

    return None


if __name__ == "__main__":
    import io
    from contextlib import redirect_stdout, redirect_stderr

    # Capture any stray output
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
        sys.exit(2)  # Exit 2 to signal the agent should address this

    sys.exit(0)
