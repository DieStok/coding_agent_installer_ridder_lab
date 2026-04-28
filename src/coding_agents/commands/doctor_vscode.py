"""VSCode-extension-related doctor checks.

Kept in a separate module so the bulky scan logic (cron, systemd) and the
Codex protocol-drift detector don't bloat ``commands/doctor.py``. Each public
function returns the same ``(name, status, fix)`` tuple shape that
``_gather_checks`` consumes.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path

log = logging.getLogger("coding-agents")

CheckRow = tuple[str, str, str]

# Bare CLI names we warn about when they appear unprefixed in cron / systemd.
_BARE_AGENT_NAMES = ("claude", "codex", "opencode", "pi")
_BARE_NAME_RE = re.compile(
    r"(?<![/\w-])(" + "|".join(_BARE_AGENT_NAMES) + r")(?![\w-])"
)


# --------------------------------------------------------------------------- #
# Codex extension/SIF version drift (decision 5)
# --------------------------------------------------------------------------- #

def _read_codex_extension_version() -> str | None:
    """Return ``maj.min`` for the bundled Codex extension binary, or None."""
    candidates: list[Path] = []
    for server in (
        Path.home() / ".vscode-server" / "extensions",
        Path.home() / ".cursor-server" / "extensions",
        Path.home() / ".vscode-server-insiders" / "extensions",
    ):
        if not server.is_dir():
            continue
        try:
            for child in server.iterdir():
                if child.is_dir() and child.name.startswith("openai.chatgpt-"):
                    candidates.append(child)
        except OSError:
            continue
    if not candidates:
        return None
    # Prefer the highest semver-ish dir (sorted lexically is good enough).
    chosen = sorted(candidates)[-1]
    bin_path = chosen / "bin" / "linux-x86_64" / "codex"
    if not bin_path.exists():
        return None
    try:
        result = subprocess.run(
            [str(bin_path), "--version"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return _normalize_version(result.stdout)


def _read_codex_sif_version(sif_path: Path) -> str | None:
    """Return ``maj.min`` for the SIF-pinned codex, or None."""
    if not sif_path.exists():
        return None
    apptainer = "apptainer"
    try:
        result = subprocess.run(
            [apptainer, "exec", str(sif_path), "codex", "--version"],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return _normalize_version(result.stdout)


def _normalize_version(raw: str) -> str | None:
    """Return ``maj.min`` from an arbitrary ``--version`` line."""
    m = re.search(r"(\d+)\.(\d+)", raw or "")
    if not m:
        return None
    return f"{m.group(1)}.{m.group(2)}"


def codex_version_drift_check(sif_path: Path | None) -> CheckRow | None:
    """Compare extension-bundled vs SIF-pinned codex versions.

    Returns ``None`` if either version is unreadable (the user gets nothing
    rather than a noisy unknown). Otherwise warns on major.minor mismatch.
    """
    ext = _read_codex_extension_version()
    sif = _read_codex_sif_version(sif_path) if sif_path else None
    if ext is None or sif is None:
        return None
    if ext == sif:
        return ("Codex extension/SIF version", "pass", f"{ext} matches")
    return (
        "Codex extension/SIF version",
        "warn",
        (
            f"extension {ext} vs SIF {sif} — pin the ChatGPT extension or "
            "rebuild the SIF if the chat panel breaks"
        ),
    )


# --------------------------------------------------------------------------- #
# Cron / systemd scans
# --------------------------------------------------------------------------- #

def scan_crontab() -> list[CheckRow]:
    """Run ``crontab -l`` and warn on lines that invoke bare CLI names."""
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []  # no crontab is the normal case
    rows: list[CheckRow] = []
    for lineno, line in enumerate(result.stdout.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _BARE_NAME_RE.search(stripped)
        if not match:
            continue
        agent = match.group(1)
        rows.append((
            f"crontab line {lineno} invokes bare {agent}",
            "warn",
            f"replace with $CODING_AGENT_INSTALL_DIR/bin/agent-{agent} or sbatch --wrap",
        ))
    return rows


def scan_systemd_units() -> list[CheckRow]:
    """Scan user systemd unit ``ExecStart=`` lines for bare CLI names."""
    try:
        listing = subprocess.run(
            ["systemctl", "--user", "list-unit-files", "--type=service",
             "--no-legend", "--plain"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if listing.returncode != 0:
        return []
    rows: list[CheckRow] = []
    for line in listing.stdout.splitlines():
        unit = line.split()[0] if line.split() else ""
        if not unit or not unit.endswith(".service"):
            continue
        try:
            cat = subprocess.run(
                ["systemctl", "--user", "cat", unit],
                capture_output=True, text=True, timeout=10, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        for line2 in cat.stdout.splitlines():
            if not line2.startswith("ExecStart="):
                continue
            value = line2[len("ExecStart="):]
            match = _BARE_NAME_RE.search(value)
            if not match:
                continue
            agent = match.group(1)
            rows.append((
                f"systemd unit {unit} invokes bare {agent}",
                "warn",
                f"point ExecStart at $CODING_AGENT_INSTALL_DIR/bin/agent-{agent}",
            ))
    return rows


# --------------------------------------------------------------------------- #
# OpenCode path-shim placement check (Phase 4 wires this in)
# --------------------------------------------------------------------------- #

def opencode_path_shim_check(install_dir: Path) -> CheckRow:
    """Verify ``which opencode`` resolves to our shim, not the npm bin."""
    expected = install_dir / "bin" / "path-shim" / "opencode"
    try:
        result = subprocess.run(
            ["which", "opencode"], capture_output=True, text=True,
            timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ("OpenCode path-shim resolves first", "warn", "could not run `which`")
    resolved = result.stdout.strip()
    if not resolved:
        return ("OpenCode path-shim resolves first", "warn",
                "opencode not on PATH — connect VSCode then re-source ~/.bashrc")
    if Path(resolved) == expected:
        return ("OpenCode path-shim resolves first", "pass", str(expected))
    return (
        "OpenCode path-shim resolves first",
        "warn",
        f"resolved {resolved} — expected {expected}; source ~/.bashrc",
    )


# --------------------------------------------------------------------------- #
# VSCode-fallback Python ≥ 3.7 probe
# --------------------------------------------------------------------------- #

# The PATH VSCode falls back to when its `/bin/bash -lic 'printf $PATH'`
# probe times out (>10s). Verbatim from the failure log on this cluster;
# this is the closest approximation to "what the extension's spawn env
# looks like in the worst case".
_VSCODE_FALLBACK_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# Search order mirrors the per-extension stub in wrapper_vscode.py — a
# pass here means the stub's probe will succeed too.
_PYTHON_CANDIDATES = (
    "python3.13", "python3.12", "python3.11", "python3.10",
    "python3.9", "python3.8", "python3.7", "python3",
)


def vscode_python_version_check() -> CheckRow:
    """Verify a Python ≥ 3.7 is reachable on the bare PATH VSCode falls back
    to when the login-shell PATH probe times out.

    Mirrors the per-extension stub's probe so a pass here implies the stub
    will also resolve a working Python at spawn time. Catches the
    ``SyntaxError: future feature annotations is not defined`` failure mode
    where ``/usr/bin/python3`` is ≤ 3.6 and the extension can't reach a
    newer Python because ~/.bashrc was too slow to source.
    """
    env = {"PATH": _VSCODE_FALLBACK_PATH}
    for cand in _PYTHON_CANDIDATES:
        try:
            ok = subprocess.run(
                [cand, "-c",
                 "import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)"],
                capture_output=True, env=env, timeout=5, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if ok.returncode != 0:
            continue
        try:
            ver = subprocess.run(
                [cand, "-c",
                 "import sys; print('.'.join(map(str, sys.version_info[:3])))"],
                capture_output=True, env=env, text=True, timeout=5, check=False,
            )
            version = ver.stdout.strip() or "unknown"
        except (OSError, subprocess.TimeoutExpired):
            version = "unknown"
        return (
            "VSCode-fallback Python >= 3.7",
            "pass",
            f"{cand} ({version}) on bare PATH",
        )

    return (
        "VSCode-fallback Python >= 3.7",
        "warn",
        "no python>=3.7 on bare PATH (/usr/local/bin:/usr/bin:...) — "
        "VSCode extensions will fail to spawn agent-vscode whenever the "
        "login-shell PATH probe times out. Fix: install a system "
        "python>=3.7, or set terminal.integrated.env.linux.PATH in VSCode "
        "user settings, or speed up ~/.bashrc.",
    )


# --------------------------------------------------------------------------- #
# Escape-hatch acknowledgement
# --------------------------------------------------------------------------- #

def no_wrap_acknowledgement() -> CheckRow | None:
    if os.environ.get("CODING_AGENTS_NO_WRAP") == "1":
        return (
            "CODING_AGENTS_NO_WRAP set",
            "warn",
            "wrapper bypassed (still inside SIF — see docs/vscode_integration.md)",
        )
    return None


# --------------------------------------------------------------------------- #
# Pi default-settings reachable in the SIF (no-wrap-via-sif plan, phase 2b)
# --------------------------------------------------------------------------- #

def pi_default_settings_in_sif_check(sif_path: Path | None) -> CheckRow | None:
    """Verify the SIF carries /opt/pi-default-settings.json.

    The wrapper template's first-run hook (Phase 2b) copies this file into
    each user's ~/.pi/agent/settings.json on their first Pi invocation. If
    the lab admin forgot to bake the file into the SIF, fresh users will
    open Pi with no extensions wired up — agent works but lab defaults
    are missing.

    Returns ``None`` when no SIF is configured or apptainer is unavailable
    (login-node case — soft check, not load-bearing).
    """
    if sif_path is None or not sif_path.exists():
        return None
    apptainer = "apptainer"
    try:
        result = subprocess.run(
            [apptainer, "exec", str(sif_path),
             "test", "-r", "/opt/pi-default-settings.json"],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None  # apptainer missing or hung — defer to other rows
    if result.returncode == 0:
        return ("Pi defaults baked in SIF", "pass", "/opt/pi-default-settings.json")
    return (
        "Pi defaults baked in SIF",
        "warn",
        "/opt/pi-default-settings.json missing — fresh users get empty Pi (lab admin: rebuild SIF with `pi install npm:pi-ask-user` etc.)",
    )
