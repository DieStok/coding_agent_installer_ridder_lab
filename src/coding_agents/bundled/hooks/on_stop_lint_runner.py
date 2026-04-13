#!/usr/bin/env python3
"""
Stop Hook: Lint Runner

Detects files changed during the session and runs the appropriate linter
for each file type. Returns findings as context to the agent.

Non-blocking — surfaces errors but does not prevent the agent from continuing.

Linters used:
  - Python (.py): ruff check, vulture, pyright
  - YAML (.yml, .yaml): yamllint
  - JSON (.json): biome check
  - Shell (.sh, .bash): shellcheck
"""
import json
import os
import subprocess
import sys
from pathlib import Path


def get_tool_path(tool_name):
    """Find tool in the coding-agents tools venv or PATH."""
    install_dir = os.environ.get("CODING_AGENT_INSTALL_DIR", "")

    # Check tools venv first
    if install_dir:
        venv_bin = Path(install_dir) / "tools" / ".venv" / "bin" / tool_name
        if venv_bin.exists():
            return str(venv_bin)
        # Check tools node_modules
        node_bin = Path(install_dir) / "tools" / "node_modules" / ".bin" / tool_name
        if node_bin.exists():
            return str(node_bin)
        # Check tools/bin (for shellcheck static binary)
        static_bin = Path(install_dir) / "tools" / "bin" / tool_name
        if static_bin.exists():
            return str(static_bin)

    # Fallback to PATH
    import shutil
    return shutil.which(tool_name)


def run_tool(cmd, timeout=30):
    """Run a linting tool and capture output."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        output = result.stdout.strip()
        if result.stderr.strip():
            output += "\n" + result.stderr.strip()
        return output if output else None
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return f"[timeout after {timeout}s]"


def get_changed_files(minutes=15):
    """Find files changed recently. Uses git if available, else find."""
    try:
        # Try git first
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
            # Also include untracked files
            result2 = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                capture_output=True, text=True, timeout=10
            )
            if result2.returncode == 0 and result2.stdout.strip():
                files.extend(f.strip() for f in result2.stdout.strip().split("\n") if f.strip())
            return [f for f in files if Path(f).exists()]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: find recently modified files
    try:
        result = subprocess.run(
            ["find", ".", "-maxdepth", "5", "-type", "f", "-mmin", f"-{minutes}",
             "-not", "-path", "./.git/*", "-not", "-path", "./__pycache__/*",
             "-not", "-name", "*.pyc"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return []


def lint_python(files):
    """Run Python linters on changed .py files."""
    py_files = [f for f in files if f.endswith(".py")]
    if not py_files:
        return []

    findings = []

    # ruff
    ruff = get_tool_path("ruff")
    if ruff:
        output = run_tool([ruff, "check", "--output-format=concise"] + py_files)
        if output:
            findings.append(f"**ruff:**\n{output}")

    # vulture
    vulture = get_tool_path("vulture")
    if vulture:
        output = run_tool([vulture] + py_files + ["--min-confidence", "80"])
        if output:
            findings.append(f"**vulture (dead code):**\n{output}")

    # pyright
    pyright = get_tool_path("pyright")
    if pyright:
        output = run_tool([pyright] + py_files, timeout=60)
        if output and "error" in output.lower():
            findings.append(f"**pyright:**\n{output}")

    return findings


def lint_yaml(files):
    """Run yamllint on .yml/.yaml files."""
    yaml_files = [f for f in files if f.endswith((".yml", ".yaml"))]
    if not yaml_files:
        return []

    yamllint = get_tool_path("yamllint")
    if not yamllint:
        return []

    findings = []
    for f in yaml_files:
        output = run_tool([yamllint, "-d", "relaxed", f])
        if output:
            findings.append(f"**yamllint** ({f}):\n{output}")
    return findings


def lint_json(files):
    """Run biome check on .json files."""
    json_files = [f for f in files if f.endswith(".json") and not f.endswith("package-lock.json")]
    if not json_files:
        return []

    biome = get_tool_path("biome")
    if not biome:
        return []

    findings = []
    output = run_tool([biome, "check", "--formatter-enabled=false"] + json_files)
    if output:
        findings.append(f"**biome (JSON):**\n{output}")
    return findings


def lint_shell(files):
    """Run shellcheck on .sh/.bash files."""
    sh_files = [f for f in files if f.endswith((".sh", ".bash"))]
    if not sh_files:
        return []

    shellcheck = get_tool_path("shellcheck")
    if not shellcheck:
        return []

    findings = []
    output = run_tool([shellcheck, "-f", "gcc"] + sh_files)
    if output:
        findings.append(f"**shellcheck:**\n{output}")
    return findings


def main():
    files = get_changed_files()
    if not files:
        return None

    all_findings = []
    all_findings.extend(lint_python(files))
    all_findings.extend(lint_yaml(files))
    all_findings.extend(lint_json(files))
    all_findings.extend(lint_shell(files))

    if not all_findings:
        return None  # Clean — no issues found

    message = "🔍 **Lint results for changed files:**\n\n" + "\n\n".join(all_findings)

    return {
        "decision": "approve",  # Non-blocking
        "reason": message,
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
        sys.exit(2)  # Signal agent should address findings

    sys.exit(0)
