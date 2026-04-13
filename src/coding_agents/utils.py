"""Utility helpers — subprocess wrappers, NFS-safe symlinks, shell integration."""
from __future__ import annotations

import errno
import logging
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger("coding-agents")

# Strict regex for paths safe to interpolate into shell code
_SAFE_PATH_RE = re.compile(r'^[a-zA-Z0-9/_.\-~]+$')


# ---------------------------------------------------------------------------
# Secure file writing
# ---------------------------------------------------------------------------

def secure_write_text(path: Path, content: str) -> None:
    """Write text file with 0o600 permissions (owner-only read/write).

    Uses os.open() to set permissions at creation time — no window where
    the file is world-readable. Essential on shared HPC clusters.
    """
    log.debug("secure_write_text: %s (%d bytes)", path, len(content))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, content.encode())
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# Subprocess
# ---------------------------------------------------------------------------

def run(
    cmd: list[str] | str,
    *,
    timeout: int = 300,
    check: bool = True,
    shell: bool = False,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    """Run a command with NFS retry on errno 116 (stale file handle)."""
    log.debug("run: cmd=%s cwd=%s timeout=%d", cmd, cwd, timeout)
    merged_env = {**os.environ, **(env or {})}
    kwargs = dict(
        timeout=timeout,
        check=False,
        shell=shell,
        cwd=str(cwd) if cwd else None,
        env=merged_env,
    )
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True

    for attempt in range(2):
        try:
            result = subprocess.run(cmd, **kwargs)
            stdout_preview = (getattr(result, "stdout", "") or "")[:200]
            stderr_preview = (getattr(result, "stderr", "") or "")[:200]
            log.debug("run: rc=%d stdout=%r stderr=%r", result.returncode, stdout_preview, stderr_preview)
            if check and result.returncode != 0:
                log.error("run: cmd=%s failed rc=%d: %s", cmd, result.returncode, stderr_preview)
                raise subprocess.CalledProcessError(
                    result.returncode, cmd,
                    output=getattr(result, "stdout", None),
                    stderr=getattr(result, "stderr", None),
                )
            return result
        except OSError as exc:
            if exc.errno == errno.ESTALE and attempt == 0:
                log.debug("Stale NFS handle, retrying: %s", cmd)
                continue
            raise
    # Unreachable, but satisfies type checker
    raise RuntimeError("retry exhausted")


# ---------------------------------------------------------------------------
# NFS-safe symlink
# ---------------------------------------------------------------------------

def safe_symlink(source: Path, target: Path) -> None:
    """Create a symlink atomically (NFS-safe: temp in same dir then rename).

    If *target* already exists as a regular file, it is backed up to .bak.
    """
    log.debug("safe_symlink: %s → %s", source, target)
    target = target.resolve() if target.exists() else target
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.is_symlink():
        target.unlink()
    elif target.exists():
        backup = target.with_suffix(target.suffix + ".bak")
        log.info("Backing up %s → %s", target, backup)
        target.rename(backup)

    # Create temp symlink in same dir, then atomic rename
    fd, tmp = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=f".tmp-{os.getpid()}-",
    )
    os.close(fd)
    os.unlink(tmp)  # mkstemp creates a file; we need the name only
    os.symlink(str(source), tmp)
    os.rename(tmp, str(target))


# ---------------------------------------------------------------------------
# npm install (NFS-safe)
# ---------------------------------------------------------------------------

def npm_install(prefix: Path, package: str) -> subprocess.CompletedProcess:
    """Install an npm package with NFS-safe flags."""
    log.debug("npm_install: package=%s prefix=%s", package, prefix)
    cache_dir = prefix / ".npm-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return run(
        [
            "npm", "install",
            "--prefix", str(prefix),
            "--no-package-lock",
            "--no-optional",
            "--cache", str(cache_dir),
            package,
        ],
        check=True,
    )


# ---------------------------------------------------------------------------
# uv / venv helpers
# ---------------------------------------------------------------------------

def uv_create_venv(venv_path: Path, python: str = "python3.12") -> None:
    """Create a venv with uv."""
    log.debug("uv_create_venv: path=%s python=%s", venv_path, python)
    run(["uv", "venv", str(venv_path), "--python", python], check=True)


def uv_pip_install(venv_path: Path, packages: list[str], *, upgrade: bool = False) -> None:
    """Install packages into a uv-managed venv."""
    log.debug("uv_pip_install: packages=%s upgrade=%s venv=%s", packages, upgrade, venv_path)
    install_dir = venv_path.parent.parent  # tools/.venv -> install_dir/tools
    cache_dir = install_dir / ".uv-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    cmd = ["uv", "pip", "install", "--python", str(venv_path / "bin" / "python")]
    if upgrade:
        cmd.append("--upgrade")
    cmd.extend(packages)
    run(cmd, env={"UV_CACHE_DIR": str(cache_dir)}, check=True)


# ---------------------------------------------------------------------------
# Shell integration
# ---------------------------------------------------------------------------

SHELL_MARKERS = ("# >>> coding-agents >>>", "# <<< coding-agents <<<")


def inject_shell_block(install_dir: Path) -> list[Path]:
    """Add PATH/env block to ~/.bashrc and ~/.zshrc (if zsh). Returns modified files."""
    log.debug("inject_shell_block: install_dir=%s", install_dir)
    path_str = str(install_dir)
    if not _SAFE_PATH_RE.match(path_str):
        raise ValueError(f"Install path contains unsafe characters: {path_str}")
    quoted = shlex.quote(path_str)
    block = f"""{SHELL_MARKERS[0]}
export CODING_AGENT_INSTALL_DIR={quoted}
export PATH="$CODING_AGENT_INSTALL_DIR/bin:$CODING_AGENT_INSTALL_DIR/node_modules/.bin:$PATH"
export CODING_AGENTS_TOOLS_VENV="$CODING_AGENT_INSTALL_DIR/tools/.venv"
export JAI_CONFIG_DIR="$CODING_AGENT_INSTALL_DIR/jai"
{SHELL_MARKERS[1]}"""

    rc_files = [Path.home() / ".bashrc"]
    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        rc_files.append(Path.home() / ".zshrc")

    modified = []
    for rc in rc_files:
        _write_guarded_block(rc, block)
        modified.append(rc)
    return modified


def remove_shell_block() -> list[Path]:
    """Remove the coding-agents block from shell rc files."""
    modified = []
    for rc in [Path.home() / ".bashrc", Path.home() / ".zshrc"]:
        if not rc.exists():
            continue
        content = rc.read_text()
        if SHELL_MARKERS[0] in content:
            lines = content.splitlines(keepends=True)
            new_lines = []
            inside = False
            for line in lines:
                if SHELL_MARKERS[0] in line:
                    inside = True
                    continue
                if SHELL_MARKERS[1] in line:
                    inside = False
                    continue
                if not inside:
                    new_lines.append(line)
            rc.write_text("".join(new_lines))
            modified.append(rc)
    return modified


def _write_guarded_block(rc_file: Path, block: str) -> None:
    """Write a marker-guarded block, replacing any existing one."""
    if rc_file.exists():
        content = rc_file.read_text()
    else:
        content = ""

    if SHELL_MARKERS[0] in content:
        # Replace existing block
        lines = content.splitlines(keepends=True)
        new_lines = []
        inside = False
        for line in lines:
            if SHELL_MARKERS[0] in line:
                inside = True
                continue
            if SHELL_MARKERS[1] in line:
                inside = False
                continue
            if not inside:
                new_lines.append(line)
        content = "".join(new_lines)

    # Append
    if not content.endswith("\n"):
        content += "\n"
    content += "\n" + block + "\n"
    rc_file.write_text(content)


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def detect_platform() -> dict[str, str | bool | None]:
    """Detect OS, arch, available commands, and local-mode specifics."""
    import platform

    info = {
        "os": platform.system().lower(),
        "arch": platform.machine(),
        "kernel": platform.release(),
        "is_macos": platform.system() == "Darwin",
        "is_linux": platform.system() == "Linux",
        "node": shutil.which("node") is not None,
        "npm": shutil.which("npm") is not None,
        "uv": shutil.which("uv") is not None,
        "git": shutil.which("git") is not None,
        "code": shutil.which("code") is not None,
        "brew": shutil.which("brew") is not None,
        "python3": shutil.which("python3"),
        "nvm": Path.home().joinpath(".nvm").exists(),
    }
    log.debug("detect_platform: %s", info)
    return info
