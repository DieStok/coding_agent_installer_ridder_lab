"""Dry-run-aware filesystem helpers.

Thin wrappers around the common ``shutil`` / ``pathlib`` mutations used by
the executor and the command modules. In real runs they do exactly what
they say; in dry-run they log ``[DRY-RUN]`` and return without touching
the filesystem.

Keeping these in one place avoids sprinkling ``if is_dry_run():`` checks
throughout the installer and makes it easy to audit the set of
filesystem mutations the tool can perform.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from coding_agents.dry_run import content_fingerprint, is_dry_run, would


def dry_run_mkdir(
    path: Path,
    *,
    parents: bool = True,
    exist_ok: bool = True,
    mode: int | None = None,
) -> None:
    """``Path.mkdir`` (optionally followed by ``chmod``) with dry-run support."""
    if is_dry_run():
        would(
            "mkdir",
            "create_dir",
            path=path,
            parents=parents,
            exist_ok=exist_ok,
            mode=oct(mode) if mode is not None else None,
        )
        return
    path.mkdir(parents=parents, exist_ok=exist_ok)
    if mode is not None:
        path.chmod(mode)


def dry_run_copy(src: Path, dst: Path) -> None:
    """``shutil.copy2(src, dst)`` with dry-run support."""
    if is_dry_run():
        size = src.stat().st_size if src.exists() else 0
        would("file_copy", "copy2", src=src, dst=dst, bytes=size)
        return
    shutil.copy2(str(src), str(dst))


def dry_run_copytree(src: Path, dst: Path) -> None:
    """``shutil.copytree(src, dst)`` with dry-run support."""
    if is_dry_run():
        entries = sum(1 for _ in src.rglob("*")) if src.exists() else 0
        would("file_copy", "copytree", src=src, dst=dst, entries=entries)
        return
    shutil.copytree(str(src), str(dst))


def dry_run_rmtree(path: Path) -> None:
    """``shutil.rmtree(path)`` with dry-run support."""
    if is_dry_run():
        entries = sum(1 for _ in path.rglob("*")) if path.exists() else 0
        would("file_delete", "rmtree", path=path, entries=entries)
        return
    shutil.rmtree(str(path))


def dry_run_unlink(path: Path) -> None:
    """``Path.unlink`` with dry-run support. Handles symlinks + regular files."""
    if is_dry_run():
        # ``is_symlink`` returns True even for broken symlinks, so it's the
        # right check here. ``exists`` would follow the link.
        is_symlink = path.is_symlink()
        would("file_delete", "unlink", path=path, is_symlink=is_symlink)
        return
    path.unlink()


def dry_run_symlink_to(target: Path, link_to: str | Path) -> None:
    """``Path.symlink_to(link_to)`` with dry-run support.

    Unlike :func:`coding_agents.utils.safe_symlink`, this is a direct
    wrapper for relative symlinks created in project_init.
    """
    if is_dry_run():
        would(
            "symlink",
            "symlink_to",
            target=target,
            link_to=str(link_to),
            replaces_existing=target.exists() or target.is_symlink(),
        )
        return
    target.symlink_to(link_to)


def dry_run_append_text(path: Path, content: str) -> None:
    """Append text to a file with dry-run support."""
    if is_dry_run():
        would(
            "file_write",
            "append_text",
            path=path,
            bytes=len(content),
            sha8=content_fingerprint(content),
        )
        return
    with open(path, "a") as f:
        f.write(content)


def dry_run_write_text(path: Path, content: str, *, mode: int | None = None) -> None:
    """``Path.write_text`` (optionally followed by ``chmod``) with dry-run support."""
    if is_dry_run():
        would(
            "file_write",
            "write_text",
            path=path,
            bytes=len(content),
            sha8=content_fingerprint(content),
            mode=oct(mode) if mode is not None else None,
        )
        return
    path.write_text(content)
    if mode is not None:
        path.chmod(mode)
