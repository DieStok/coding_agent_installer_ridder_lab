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


def run_doctor() -> int:
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

    # 8. jai status
    jai = shutil.which("jai")
    checks.append((
        "jai sandbox",
        "pass" if jai else "warn",
        "(system admin must install jai)" if not jai else "",
    ))

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
