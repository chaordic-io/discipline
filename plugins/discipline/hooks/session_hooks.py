#!/usr/bin/env python3
"""SessionStart and Stop hooks: a crashed or new session resumes where the last one stopped.

- SessionStart (startup, resume, clear, compact): adds this branch's continuation point, the step that
  was in progress, and the changes newer than the work file to the session's context.
- Stop: when files changed after this branch's work file was last written, asks the agent once to
  bring it up to date before stopping (a second stop in a row always goes through).

Both act only in a repository set up with discipline (`.agents/profile.json` exists) and on a branch.
Set DISCIPLINE_STOP_CHECK=0 to turn the stop check off. A hook must never break a session: on any
error it does nothing.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def respond(event: dict) -> dict | None:
    if event.get("cwd"):
        os.chdir(event["cwd"])
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from discipline import work  # noqa: PLC0415  (after chdir: the package finds the repository from it)

    name = event.get("hook_event_name")
    if name == "SessionStart":
        context = work.session_context()
        if context:
            return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
    elif name == "Stop":
        if event.get("stop_hook_active") or os.environ.get("DISCIPLINE_STOP_CHECK") == "0":
            return None
        reason = work.stop_reason()
        if reason:
            return {"decision": "block", "reason": reason}
    return None


def main() -> int:
    try:
        out = respond(json.load(sys.stdin))
    except Exception:  # noqa: BLE001  (never break a session because of this hook)
        return 0
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
