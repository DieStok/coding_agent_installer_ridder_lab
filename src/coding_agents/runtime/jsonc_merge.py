"""JSONC-tolerant deep-merge for VSCode settings.json.

VSCode's settings.json is JSONC (JSON with comments + trailing commas). The
``json5`` library tolerates both. We deep-merge the user's existing keys with
ours, then write atomically so a concurrent VSCode write can never see a
half-emitted file.

Atomic-write semantics mirror ``utils.secure_write_text`` (Sprint 1 Task 1.2):
``mkstemp`` in same dir + ``fsync`` + ``os.replace`` + parent fsync. A ``.bak``
of the prior content is left next to the target so a manual fix is one
``mv`` away if our merge ever produces something the user dislikes.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def _deep_merge(existing: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Recursive merge: nested dicts merge key-by-key; lists/scalars overwrite."""
    out = dict(existing)
    for key, value in new.items():
        if (
            key in out
            and isinstance(out[key], dict)
            and isinstance(value, dict)
        ):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _load_jsonc(path: Path) -> dict[str, Any]:
    """Parse JSONC; raise on hard syntax error so caller can decide."""
    text = path.read_text()
    if not text.strip():
        return {}
    try:
        import json5  # type: ignore[import-not-found]
    except ImportError:
        # Fallback: treat as plain JSON. Strip line comments + trailing commas
        # cheaply enough that vanilla settings.json parses; users with exotic
        # JSONC will get a clear error message.
        return _parse_plain_json_fallback(text)

    parsed = json5.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected object at top of {path}, got {type(parsed).__name__}")
    return parsed


def _parse_plain_json_fallback(text: str) -> dict[str, Any]:
    """Best-effort JSONC handling without json5 — strip // line comments."""
    cleaned_lines = []
    for line in text.splitlines():
        # Drop everything after an unquoted "//". This is the cheap path; users
        # with /* block comments */ should install json5.
        in_string = False
        escape = False
        cut = len(line)
        for i, ch in enumerate(line):
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if not in_string and ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                cut = i
                break
        cleaned_lines.append(line[:cut])
    cleaned = "\n".join(cleaned_lines)
    # json.loads cannot handle trailing commas in {}/[] — strip them via
    # a tolerant pass.
    import re
    cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
    parsed = json.loads(cleaned) if cleaned.strip() else {}
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object, got {type(parsed).__name__}")
    return parsed


def _atomic_write(path: Path, content: str) -> None:
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(parent))
    tmp_path = Path(tmp_str)
    try:
        os.fchmod(fd, 0o600)
        payload = content.encode()
        n = os.write(fd, payload)
        while n < len(payload):
            n += os.write(fd, payload[n:])
        os.fsync(fd)
        os.close(fd)
        os.replace(tmp_path, path)
        try:
            dir_fd = os.open(str(parent), os.O_DIRECTORY)
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def deep_merge_jsonc_settings(
    target_path: Path,
    new_keys: dict[str, Any],
    *,
    backup: bool = True,
) -> Path:
    """Merge ``new_keys`` into the JSONC file at ``target_path`` atomically.

    Returns ``target_path`` for chaining. If the target exists, its prior
    content is copied to ``<target>.bak`` before the new file is written
    (when ``backup=True``). Lists overwrite — agents own their own keys
    and the user can re-add list entries by hand if they want a different
    set.
    """
    if target_path.exists():
        existing = _load_jsonc(target_path)
        if backup:
            bak = target_path.with_name(target_path.name + ".bak")
            bak.write_text(target_path.read_text())
    else:
        existing = {}

    merged = _deep_merge(existing, new_keys)
    rendered = json.dumps(merged, indent=2, sort_keys=True) + "\n"
    _atomic_write(target_path, rendered)
    return target_path
