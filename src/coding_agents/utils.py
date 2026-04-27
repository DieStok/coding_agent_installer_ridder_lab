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

from coding_agents.dry_run import (
    content_fingerprint,
    fake_completed_process,
    is_dry_run,
    would,
)

log = logging.getLogger("coding-agents")

# Strict regex for paths safe to interpolate into shell code
_SAFE_PATH_RE = re.compile(r'^[a-zA-Z0-9/_.\-~]+$')


# ---------------------------------------------------------------------------
# Secure file writing
# ---------------------------------------------------------------------------

def secure_write_text(path: Path, content: str) -> None:
    """Atomically write a text file with 0o600 permissions.

    Synthesis §3.3 / Sprint 1 Task 1.2: the previous implementation opened
    with ``O_WRONLY|O_CREAT|O_TRUNC`` and a single ``os.write()``. A
    ``Ctrl-C`` / ``scancel`` / OOM mid-write left a zero-byte file. Since
    callers like ``config.load_config`` swallow ``JSONDecodeError``, that
    silently corrupted the user's settings.

    POSIX safe-replace pattern instead:

      1. ``mkstemp`` in the same directory as the target → unique file
         created with 0o600 by mkstemp's own design.
      2. Write content via ``os.write`` (no buffering).
      3. ``os.fsync(fd)`` so the data is on disk before the rename.
      4. ``os.replace(tmp, path)`` — atomic on POSIX (same filesystem
         guaranteed since both live in the same dir).
      5. ``os.fsync`` the parent dir so the rename itself survives a
         crash.

    Effect: any concurrent reader sees either the old content or the
    new content — never a half-written or zero-byte file. A crash before
    step 4 leaves the temp file behind (cleaned up by ``mkstemp``'s
    automatic registration on process exit if we still hold the fd; the
    finally block also unlinks). A crash after step 4 is fully durable
    once step 5 returns.

    Permissions discipline (0o600) is preserved: the file never exists
    with broader permissions because ``mkstemp`` creates it 0o600 from
    the start. Synthesis §2.5 documents this as the right shape.
    """
    log.debug("secure_write_text: %s (%d bytes)", path, len(content))
    if is_dry_run():
        would(
            "file_write",
            "secure_write_text",
            path=path,
            bytes=len(content),
            sha8=content_fingerprint(content),
            mode="0o600",
        )
        return

    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)

    payload = content.encode()

    # mkstemp returns (fd, path) with permissions 0o600 (owner-only) on
    # POSIX. Putting the temp in the same dir as the target is required
    # for os.replace to be atomic.
    fd, tmp_path_str = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(parent),
    )
    tmp_path = Path(tmp_path_str)
    try:
        # Single write — no buffering layer between our bytes and the kernel.
        # tempfile.mkstemp may have set arbitrary umask-derived perms on
        # some platforms; force 0o600 explicitly for defence-in-depth.
        os.fchmod(fd, 0o600)
        n = os.write(fd, payload)
        if n != len(payload):  # short write; rare on local fs but possible on NFS
            # Fall back to a loop for the remainder.
            written = n
            while written < len(payload):
                written += os.write(fd, payload[written:])
        os.fsync(fd)
        os.close(fd)
        fd = -1  # marker: don't close again in finally

        os.replace(tmp_path, path)

        # fsync the parent dir so the rename is durable.
        try:
            dir_fd = os.open(str(parent), os.O_DIRECTORY)
        except OSError:
            # Some filesystems don't support O_DIRECTORY fsync (e.g. tmpfs
            # in certain setups). Best-effort; the rename itself is atomic.
            return
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except BaseException:
        # On any failure (including KeyboardInterrupt), best-effort
        # cleanup of the temp file. The target is left untouched.
        if fd != -1:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


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
    stdin_devnull: bool = True,
) -> subprocess.CompletedProcess:
    """Run a command with NFS retry on errno 116 (stale file handle).

    `stdin_devnull` defaults to True so installer scripts that try to read
    from stdin (e.g. `curl … | bash` running an interactive prompt) can't
    silently hang the TUI. Pass False if the caller actually needs to feed
    stdin.
    """
    log.debug("run: cmd=%s cwd=%s timeout=%d", cmd, cwd, timeout)
    if is_dry_run():
        would(
            "subprocess",
            "run",
            cmd=cmd,
            cwd=cwd,
            shell=shell,
            timeout=timeout,
            env_overlay=sorted((env or {}).keys()),
        )
        return fake_completed_process(cmd, capture=capture)
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
    if stdin_devnull:
        kwargs["stdin"] = subprocess.DEVNULL

    # Lazy import — avoids circular import (observer imports nothing from
    # utils, but we keep it lazy for safety).
    from coding_agents.installer.observer import emit_verbose

    for attempt in range(2):
        try:
            result = subprocess.run(cmd, **kwargs)
            stdout_preview = (getattr(result, "stdout", "") or "")[:200]
            stderr_preview = (getattr(result, "stderr", "") or "")[:200]
            log.debug("run: rc=%d stdout=%r stderr=%r", result.returncode, stdout_preview, stderr_preview)
            # Emit captured output to the verbose pane (no-op if no sink set).
            cmd_label = cmd[0] if isinstance(cmd, list) else cmd.split()[0]
            stdout_full = getattr(result, "stdout", "") or ""
            stderr_full = getattr(result, "stderr", "") or ""
            if stdout_full:
                emit_verbose(f"$ {cmd_label} (stdout)\n{stdout_full}")
            if stderr_full:
                emit_verbose(f"$ {cmd_label} (stderr)\n{stderr_full}")
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
    if is_dry_run():
        would(
            "symlink",
            "create",
            src=source,
            target=target,
            replaces_existing=target.exists() or target.is_symlink(),
        )
        return
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
    """Install an npm package with NFS-safe flags.

    Note: we deliberately keep optionalDependencies enabled — many modern CLIs
    (OpenCode, esbuild, biome, ...) ship per-platform native binaries via
    `optionalDependencies` and `--no-optional` strips them, leaving a broken
    install with exit 1.
    """
    log.debug("npm_install: package=%s prefix=%s", package, prefix)
    cache_dir = prefix / ".npm-cache"
    if is_dry_run():
        would("mkdir", "create_dir", path=cache_dir, parents=True, exist_ok=True)
    else:
        cache_dir.mkdir(parents=True, exist_ok=True)
    return run(
        [
            "npm", "install",
            "--prefix", str(prefix),
            "--no-package-lock",
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
    if is_dry_run():
        would("mkdir", "create_dir", path=cache_dir, parents=True, exist_ok=True)
    else:
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
# Phase-4 path-shim block — separate marker pair so the existing block
# stays untouched. Order matters: shim block injected AFTER the main block
# so any conda/uv/pyenv re-prepends from upstream rc files don't clobber
# our prefix.
SHELL_MARKERS_PATH_SHIM = (
    "# >>> coding-agents-path-shim >>>",
    "# <<< coding-agents-path-shim <<<",
)


def render_shell_block(
    install_dir: Path,
    *,
    sandbox_sif_path: str = "",
    sandbox_secrets_dir: str = "",
    sandbox_logs_dir: str = "",
) -> str:
    """Pure function: build the rc-file shell block.

    Extracted so the rendering logic is unit-testable without touching
    ~/.zshrc. ``inject_shell_block`` is the I/O wrapper that calls this.
    """
    path_str = str(install_dir)
    if not _SAFE_PATH_RE.match(path_str):
        raise ValueError(f"Install path contains unsafe characters: {path_str}")
    quoted = shlex.quote(path_str)
    lines = [
        SHELL_MARKERS[0],
        f"export CODING_AGENT_INSTALL_DIR={quoted}",
        'export PATH="$CODING_AGENT_INSTALL_DIR/bin:$CODING_AGENT_INSTALL_DIR/node_modules/.bin:$PATH"',
        'export CODING_AGENTS_TOOLS_VENV="$CODING_AGENT_INSTALL_DIR/tools/.venv"',
    ]
    if sandbox_sif_path:
        lines.append(f"export AGENT_SIF={shlex.quote(sandbox_sif_path)}")
    if sandbox_secrets_dir:
        lines.append(f"export AGENT_SECRETS_DIR={shlex.quote(sandbox_secrets_dir)}")
    if sandbox_logs_dir:
        lines.append(f"export AGENT_LOGS_DIR={shlex.quote(sandbox_logs_dir)}")
    lines.append(SHELL_MARKERS[1])
    return "\n".join(lines)


def render_path_shim_block(install_dir: Path) -> str:
    """Build the second rc block that prepends the OpenCode path-shim dir.

    A separate marker block (rather than appending to the main block) so:
      1. The existing block's tests don't change.
      2. ``coding-agents uninstall`` can remove the shim block without
         touching the main block (or vice-versa) for partial rollbacks.
      3. Conda/uv/pyenv blocks that prepend their own bin dirs run first
         (typical .bashrc order); our path-shim then wins on the next line.
    """
    path_str = str(install_dir / "bin" / "path-shim")
    if not _SAFE_PATH_RE.match(path_str):
        raise ValueError(f"Path-shim path contains unsafe characters: {path_str}")
    quoted = shlex.quote(path_str)
    return "\n".join([
        SHELL_MARKERS_PATH_SHIM[0],
        f'export PATH={quoted}:"$PATH"',
        SHELL_MARKERS_PATH_SHIM[1],
    ])


def inject_shell_block(
    install_dir: Path,
    *,
    sandbox_sif_path: str = "",
    sandbox_secrets_dir: str = "",
    sandbox_logs_dir: str = "",
    inject_path_shim: bool = False,
) -> list[Path]:
    """Add PATH/env block to ~/.bashrc and ~/.zshrc (if zsh). Returns modified files.

    When ``inject_path_shim=True`` a second marker block is appended after
    the main block to prepend ``<install_dir>/bin/path-shim`` to ``$PATH``
    (Phase 4 — OpenCode wrapping).
    """
    log.debug("inject_shell_block: install_dir=%s shim=%s", install_dir, inject_path_shim)
    block = render_shell_block(
        install_dir,
        sandbox_sif_path=sandbox_sif_path,
        sandbox_secrets_dir=sandbox_secrets_dir,
        sandbox_logs_dir=sandbox_logs_dir,
    )
    shim_block = render_path_shim_block(install_dir) if inject_path_shim else None

    rc_files = [Path.home() / ".bashrc"]
    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        rc_files.append(Path.home() / ".zshrc")

    if is_dry_run():
        would(
            "shell_rc",
            "inject_block",
            rc_files=rc_files,
            marker=SHELL_MARKERS[0],
            bytes=len(block),
        )
        if shim_block:
            would(
                "shell_rc",
                "inject_path_shim",
                rc_files=rc_files,
                marker=SHELL_MARKERS_PATH_SHIM[0],
                bytes=len(shim_block),
            )
        return rc_files

    modified = []
    for rc in rc_files:
        _write_guarded_block(rc, block)
        if shim_block:
            _write_guarded_block(rc, shim_block, markers=SHELL_MARKERS_PATH_SHIM)
        modified.append(rc)
    return modified


def remove_shell_block() -> list[Path]:
    """Remove both the main and path-shim coding-agents blocks from rc files."""
    candidates = []
    for rc in [Path.home() / ".bashrc", Path.home() / ".zshrc"]:
        if not rc.exists():
            continue
        text = rc.read_text()
        if SHELL_MARKERS[0] in text or SHELL_MARKERS_PATH_SHIM[0] in text:
            candidates.append(rc)

    if is_dry_run():
        would("shell_rc", "remove_block", rc_files=candidates, marker=SHELL_MARKERS[0])
        return candidates

    modified = []
    for rc in candidates:
        content = rc.read_text()
        for markers in (SHELL_MARKERS, SHELL_MARKERS_PATH_SHIM):
            content = _strip_block(content, markers)
        rc.write_text(content)
        modified.append(rc)
    return modified


def _strip_block(content: str, markers: tuple[str, str]) -> str:
    """Remove the marker-guarded block plus the blank-line gap that hugged it.

    Why: ``_write_guarded_block`` injects the block with a leading "\\n\\n"
    separator. Every subsequent re-emit would otherwise accumulate one more
    blank line as those padding newlines are preserved on strip. We collapse
    consecutive blank lines **only at the splice point** (the gap left by
    the removed block) — user-intentional double-blank lines elsewhere in
    the rc file are preserved untouched.
    """
    lines = content.splitlines(keepends=True)
    pre: list[str] = []
    post: list[str] = []
    inside = False
    seen_block = False
    for line in lines:
        if markers[0] in line:
            inside = True
            seen_block = True
            continue
        if markers[1] in line:
            inside = False
            continue
        if inside:
            continue
        (post if seen_block else pre).append(line)

    if not seen_block:
        return content

    # Trim trailing blanks from the pre-side and leading blanks from the
    # post-side. If both halves have content, separate with one blank line;
    # otherwise concatenate without inserting one.
    while pre and pre[-1].strip() == "":
        pre.pop()
    while post and post[0].strip() == "":
        post.pop(0)
    if pre and post:
        return "".join(pre) + "\n" + "".join(post)
    return "".join(pre) + "".join(post)


def _write_guarded_block(
    rc_file: Path,
    block: str,
    markers: tuple[str, str] = SHELL_MARKERS,
) -> None:
    """Write a marker-guarded block, replacing any existing one with the same markers.

    Idempotent on byte identity: trailing blank lines are normalised so a
    second injection does not accumulate extra newlines around the block.
    """
    if rc_file.exists():
        content = rc_file.read_text()
    else:
        content = ""

    if markers[0] in content:
        content = _strip_block(content, markers)

    # Normalise: collapse trailing newlines to exactly one, then add the
    # canonical "blank line + block + newline" suffix. Keeps repeated calls
    # from accumulating empty lines around the block.
    content = content.rstrip("\n")
    if content:
        content += "\n\n" + block + "\n"
    else:
        content = block + "\n"
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
