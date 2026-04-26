"""InstallObserver — small adapter the executor talks to instead of a bare
RichLog. Exposes the same .write() method (so existing log.write() calls
still work) plus phase tracking and a verbose sink for subprocess output.

The observer also registers itself as a module-level "verbose sink" that
utils.run() checks after each subprocess completes. This lets us stream
stdout/stderr into the verbose pane without plumbing the observer through
every helper function.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from textual.widgets import ProgressBar, RichLog


class InstallObserver:
    """Wraps the install-log RichLog with progress + verbose-pane hooks.

    Duck-typed to RichLog: anywhere the executor used to write to a RichLog
    via `log.write(...)`, it can now write to the observer the same way.
    """

    def __init__(
        self,
        log: "RichLog",
        verbose: "RichLog | None" = None,
        progress: "ProgressBar | None" = None,
        total_phases: int = 0,
    ) -> None:
        self._log = log
        self._verbose = verbose
        self._progress = progress
        self._total = total_phases
        self._completed = 0

    # ---- pass-through to the main install log ----
    def write(self, text: Any) -> None:
        self._log.write(text)

    # ---- phase tracking ----
    def set_total_phases(self, n: int) -> None:
        self._total = n
        self._completed = 0
        if self._progress is not None:
            self._progress.update(total=n, progress=0)

    def start_phase(self, label: str) -> None:
        """Mark the start of a top-level installer phase."""
        self._completed += 1
        self._log.write(f"\n[bold]{label}[/bold]")
        if self._progress is not None:
            current = min(self._completed, self._total)
            self._progress.update(progress=current - 1)

    def finish_phase(self) -> None:
        """Tick the progress bar after a phase block completes."""
        if self._progress is not None:
            self._progress.update(progress=min(self._completed, self._total))

    # ---- verbose pane (subprocess output, etc.) ----
    def verbose(self, text: str) -> None:
        if self._verbose is None:
            return
        for line in text.rstrip("\n").splitlines():
            self._verbose.write(line)


# Module-level sink so utils.run() can stream subprocess output to the
# verbose pane without taking the observer as an argument.
_verbose_sink: Callable[[str], None] | None = None


def set_verbose_sink(sink: Callable[[str], None] | None) -> None:
    """Register (or clear) the global subprocess-output sink."""
    global _verbose_sink
    _verbose_sink = sink


def emit_verbose(text: str) -> None:
    """utils.run() calls this after each subprocess completes."""
    if _verbose_sink is not None and text:
        try:
            _verbose_sink(text)
        except Exception:
            pass  # never let a UI bug break an install
