#!/usr/bin/env python3
"""Shared SLURM session helper for VSCode extension wrappers.

Invoked by the per-extension stubs (``agent-claude-vscode``,
``agent-codex-vscode``, ``agent-opencode-vscode``, ``agent-pi-vscode``)
that VSCode launches when a user clicks Send in a coding-agent panel.

Flow (see plan §"Proposed Solution"):

    1.  ``CODING_AGENTS_NO_WRAP=1``     → exec npm-installed binary (no SIF).
    2.  ``SLURM_JOB_ID`` already set    → exec ``agent-<n>`` directly.
    3.  cache valid & job alive         → ``srun --jobid=$ID agent-<n>``.
    4.  no cache / dead job             → ``salloc --no-shell``, cache jobid,
                                           ``srun --jobid``.

Failure semantics: one retry on the next spawn ≥30 s after a salloc failure;
permanent refuse afterwards until vscode-reset / Cursor restart / 4 h age-out
(per brainstorm decision 1).

Standalone — only imports stdlib so it works after being copied to
``<install_dir>/bin/agent-vscode``. The exposed entry point is ``main()``.
"""
from __future__ import annotations

import argparse
import datetime
import errno
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

CACHE_SCHEMA_VERSION = 1
CACHE_FILENAME = "vscode-session.json"
SALLOC_RETRY_COOLDOWN_SECONDS = 30
SALLOC_FAILURE_AGE_OUT_SECONDS = 4 * 60 * 60  # 4 hours
DEFAULT_SALLOC_TIME = "08:00:00"
DEFAULT_SALLOC_MEM = "10G"
DEFAULT_SALLOC_CPUS = "2"
DEFAULT_SALLOC_ACCOUNT = "compgen"
JOB_ID_RE = re.compile(r"job allocation (\d+)")

EXIT_SUCCESS = 0
EXIT_NO_AGENT = 2
EXIT_SALLOC_FAILED = 13
EXIT_SRUN_FAILED = 14
EXIT_REFUSE_PERSISTENT_FAILURE = 15

VALID_AGENTS = ("claude", "codex", "opencode", "pi")

# Per-agent env passthrough — every name in this list, if set in the parent
# environment, is forwarded as ``APPTAINERENV_<NAME>`` so it crosses the SIF
# boundary. Names are pre-validated to match the wrapper's
# ^[A-Z][A-Z0-9_]{0,63}$ regex.
ENV_PASSTHROUGH: dict[str, list[str]] = {
    "claude": [
        "CLAUDE_CODE_SSE_PORT", "CLAUDE_CODE_ENTRYPOINT", "CLAUDECODE",
        "CLAUDE_AGENT_SDK_VERSION", "CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING",
        "MCP_CONNECTION_NONBLOCKING", "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL", "ANTHROPIC_CONFIG_DIR",
    ],
    "codex": [
        "CODEX_HOME", "CODEX_INTERNAL_ORIGINATOR_OVERRIDE",
        "RUST_LOG", "DEBUG", "OPENAI_API_KEY", "OPENAI_BASE_URL",
        "CODEX_API_KEY", "CODEX_CA_CERTIFICATE", "CODEX_SQLITE_HOME",
    ],
    "opencode": [
        "OPENCODE_CALLER", "_EXTENSION_OPENCODE_PORT", "OPENCODE_CONFIG",
        "OPENCODE_CONFIG_DIR", "OPENCODE_CONFIG_CONTENT", "OPENCODE_PERMISSION",
        "OPENCODE_DISABLE_PROJECT_CONFIG", "OPENCODE_MODELS_URL",
        "OPENCODE_DISABLE_LSP_DOWNLOAD", "OPENCODE_DB", "OPENCODE_TEST_HOME",
        "OPENCODE_AUTH_CONTENT", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
    ],
    "pi": [
        "PI_VSCODE_BRIDGE_URL", "PI_VSCODE_BRIDGE_TOKEN", "PI_VSCODE_TERMINAL_ID",
        "PI_PACKAGE_DIR", "PI_SMOL_MODEL", "PI_SLOW_MODEL", "PI_PLAN_MODEL",
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
        "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_API_KEY",
    ],
}

# Per-agent additional Apptainer binds appended to the parent's APPTAINER_BIND.
# Each entry is a (host_path, container_path, mode) tuple where mode is "rw" or
# "ro". Host paths starting with "~" are expanded via Path.home(); paths that
# don't exist on the host are silently skipped (the corresponding feature
# degrades but the wrapper still works).
PRE_APPTAINER_BINDS: dict[str, list[tuple[str, str, str]]] = {
    "claude": [
        ("~/.claude", "~/.claude", "rw"),
        ("~/.claude.json", "~/.claude.json", "rw"),
        ("~/.cache", "~/.cache", "ro"),
        ("~/.bun", "~/.bun", "ro"),
        ("~/.npm", "~/.npm", "ro"),
        ("/etc/ssl/certs", "/etc/ssl/certs", "ro"),
        ("/etc/pki", "/etc/pki", "ro"),
        ("/etc/resolv.conf", "/etc/resolv.conf", "ro"),
        ("/etc/hosts", "/etc/hosts", "ro"),
        ("~/.gitconfig", "~/.gitconfig", "ro"),
    ],
    "codex": [
        ("~/.codex", "~/.codex", "rw"),
        ("/tmp", "/tmp", "rw"),
        ("/dev/shm", "/dev/shm", "rw"),
        ("/etc/ssl/certs", "/etc/ssl/certs", "ro"),
        ("/etc/pki", "/etc/pki", "ro"),
        ("/etc/resolv.conf", "/etc/resolv.conf", "ro"),
        ("/etc/hosts", "/etc/hosts", "ro"),
    ],
    "opencode": [
        ("~/.config/opencode", "~/.config/opencode", "rw"),
        ("~/.local/share/opencode", "~/.local/share/opencode", "rw"),
        ("~/.cache/opencode", "~/.cache/opencode", "rw"),
        ("~/.local/state/opencode", "~/.local/state/opencode", "rw"),
        ("~/.opencode", "~/.opencode", "ro"),
        ("/tmp", "/tmp", "rw"),
        ("/etc/ssl/certs", "/etc/ssl/certs", "ro"),
        ("/etc/pki", "/etc/pki", "ro"),
        ("/etc/resolv.conf", "/etc/resolv.conf", "ro"),
        ("/etc/hosts", "/etc/hosts", "ro"),
    ],
    "pi": [
        # Pi-side VSCode extension dir (pi0.pi-vscode-*) is added at install
        # time via a setting under "pi" key — see _expand_pi_extension_binds.
        ("~/.pi", "~/.pi", "rw"),
        ("/etc/ssl/certs", "/etc/ssl/certs", "ro"),
        ("/etc/resolv.conf", "/etc/resolv.conf", "ro"),
        ("/etc/hosts", "/etc/hosts", "ro"),
    ],
}


# --------------------------------------------------------------------------- #
# Cache file management
# --------------------------------------------------------------------------- #

def cache_dir() -> Path:
    """Return the cache directory: ``$XDG_RUNTIME_DIR`` or ``$HOME/.coding-agents``."""
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg:
        return Path(xdg) / "coding-agents"
    return Path.home() / ".coding-agents"


def cache_path() -> Path:
    return cache_dir() / CACHE_FILENAME


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _now_epoch() -> float:
    return time.time()


def _parse_iso(stamp: str) -> float:
    """Parse an ISO timestamp written by ``_now_iso`` back into epoch seconds."""
    if stamp.endswith("Z"):
        stamp = stamp[:-1] + "+00:00"
    return datetime.datetime.fromisoformat(stamp).timestamp()


def read_cache(path: Path) -> dict[str, Any] | None:
    """Return the cached state or ``None`` if absent / unreadable / wrong schema."""
    try:
        raw = path.read_text()
    except (FileNotFoundError, PermissionError):
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("schema_version") != CACHE_SCHEMA_VERSION:
        return None
    return data


def write_cache(path: Path, state: dict[str, Any]) -> None:
    """Atomic write — same pattern as ``utils.secure_write_text`` but stdlib-only."""
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(parent))
    tmp_path = Path(tmp_str)
    try:
        os.fchmod(fd, 0o600)
        payload = json.dumps(state, indent=2, sort_keys=True).encode()
        n = os.write(fd, payload)
        while n < len(payload):
            n += os.write(fd, payload[n:])
        os.fsync(fd)
        os.close(fd)
        os.replace(tmp_path, path)
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


# --------------------------------------------------------------------------- #
# SLURM probing
# --------------------------------------------------------------------------- #

def squeue_job_alive(job_id: int) -> bool:
    """Return True if ``squeue -j <id> -h`` reports the job is still in the queue."""
    try:
        result = subprocess.run(
            ["squeue", "-j", str(job_id), "-h", "-o", "%i"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # No squeue available, or it hung — assume the job is dead so we
        # re-allocate. Better than wedging the spawn.
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def allocate_via_salloc(cursor_pid: int) -> tuple[int | None, str, str]:
    """Run ``salloc --no-shell`` and parse the JOB_ID from stderr.

    Returns ``(job_id, salloc_cmd_str, stderr)``. ``job_id`` is None on
    failure; ``stderr`` carries the error text for the caller to surface.
    """
    user = os.environ.get("USER", "user")
    cmd = [
        "salloc",
        f"--account={DEFAULT_SALLOC_ACCOUNT}",
        f"--time={DEFAULT_SALLOC_TIME}",
        f"--mem={DEFAULT_SALLOC_MEM}",
        f"--cpus-per-task={DEFAULT_SALLOC_CPUS}",
        "--no-shell",
        f"--job-name=cod-ag-vscode-{user}-{cursor_pid}",
    ]
    cmd_str = " ".join(cmd)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return None, cmd_str, f"{type(exc).__name__}: {exc}"
    # ``salloc --no-shell`` writes "salloc: Granted job allocation N" to STDERR
    # (deepen-plan finding 2026-04-27). The exit code may be 0 even on success.
    combined = (result.stderr or "") + (result.stdout or "")
    match = JOB_ID_RE.search(combined)
    if result.returncode != 0 or match is None:
        return None, cmd_str, (result.stderr or result.stdout or f"rc={result.returncode}")
    return int(match.group(1)), cmd_str, ""


# --------------------------------------------------------------------------- #
# Failure-budget logic (decision 1)
# --------------------------------------------------------------------------- #

def should_refuse_persistent_failure(state: dict[str, Any]) -> bool:
    """Implement the bounded-retry rules from brainstorm decision 1.

    State machine:
      * failure_count == 0  → never refuse.
      * failure_count == 1  → refuse if last_failure_at is < 30 s ago
                              (rate-limit) **and** we still have a job_id.
                              Otherwise allow one retry.
      * failure_count >= 2  → refuse unconditionally.
      * 4 h age-out         → reset (caller deletes failure stamp before
                              entering this path).
    """
    last = state.get("last_failure_at")
    count = int(state.get("failure_count", 0) or 0)
    if last is None or count == 0:
        return False
    try:
        last_epoch = _parse_iso(last)
    except ValueError:
        return False
    now = _now_epoch()
    age = now - last_epoch
    if age >= SALLOC_FAILURE_AGE_OUT_SECONDS:
        return False
    if count >= 2:
        return True
    return age < SALLOC_RETRY_COOLDOWN_SECONDS


def reset_failure_counters(state: dict[str, Any]) -> None:
    state["last_failure_at"] = None
    state["failure_count"] = 0


def record_failure(state: dict[str, Any]) -> None:
    state["last_failure_at"] = _now_iso()
    state["failure_count"] = int(state.get("failure_count", 0) or 0) + 1


# --------------------------------------------------------------------------- #
# Bind expansion / env passthrough
# --------------------------------------------------------------------------- #

def _expand_path(p: str) -> str:
    if p.startswith("~/") or p == "~":
        return str(Path.home()) + p[1:]
    return p


def build_apptainer_binds(agent: str, install_dir: Path | None = None) -> list[str]:
    """Build the ``--bind`` strings appended to ``$APPTAINER_BIND``.

    Skips entries whose host path doesn't exist, so a missing ``~/.bun``
    on a fresh user doesn't fail the spawn.
    """
    out: list[str] = []
    for host, target, mode in PRE_APPTAINER_BINDS.get(agent, []):
        host_p = Path(_expand_path(host))
        if not host_p.exists():
            continue
        target_expanded = _expand_path(target)
        out.append(f"{host_p}:{target_expanded}:{mode}")

    if agent == "pi" and install_dir is not None:
        for ext_dir in _discover_pi_vscode_extension_dirs():
            out.append(f"{ext_dir}:{ext_dir}:ro")
    return out


def _discover_pi_vscode_extension_dirs() -> list[Path]:
    """Return existing ``pi0.pi-vscode-*`` extension dirs to bind read-only."""
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
                if child.is_dir() and child.name.startswith("pi0.pi-vscode-"):
                    candidates.append(child)
        except OSError:
            continue
    return candidates


def passthrough_env(agent: str, parent_env: dict[str, str]) -> dict[str, str]:
    """Build ``APPTAINERENV_*`` overlay entries for the given agent."""
    overlay: dict[str, str] = {}
    for name in ENV_PASSTHROUGH.get(agent, []):
        if name in parent_env:
            overlay[f"APPTAINERENV_{name}"] = parent_env[name]
    return overlay


# --------------------------------------------------------------------------- #
# Inner-wrapper exec helpers
# --------------------------------------------------------------------------- #

def install_dir_from_self() -> Path:
    """Resolve ``<install_dir>`` from ``$CODING_AGENT_INSTALL_DIR`` or argv0."""
    env = os.environ.get("CODING_AGENT_INSTALL_DIR")
    if env:
        return Path(env)
    # When invoked as <install_dir>/bin/agent-vscode, parent.parent is install_dir
    return Path(sys.argv[0]).resolve().parent.parent


def exec_inner_wrapper(agent: str, agent_argv: list[str], install_dir: Path) -> None:
    """``exec`` ``<install_dir>/bin/agent-<n>``; never returns on success."""
    target = install_dir / "bin" / f"agent-{agent}"
    os.execv(str(target), [str(target), *agent_argv])


def exec_no_wrap(agent: str, agent_argv: list[str], install_dir: Path) -> None:
    """``exec`` the raw npm-installed binary (escape hatch)."""
    target = install_dir / "node_modules" / ".bin" / agent
    os.execv(str(target), [str(target), *agent_argv])


def srun_inner(
    job_id: int,
    agent: str,
    agent_argv: list[str],
    install_dir: Path,
    *,
    use_pty: bool,
    overlay_env: dict[str, str],
) -> int:
    """Run ``srun --jobid=$ID [--pty] <install_dir>/bin/agent-<n> ARGV``.

    Returns the exit code. We use ``subprocess.run`` rather than ``execv``
    so the helper can update the cache after the inner command exits
    (e.g. to clear failure counters on success).
    """
    cmd = ["srun", f"--jobid={job_id}"]
    if use_pty:
        cmd.append("--pty")
    cmd.append(str(install_dir / "bin" / f"agent-{agent}"))
    cmd.extend(agent_argv)

    env = {**os.environ, **overlay_env}
    try:
        result = subprocess.run(cmd, env=env, check=False)
    except FileNotFoundError as exc:
        sys.stderr.write(f"agent-vscode: srun not on PATH: {exc}\n")
        return EXIT_SRUN_FAILED
    return result.returncode


# --------------------------------------------------------------------------- #
# Main flow
# --------------------------------------------------------------------------- #

def parse_args(argv: list[str]) -> tuple[str, list[str]]:
    parser = argparse.ArgumentParser(
        prog="agent-vscode",
        description="SLURM session helper for VSCode coding-agent extensions.",
    )
    parser.add_argument("--agent", required=True, choices=VALID_AGENTS)
    parser.add_argument("agent_argv", nargs=argparse.REMAINDER,
                        help="argv to forward to agent-<n> (prefix with '--').")
    args = parser.parse_args(argv)
    forwarded = list(args.agent_argv)
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]
    return args.agent, forwarded


def cursor_pid_from_env() -> int:
    """Return the parent PID — used to invalidate cache across Cursor restarts.

    The extension host is the immediate parent of the stub; getppid() points
    at it. If that PID changes between spawns (Cursor restart), the cache is
    stale.
    """
    return os.getppid()


def get_or_allocate_job(state: dict[str, Any], cursor_pid: int) -> tuple[int | None, str | None]:
    """Resolve to a live SLURM job id, allocating if needed.

    Returns ``(job_id, error_message)``. On success ``error_message`` is None.
    Mutates ``state`` in place to persist allocation/failure metadata.
    """
    cached_job = state.get("job_id")
    cached_pid = state.get("cursor_pid")

    if cached_job and cached_pid == cursor_pid and squeue_job_alive(int(cached_job)):
        # Reuse — the cache is good.
        return int(cached_job), None

    # Cache stale — clear job_id so that, if salloc fails, we don't leave a
    # ghost id in the file.
    state["job_id"] = None

    job_id, cmd_str, stderr = allocate_via_salloc(cursor_pid)
    if job_id is None:
        record_failure(state)
        state["salloc_command"] = cmd_str
        return None, stderr or "salloc failed (no job id parsed)"

    reset_failure_counters(state)
    now_iso = _now_iso()
    state["job_id"] = job_id
    state["allocated_at"] = now_iso
    state["expires_at"] = (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(seconds=8 * 3600)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    state["cursor_pid"] = cursor_pid
    state["cursor_session_id"] = os.environ.get("VSCODE_GIT_IPC_HANDLE", "")
    state["salloc_command"] = cmd_str
    return job_id, None


def initial_state(cursor_pid: int) -> dict[str, Any]:
    return {
        "schema_version": CACHE_SCHEMA_VERSION,
        "job_id": None,
        "allocated_at": None,
        "expires_at": None,
        "cursor_pid": cursor_pid,
        "cursor_session_id": os.environ.get("VSCODE_GIT_IPC_HANDLE", ""),
        "last_failure_at": None,
        "failure_count": 0,
        "salloc_command": "",
    }


def run_with_lock(
    agent: str,
    agent_argv: list[str],
    install_dir: Path,
    cursor_pid: int,
) -> int:
    """Acquire the cache flock, then resolve a job and dispatch via srun."""
    cache_p = cache_path()
    cache_p.parent.mkdir(parents=True, exist_ok=True)
    lock_path = cache_p.with_suffix(cache_p.suffix + ".lock")

    # Open the lock file for the whole read-modify-write cycle. fcntl.flock
    # is advisory but every other agent-vscode instance honours it, so it's
    # sufficient for serialising allocation across concurrent spawns.
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)

        existing = read_cache(cache_p)
        # Cursor-restart invalidation: if cached cursor_pid != current ppid,
        # the previous Cursor session is gone — start fresh (drops any
        # poisoned failure counters from a since-restarted Cursor).
        if existing and existing.get("cursor_pid") not in (cursor_pid, None):
            existing = None

        # 4-hour age-out: if the cached failure stamp is older than the
        # window, treat the state as if no failure ever occurred.
        if existing and existing.get("last_failure_at"):
            try:
                age = _now_epoch() - _parse_iso(existing["last_failure_at"])
            except ValueError:
                age = 0
            if age >= SALLOC_FAILURE_AGE_OUT_SECONDS:
                reset_failure_counters(existing)

        state = existing or initial_state(cursor_pid)
        state["schema_version"] = CACHE_SCHEMA_VERSION
        state["cursor_pid"] = cursor_pid

        if should_refuse_persistent_failure(state):
            sys.stderr.write(
                "agent-vscode: refusing to spawn — repeated salloc failures.\n"
                "  Run 'coding-agents vscode-reset' or restart Cursor to clear state.\n"
            )
            write_cache(cache_p, state)
            return EXIT_REFUSE_PERSISTENT_FAILURE

        job_id, error = get_or_allocate_job(state, cursor_pid)
        write_cache(cache_p, state)

        if job_id is None:
            sys.stderr.write(
                f"agent-vscode: salloc failed: {error}\n"
                "  Will retry once on next spawn after a 30 s cooldown.\n"
            )
            return EXIT_SALLOC_FAILED

        overlay = passthrough_env(agent, dict(os.environ))
        binds = build_apptainer_binds(agent, install_dir)
        if binds:
            existing_binds = os.environ.get("APPTAINER_BIND", "")
            joined = ",".join([*([existing_binds] if existing_binds else []), *binds])
            overlay["APPTAINER_BIND"] = joined

        # Hint to the audit log that this invocation came from a VSCode
        # extension flow rather than the terminal wrapper. Wrapper picks
        # this up via a normal env read.
        overlay["APPTAINERENV_CODING_AGENTS_VSCODE_LAUNCHED"] = "1"

        use_pty = os.isatty(0)
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    return srun_inner(
        job_id,
        agent,
        agent_argv,
        install_dir,
        use_pty=use_pty,
        overlay_env=overlay,
    )


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    try:
        agent, agent_argv = parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    install_dir = install_dir_from_self()

    if os.environ.get("CODING_AGENTS_NO_WRAP") == "1":
        try:
            exec_no_wrap(agent, agent_argv, install_dir)
        except FileNotFoundError as exc:
            sys.stderr.write(
                f"agent-vscode: CODING_AGENTS_NO_WRAP=1 set but {exc.filename} missing.\n"
            )
            return EXIT_NO_AGENT
        return EXIT_NO_AGENT  # exec replaced the process; fallthrough is defensive

    if os.environ.get("SLURM_JOB_ID"):
        try:
            exec_inner_wrapper(agent, agent_argv, install_dir)
        except FileNotFoundError as exc:
            sys.stderr.write(f"agent-vscode: inner wrapper missing: {exc.filename}\n")
            return EXIT_NO_AGENT
        return EXIT_NO_AGENT

    cursor_pid = cursor_pid_from_env()
    return run_with_lock(agent, agent_argv, install_dir, cursor_pid)


if __name__ == "__main__":
    sys.exit(main())
