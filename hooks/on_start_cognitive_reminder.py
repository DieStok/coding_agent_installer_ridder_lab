#!/usr/bin/env python3
"""
SessionStart Hook: Cognitive Offloading Reminder

Displays a brief message reminding the user to use the compound-engineering
workflow and to avoid cognitive offloading.

Non-blocking, informational only.
"""
import json
import sys


def main():
    return {
        "decision": "approve",
        "reason": (
            "🧠 Remember: the thinking is the work.\n"
            "For best results, use: /ce:brainstorm → /ce:plan → /ce:work → /ce:review\n"
            "AI agents augment your understanding — don't let them replace it.\n"
            "→ https://ergosphere.blog/posts/the-machines-are-fine/"
        ),
    }


if __name__ == "__main__":
    import io
    from contextlib import redirect_stdout, redirect_stderr

    captured_out = io.StringIO()
    captured_err = io.StringIO()

    result = None
    try:
        with redirect_stdout(captured_out), redirect_stderr(captured_err):
            result = main()
    except Exception:
        sys.exit(0)

    if result is not None:
        print(json.dumps(result))

    sys.exit(0)
