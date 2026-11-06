#!/usr/bin/env python3
"""PreToolUse hook: the review loop's reviewers and verifiers cannot write.

Acts only for the plugin's read-only agent (agent_type `discipline:review-reader`); every other agent
and the main session pass through untouched. It denies the file-editing tools outright, and Bash
commands that would change the repository: redirections into files, file-changing commands, git
commands that change the working tree, history or refs, package installs, formatters and linters in
fix mode, snapshot updates, and the review-loop commands that write its state.

This is the first line of defence; the workflow's `discipline review touched` check after the
read-only phases is the second. A Bash denylist can't be complete, so the two work together.
The hook must never break other sessions: on any error it allows the call.
"""
from __future__ import annotations

import json
import re
import sys

READ_ONLY_AGENTS = {"discipline:review-reader"}
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

WRITING_BASH = [
    (r"(^|[^<>&0-9])>{1,2}\s*(?!&|/dev/null\b|/dev/stderr\b|/dev/stdout\b)\S", "redirects output into a file"),
    (r"\btee\b", "writes files with tee"),
    (r"(^|[;&|(]\s*|\bsudo\s+|\bxargs\s+)(rm|rmdir|mv|cp|touch|mkdir|chmod|chown|ln|truncate|dd|install|patch|unzip|tar\s+-?x)\b",
     "changes files"),
    (r"\bsed\b[^|;&]*\s-i\b|\bsed\s+-i|\bperl\b[^|;&]*\s-[a-z]*i", "edits files in place"),
    (r"\bgit\s+(add|commit|checkout|switch|restore|reset|stash|clean|rm|mv|apply|am|cherry-pick|rebase|merge|pull|push|fetch|tag|branch\s+-[dDmM]|update-ref|gc|prune|worktree|submodule|config)\b",
     "changes the repository with git"),
    (r"\b(npm|pnpm|yarn|bun)\s+(i|install|add|remove|uninstall|update|upgrade|ci|link)\b|\bpip3?\s+install\b|\buv\s+(add|remove|sync|pip\s+install|lock)\b|\bgo\s+(get|mod\s+(tidy|download|vendor))\b|\bcargo\s+(add|remove|update|install)\b|\bbundle\s+(install|update)\b",
     "installs or changes packages"),
    (r"(--fix\b|--write\b|\s-w\b(?=.*\b(gofmt|goimports|prettier)\b)|\bgofmt\b[^|;&]*\s-w\b|\bruff\s+format\b|\bblack\b(?![^|;&]*--check)|\bprettier\b[^|;&]*--write)",
     "formats or fixes files"),
    (r"(\s-u\b|--update-?snapshots?\b|--updateSnapshot\b|--update-goldens?\b|\s-update\b|--snapshot-update\b)", "updates snapshots or golden files"),
    (r"\bdiscipline\s+(review\s+(plan|record|mark|baseline|answer)|lenses\s+apply|init|decisions\s+(new|index)|work(?!\s+--list))\b",
     "writes the review loop's state or the project's records"),
]


def decide(event: dict) -> dict | None:
    """The hook output for an event, or None to allow."""
    if event.get("agent_type") not in READ_ONLY_AGENTS:
        return None
    tool = event.get("tool_name")
    reason = None
    if tool in EDIT_TOOLS:
        reason = f"{tool} is not available to read-only reviewers"
    elif tool == "Bash":
        command = (event.get("tool_input") or {}).get("command") or ""
        for pattern, what in WRITING_BASH:
            if re.search(pattern, command):
                reason = f"this command {what}; read-only reviewers may only inspect"
                break
    if reason is None:
        return None
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": f"{reason} (discipline review loop). Report what you would change as a finding instead.",
    }}


def main() -> int:
    try:
        out = decide(json.load(sys.stdin))
    except Exception:  # noqa: BLE001  (never break a session because of this hook)
        return 0
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
