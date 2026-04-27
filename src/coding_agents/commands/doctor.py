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


def run_doctor(*, scan_cron: bool = False, scan_systemd: bool = False) -> int:
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

    # 2. Node.js >= 18
    node_ok, node_ver = _check_node()
    checks.append((
        f"Node.js >= 18 ({node_ver})" if node_ver else "Node.js >= 18",
        "pass" if node_ok else "fail",
        "(system dependency)" if not node_ok else "",
    ))

    # 3. uv available
    uv = shutil.which("uv")
    checks.append((
        "uv available",
        "pass" if uv else "warn",
        "curl -LsSf https://astral.sh/uv/install.sh | sh" if not uv else "",
    ))

    # 4. Each agent binary
    for key in agents:
        agent = AGENTS.get(key)
        if not agent:
            continue
        binary = shutil.which(agent["binary"])
        if not binary:
            # Check in install dir
            bin_path = install_dir / "node_modules" / ".bin" / agent["binary"]
            if not bin_path.exists():
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

    if "codex" in agents:
        sif_str = config.get("sandbox_sif_path", "")
        sif_path = Path(sif_str).expanduser() if sif_str else None
        drift = codex_version_drift_check(sif_path)
        if drift is not None:
            rows.append(drift)

    if "opencode" in agents:
        rows.append(opencode_path_shim_check(install_dir))

    ack = no_wrap_acknowledgement()
    if ack is not None:
        rows.append(ack)

    return rows


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
