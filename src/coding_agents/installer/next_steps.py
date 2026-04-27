"""Build the post-install "what to do next" step list.

Single source of truth so the TUI screen and the terminal print-on-exit
render identical content. Each step has:
    * ``action``    optional ``("cmd"|"url", payload)`` — single command or URL
    * ``ext_links`` optional list of (ext_id, agent_key) — renders one row
                    per extension with a clickable "Open in VSCode" link, a
                    "Marketplace" link, and the ``code --install-extension``
                    command on the same row.
    * ``None`` for both → informational only
"""
from __future__ import annotations

from dataclasses import dataclass, field

from coding_agents.agents import AGENTS, agents_with_vscode_ext
from coding_agents.installer.state import InstallerState


@dataclass(frozen=True)
class Step:
    title: str
    body: str
    action: tuple[str, str] | None = None  # ("cmd"|"url", payload)
    ext_links: tuple[tuple[str, str], ...] = ()  # ((agent_key, ext_id), ...)


def _vscode_uri(ext_id: str) -> str:
    return f"vscode:extension/{ext_id}"


def _marketplace_url(ext_id: str) -> str:
    return f"https://marketplace.visualstudio.com/items?itemName={ext_id}"


def build_next_steps(state: InstallerState) -> list[Step]:
    """Return the ordered post-install step list for the given install state."""
    steps: list[Step] = []
    install_dir = state.install_dir or "<install_dir>"
    wrappable = sorted(set(state.agents) & {"claude", "codex", "opencode", "pi"})

    # 1. Source the rc file so PATH + path-shim take effect.
    steps.append(Step(
        title="Source your shell-rc to pick up PATH and the OpenCode path-shim",
        body=(
            "We added an export block (and a second path-shim block, if "
            "OpenCode is installed) to ~/.bashrc / ~/.zshrc. Until you "
            "source it, `coding-agents`, `agent-<name>`, and `opencode` "
            "won't be on your PATH."
        ),
        action=("cmd", "source ~/.bashrc"),
    ))

    # 2. Run sync to symlink instruction files + (re-)emit per-agent configs.
    steps.append(Step(
        title="Run `coding-agents sync` to wire per-agent config files",
        body=(
            "Symlinks AGENTS.md into each agent's config dir, distributes "
            "skills + MCP server configs, and emits Codex hooks + OpenCode "
            "permissions. Idempotent — safe to run any time."
        ),
        action=("cmd", "coding-agents sync"),
    ))

    # 3. Doctor.
    steps.append(Step(
        title="Re-run `coding-agents doctor` to verify everything is green",
        body=(
            "WARN rows for instruction-file symlinks should disappear after "
            "step 2. The `apptainer on PATH` and `SLURM context` rows stay "
            "WARN on a login node — that's expected; they pass once you're "
            "inside an `srun --pty` shell."
        ),
        action=("cmd", "coding-agents doctor"),
    ))

    # 4. VSCode extensions — only relevant when wrappable agents were chosen.
    if wrappable:
        ext_pairs = agents_with_vscode_ext(state.agents)
        if ext_pairs:
            steps.append(Step(
                title="Install the VSCode extensions for your selected agents",
                body=(
                    "Click 'Open in VSCode' to launch the install directly in "
                    "your local VSCode (terminal must register the vscode: "
                    "URL handler — iTerm2, kitty, modern gnome-terminal, "
                    "Windows Terminal, wezterm all do this when VSCode is "
                    "installed). 'Marketplace' opens the web page as a "
                    "fallback. Or copy the `code --install-extension` "
                    "command to install via the CLI."
                ),
                action=None,
                ext_links=tuple((k, ext) for k, ext in ext_pairs),
            ))

    # 5. VSCode wrapper-hooks paste-block (only if Settings Sync hides the file).
    if wrappable:
        steps.append(Step(
            title="Wire the VSCode wrapper hooks (Settings Sync users)",
            body=(
                "If `coding-agents sync` printed a JSONC block under "
                "'VSCode wrapper hooks' (Settings Sync users — settings.json "
                "lives in cloud sync, not on this host), open the Command "
                "Palette and paste it into your user settings. After saving, "
                "the four sidebars route through the SIF wrapper.\n"
                "  Command Palette → 'Preferences: Open User Settings (JSON)'"
            ),
            action=None,
        ))

    # 6. Smoke-test the wrapper inside an srun.
    if state.mode != "local":
        steps.append(Step(
            title="Smoke-test the wrapper inside a SLURM session",
            body=(
                "Allocate a small interactive job and re-run doctor — the "
                "SLURM/Apptainer rows should now be PASS, and you can spawn "
                "an agent end-to-end inside the SIF."
            ),
            action=("cmd",
                    "srun --account=compgen --time=01:00:00 --mem=2G "
                    "--cpus-per-task=2 --pty bash"),
        ))

    # 7. VSCode sidebars — final integration check.
    if wrappable:
        names = ", ".join(AGENTS[k]["display_name"] for k in wrappable)
        steps.append(Step(
            title="Open each sidebar in VSCode and send a test message",
            body=(
                f"For each wrapped agent ({names}), open the sidebar, send a "
                "small message, and confirm a response. Verify wrapping with: "
                "`ps -ef | grep agent-`, `squeue -u $USER`, and "
                "`cat ~/agent-logs/<agent>-$(date -I).jsonl`. If a message "
                "hangs >30s, run `coding-agents vscode-reset` and retry."
            ),
            action=("cmd", "coding-agents vscode-reset"),
        ))

    # 8. Reference docs.
    steps.append(Step(
        title="Reference docs",
        body=(
            "Operator how-to (latency, bypass, reset, cron/systemd "
            "workarounds, extension version pinning):"
        ),
        action=("url", "docs/vscode_integration.md"),
    ))

    return steps


def _osc8(label: str, url: str) -> str:
    """Wrap ``label`` in an OSC-8 hyperlink escape sequence.

    Modern terminals (iTerm2, kitty, gnome-terminal, Windows Terminal,
    wezterm, alacritty) render this as an underlined clickable link. Older
    terminals strip the escape and just show ``label``.
    """
    BEL = "\x07"
    return f"\x1b]8;;{url}{BEL}{label}\x1b]8;;{BEL}"


def render_terminal(steps: list[Step]) -> str:
    """Render the step list as ANSI-styled text for printing on TUI exit.

    Uses OSC-8 hyperlinks for URLs and extension links, ANSI bold for step
    titles, cyan for runnable commands. Plain-text fallback is intact —
    terminals without OSC-8 support just see the labels without underlines.
    """
    lines: list[str] = []
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDER = "\033[4m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    RESET = "\033[0m"

    lines.append(f"\n{BOLD}{GREEN}Next steps{RESET}\n")
    for i, step in enumerate(steps, start=1):
        lines.append(f"{BOLD}{i}. {step.title}{RESET}")
        for body_line in step.body.splitlines():
            lines.append(f"   {body_line}")
        if step.action is not None:
            kind, payload = step.action
            if kind == "cmd":
                lines.append(f"   {CYAN}$ {payload}{RESET}")
            elif kind == "url":
                lines.append(f"   {DIM}→ {_osc8(payload, payload)}{RESET}")
        for agent_key, ext_id in step.ext_links:
            display_name = AGENTS.get(agent_key, {}).get("display_name", agent_key)
            open_link = _osc8("Open in VSCode", _vscode_uri(ext_id))
            mp_link = _osc8("Marketplace", _marketplace_url(ext_id))
            lines.append(
                f"   • {BOLD}{display_name}{RESET} "
                f"({DIM}{ext_id}{RESET})"
            )
            lines.append(
                f"       {UNDER}{open_link}{RESET}   ·   "
                f"{UNDER}{mp_link}{RESET}"
            )
            lines.append(
                f"       {CYAN}$ code --install-extension {ext_id}{RESET}"
            )
        lines.append("")  # blank between steps
    return "\n".join(lines)
