"""doctor command — health checks with color-coded pass/warn/fail."""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

_log = logging.getLogger("coding-agents")

from rich.console import Console
from rich.table import Table

from coding_agents.agents import AGENTS, agents_with_vscode_ext
from coding_agents.config import load_config, get_install_dir

console = Console()


def run_doctor(
    *,
    scan_cron: bool = False,
    scan_systemd: bool = False,
    probe_sif: bool = False,
) -> int:
    """Run all health checks. Returns 0 if all pass, 1 if any fail."""
    config = load_config()
    if not config.get("install_dir"):
        console.print("[red]No installation found. Run `coding-agents install` first.[/red]")
        return 1

    install_dir = get_install_dir(config)
    agents = config.get("agents", [])

    _log.info("run_doctor: install_dir=%s, agents=%s", install_dir, agents)
    table = Table(title="coding-agents doctor", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Check", min_width=40)
    table.add_column("Status", width=6)
    table.add_column("Fix", min_width=30)

    checks = _gather_checks(install_dir, agents, config)
    checks.extend(_gather_vscode_checks(install_dir, config, agents))
    _add_cli_source_drift_check(checks)
    if probe_sif:
        _add_sif_runtime_probes(checks, config)
    if scan_cron:
        from coding_agents.commands.doctor_vscode import scan_crontab
        checks.extend(scan_crontab())
    if scan_systemd:
        from coding_agents.commands.doctor_vscode import scan_systemd_units
        checks.extend(scan_systemd_units())
    has_fail = False

    for i, (name, status, fix) in enumerate(checks, 1):
        if status == "pass":
            icon = "[green]PASS[/green]"
        elif status == "warn":
            icon = "[yellow]WARN[/yellow]"
        else:
            icon = "[red]FAIL[/red]"
            has_fail = True
        table.add_row(str(i), name, icon, fix or "")

    console.print(table)
    return 1 if has_fail else 0


def _gather_checks(
    install_dir: Path, agents: list[str], config: dict
) -> list[tuple[str, str, str]]:
    """Return list of (check_name, status, fix_command)."""
    checks = []

    # 1. Python 3 available
    py = shutil.which("python3")
    checks.append((
        "Python 3 available",
        "pass" if py else "fail",
        "(system dependency)" if not py else "",
    ))

    # 2. Node.js >= 18 — only required at install/update time (npm_install)
    # and for the CODING_AGENTS_NO_WRAP=1 escape hatch. The wrapped sidebar /
    # terminal flow uses the SIF's baked-in node, so a missing host node on
    # a compute or login shell is informational (PASS with note) when the
    # SIF is available, and FAIL only when neither path can run.
    node_ok, node_ver = _check_node()
    if node_ok:
        checks.append((
            f"Node.js >= 18 ({node_ver})",
            "pass",
            "",
        ))
    elif _sif_can_run_node(config):
        checks.append((
            "Node.js >= 18",
            "pass",
            "(host node not required for HPC mode — every agent (claude, "
            "codex, opencode, pi) and host tool (biome, ccstatusline) is "
            "baked into the SIF; only needed for `--local` mode where "
            "there is no SIF to fall back on)",
        ))
    else:
        checks.append((
            "Node.js >= 18",
            "fail",
            "(no host node and no SIF available; activate a node>=18 "
            "conda env, or have the lab admin provision the SIF)",
        ))

    # 3. uv available
    uv = shutil.which("uv")
    checks.append((
        "uv available",
        "pass" if uv else "warn",
        "curl -LsSf https://astral.sh/uv/install.sh | sh" if not uv else "",
    ))

    # 4. Each agent binary
    # For SIF-baked agents (codex/opencode/pi) the wrapper at
    # <install_dir>/bin/agent-<key> + a readable SIF is all we need —
    # the actual binary lives inside the SIF, not on the host. Claude
    # (curl method) keeps the legacy host-symlink check.
    for key in agents:
        agent = AGENTS.get(key)
        if not agent:
            continue

        wrapper_path = install_dir / "bin" / f"agent-{key}"
        sif_ok = _sif_can_run_node(config)  # cheap; reuses the same probe

        if agent.get("method") == "npm":
            # SIF-baked: wrapper + SIF readable = good
            if wrapper_path.exists() and sif_ok:
                ver = "via SIF"
                binary = str(wrapper_path)
            else:
                binary = None
                ver = ""
        else:
            # curl-installed (claude) — check host symlink as before
            binary = shutil.which(agent["binary"])
            if not binary:
                bin_path = install_dir / "bin" / agent["binary"]
                binary = str(bin_path) if bin_path.exists() else None
            ver = ""
            if binary:
                try:
                    result = subprocess.run(
                        agent["version_cmd"], capture_output=True, text=True, timeout=10
                    )
                    ver = result.stdout.strip().split("\n")[0][:40]
                except Exception:
                    ver = "installed"

        checks.append((
            f"{agent['display_name']} ({ver})" if ver else agent['display_name'],
            "pass" if binary else "fail",
            "coding-agents install" if not binary else "",
        ))

    # 5. Config symlinks
    home = Path.home()
    for key in agents:
        agent = AGENTS.get(key)
        if not agent:
            continue
        config_dir = Path(agent["config_dir"]).expanduser()
        instr_file = config_dir / agent["instruction_file"]
        ok = instr_file.is_symlink() or instr_file.exists()
        checks.append((
            f"{agent['display_name']} instruction file",
            "pass" if ok else "warn",
            "coding-agents sync" if not ok else "",
        ))

    # 6. Linting tools
    venv_bin = install_dir / "tools" / ".venv" / "bin"
    for tool in ["ruff", "vulture", "pyright", "yamllint"]:
        path = venv_bin / tool
        checks.append((
            f"Linter: {tool}",
            "pass" if path.exists() else "warn",
            "coding-agents install" if not path.exists() else "",
        ))

    # 7. shellcheck
    sc = install_dir / "tools" / "bin" / "shellcheck"
    checks.append((
        "shellcheck",
        "pass" if sc.exists() else "warn",
        "coding-agents install" if not sc.exists() else "",
    ))

    # 8. Sandbox checks (Apptainer + SIF + secrets/logs dirs) — Phase 2
    _add_sandbox_checks(checks, config)

    # 9. entire status
    if "entire" in config.get("tools", []):
        entire = shutil.which("entire")
        checks.append((
            "entire CLI",
            "pass" if entire else "warn",
            "coding-agents install" if not entire else "",
        ))

    # 10. PATH includes install_dir/bin
    import os
    path_env = os.environ.get("PATH", "")
    bin_in_path = str(install_dir / "bin") in path_env
    checks.append((
        "PATH includes install_dir/bin",
        "pass" if bin_in_path else "warn",
        "source ~/.bashrc" if not bin_in_path else "",
    ))

    # 11. VSCode extensions (cached — call code --list-extensions once)
    if config.get("vscode_extensions") and shutil.which("code"):
        exts = agents_with_vscode_ext(agents)
        installed_exts: set[str] = set()
        try:
            result = subprocess.run(
                ["code", "--list-extensions"],
                capture_output=True, text=True, timeout=15,
            )
            installed_exts = {e.strip().lower() for e in result.stdout.split("\n") if e.strip()}
        except Exception:
            pass
        for agent_key, ext_id in exts:
            installed = ext_id.lower() in installed_exts
            checks.append((
                f"VSCode ext: {ext_id}",
                "pass" if installed else "warn",
                f"code --install-extension {ext_id}" if not installed else "",
            ))

    return checks


def _gather_vscode_checks(
    install_dir: Path, config: dict, agents: list[str]
) -> list[tuple[str, str, str]]:
    """Append the VSCode-extension wrapping checks (Phase 3+5)."""
    from coding_agents.commands.doctor_vscode import (
        codex_version_drift_check,
        no_wrap_acknowledgement,
        opencode_path_shim_check,
    )

    rows: list[tuple[str, str, str]] = []

    sif_str = config.get("sandbox_sif_path", "")
    sif_path = Path(sif_str).expanduser() if sif_str else None

    if "codex" in agents:
        drift = codex_version_drift_check(sif_path)
        if drift is not None:
            rows.append(drift)

    if "opencode" in agents:
        rows.append(opencode_path_shim_check(install_dir))

    if "pi" in agents:
        from coding_agents.commands.doctor_vscode import (
            pi_default_settings_in_sif_check,
        )
        pi_check = pi_default_settings_in_sif_check(sif_path)
        if pi_check is not None:
            rows.append(pi_check)

    ack = no_wrap_acknowledgement()
    if ack is not None:
        rows.append(ack)

    return rows


def _sif_can_run_node(config: dict) -> bool:
    """Best-effort: does the SIF claim to ship its own node?

    Reads the SIF's apptainer-inspect labels (already populated by the
    sandbox-checks pass below) — specifically ``coding-agents.versions.node``.
    We don't actually exec the SIF here (slow, would require an srun
    allocation on this cluster). If apptainer is unavailable on the current
    shell (e.g. login node), we still trust the configured SIF path's
    presence as enough signal — the wrapper flow always runs on a compute
    node, where apptainer + node-in-SIF will be available together.
    """
    sif_str = config.get("sandbox_sif_path", "")
    if not sif_str:
        return False
    sif_path = Path(sif_str).expanduser()
    if not sif_path.exists():
        return False
    apptainer = shutil.which("apptainer")
    if not apptainer:
        # apptainer is compute-only on this cluster; presence of a readable
        # SIF on a login shell is enough — the runtime path will work.
        return True
    try:
        result = subprocess.run(
            [apptainer, "inspect", "--json", str(sif_path)],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return True  # assume yes; soft check, not load-bearing
    try:
        data = json.loads(result.stdout) if result.returncode == 0 else {}
    except json.JSONDecodeError:
        return True
    labels = data.get("data", {}).get("attributes", {}).get("labels", {}) or {}
    return any(k.endswith(".node") for k in labels)


def _check_node() -> tuple[bool, str]:
    """Check if Node.js >= 18 is available."""
    try:
        result = subprocess.run(
            ["node", "--version"], capture_output=True, text=True, timeout=5
        )
        ver = result.stdout.strip()  # e.g., "v18.20.8"
        major = int(ver.lstrip("v").split(".")[0])
        return major >= 18, ver
    except Exception:
        return False, ""


def _add_sandbox_checks(checks: list[tuple[str, str, str]], config: dict) -> None:
    """Append Apptainer + SIF + secrets/logs/creds checks.

    On submit nodes (no $SLURM_JOB_ID), surface an info row prompting the
    user to re-run inside ``srun --pty`` for the full check set. The SIF
    version is read via ``apptainer inspect --json`` (sub-second) rather
    than ``apptainer exec`` (700ms-2s overhead).
    """
    import os

    # Apptainer presence — on this cluster apptainer only lives on compute
    # nodes (not login). Missing-on-login is expected and informational; the
    # real failure is missing-inside-an-srun.
    apptainer = shutil.which("apptainer")
    in_slurm_now = "SLURM_JOB_ID" in os.environ
    if apptainer:
        checks.append(("apptainer on PATH", "pass", ""))
    elif in_slurm_now:
        checks.append((
            "apptainer on PATH",
            "fail",
            "compute node has no apptainer — file a hpcsupport ticket",
        ))
    else:
        checks.append((
            "apptainer on PATH",
            "pass",
            "(only present inside srun/sbatch on this cluster)",
        ))

    # SIF readability
    sif_path = Path(config.get("sandbox_sif_path", "")).expanduser() if config.get("sandbox_sif_path") else None
    if sif_path:
        sif_resolved = sif_path.resolve() if sif_path.exists() else None
        if sif_resolved and sif_resolved.exists():
            checks.append(("sandbox SIF readable", "pass", ""))
            # Try to surface baked versions via `apptainer inspect --json`
            if apptainer:
                try:
                    res = subprocess.run(
                        [apptainer, "inspect", "--json", str(sif_resolved)],
                        capture_output=True, text=True, timeout=5,
                    )
                    import json as _json
                    data = _json.loads(res.stdout) if res.returncode == 0 else {}
                    labels = data.get("data", {}).get("attributes", {}).get("labels", {})
                    versions = {k.split(".")[-1]: v for k, v in labels.items() if k.startswith("coding-agents.versions.")}
                    if versions:
                        checks.append((
                            "SIF baked versions",
                            "pass",
                            ", ".join(f"{k}={v}" for k, v in sorted(versions.items())),
                        ))
                except Exception:
                    pass
        else:
            checks.append((
                "sandbox SIF readable",
                "warn",
                f"not found at {sif_path} (lab admin must build & copy)",
            ))

    # Secrets dir mode 0700
    secrets_str = config.get("sandbox_secrets_dir", "")
    if secrets_str:
        secrets_dir = Path(secrets_str).expanduser()
        if secrets_dir.exists():
            mode = secrets_dir.stat().st_mode & 0o777
            checks.append((
                "agent-secrets dir mode 0700",
                "pass" if mode == 0o700 else "fail",
                f"chmod 700 {secrets_dir}" if mode != 0o700 else "",
            ))
        else:
            checks.append((
                "agent-secrets dir exists",
                "warn",
                f"missing: {secrets_dir} (re-run install)",
            ))

    # Logs dir mode 0700
    logs_str = config.get("sandbox_logs_dir", "")
    if logs_str:
        logs_dir = Path(logs_str).expanduser()
        if logs_dir.exists():
            mode = logs_dir.stat().st_mode & 0o777
            checks.append((
                "agent-logs dir mode 0700",
                "pass" if mode == 0o700 else "fail",
                f"chmod 700 {logs_dir}" if mode != 0o700 else "",
            ))
        else:
            checks.append((
                "agent-logs dir exists",
                "warn",
                f"missing: {logs_dir} (re-run install)",
            ))

    # SLURM context — surface an info-row when run on a submit node
    in_slurm = "SLURM_JOB_ID" in os.environ
    if not in_slurm:
        checks.append((
            "SLURM context",
            "warn",
            "re-run inside `srun --pty` for runtime sandboxing checks",
        ))
    else:
        # Inside a job: verify Claude OAuth credentials mode
        creds = Path.home() / ".claude" / ".credentials.json"
        if creds.exists():
            cmode = creds.stat().st_mode & 0o777
            checks.append((
                "claude credentials mode 0600",
                "pass" if cmode == 0o600 else "warn",
                f"chmod 600 {creds}" if cmode != 0o600 else "",
            ))


# Tools we expect to find baked inside the SIF when --probe-sif is on.
# Order matches the .def file's manifest. node/python check via -- is
# different (no --version flag for some shells); claude/codex/opencode/pi
# all support --version.
_SIF_PROBED_TOOLS: tuple[str, ...] = (
    "claude", "codex", "opencode", "pi",
    "biome", "gitleaks", "node",
)


def _add_cli_source_drift_check(checks: list[tuple[str, str, str]]) -> None:
    """Detect the uv-tool wheel-cache regression: installed cli.py
    bytes != src/coding_agents/cli.py bytes.

    On editable installs (`uv tool install --reinstall .` from the repo,
    or `pip install -e .`) the running file IS the on-disk source, so we
    short-circuit PASS without an md5 compare.

    On released wheels with no repo on disk, the on-disk source path
    doesn't exist; skip the row entirely (no false positives outside the
    dev loop).
    """
    import hashlib
    import inspect

    try:
        import coding_agents.cli as _cli
        running_src = inspect.getsourcefile(_cli)
    except Exception:
        return
    if not running_src:
        return
    running = Path(running_src).resolve()

    # Repo root: this file lives at src/coding_agents/commands/doctor.py;
    # repo root is parents[3].
    here = Path(__file__).resolve()
    project_root = here.parents[3]
    on_disk = project_root / "src" / "coding_agents" / "cli.py"
    if not on_disk.exists():
        # Released wheel install with no co-located source — nothing to
        # compare against, don't add a row.
        return

    src_dir = (project_root / "src").resolve()
    try:
        running_inside_src = running.is_relative_to(src_dir)
    except AttributeError:
        # Python < 3.9 fallback (we're 3.12+ but be defensive).
        running_inside_src = str(running).startswith(str(src_dir) + "/")

    if running_inside_src:
        checks.append((
            "coding-agents CLI matches source",
            "pass",
            "(editable install)",
        ))
        return

    try:
        running_bytes = running.read_bytes()
        on_disk_bytes = on_disk.read_bytes()
    except OSError as exc:
        checks.append((
            "coding-agents CLI matches source",
            "warn",
            f"could not compare: {exc}",
        ))
        return

    if hashlib.md5(running_bytes).digest() == hashlib.md5(on_disk_bytes).digest():
        checks.append((
            "coding-agents CLI matches source",
            "pass",
            "",
        ))
    else:
        checks.append((
            "coding-agents CLI matches source",
            "fail",
            "uv tool install --reinstall .",
        ))


def _add_sif_runtime_probes(
    checks: list[tuple[str, str, str]], config: dict
) -> None:
    """Slow path: actually exec each baked tool inside the SIF.

    The SIF labels (read by row 19 above) are static strings declared
    at build time in coding_agent_hpc.def %labels — they do not reflect
    whether the binary actually landed in /usr/local/bin or elsewhere
    on the SIF's PATH. This probe catches the case where %labels says
    "yes biome" but the %post npm install step silently failed (or
    never ran because the SIF wasn't rebuilt).
    """
    apptainer = shutil.which("apptainer")
    if not apptainer:
        # Probe is a no-op without apptainer; row 17 already surfaces this.
        return
    sif_str = config.get("sandbox_sif_path", "")
    if not sif_str:
        return
    sif_path = Path(sif_str).expanduser()
    if not sif_path.exists():
        return

    for tool in _SIF_PROBED_TOOLS:
        ok, version = _probe_sif_binary(apptainer, sif_path, tool)
        if ok:
            checks.append((
                f"SIF runtime: {tool}",
                "pass",
                version or "",
            ))
        else:
            checks.append((
                f"SIF runtime: {tool}",
                "fail",
                "binary missing — SIF rebuild needed",
            ))


def _probe_sif_binary(
    apptainer: str, sif_path: Path, tool: str
) -> tuple[bool, str]:
    """Run `apptainer exec SIF <tool> --version`. Returns (ok, version)."""
    try:
        result = subprocess.run(
            [
                apptainer, "exec",
                "--containall",
                "--no-mount", "home",
                "--writable-tmpfs",
                str(sif_path), tool, "--version",
            ],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, ""
    out = (result.stdout or "").strip().splitlines()
    err = (result.stderr or "").strip().splitlines()
    # apptainer prints "FATAL: <tool>: executable file not found" on miss.
    if any("executable file not found" in line for line in err):
        return False, ""
    if result.returncode == 0 and out:
        return True, out[0][:40]
    # Some tools print version then exit non-zero (rare); accept any
    # non-empty stdout as evidence the binary ran.
    if out:
        return True, out[0][:40]
    return False, ""
