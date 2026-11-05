"""The `discipline` command.

    discipline init [DIR]             set a repository up from the templates (never overwrites)
    discipline check                  the gate checks (problems fail, warnings don't)
    discipline review <command>       review-loop bookkeeping: plan, show, checklist, diff, touched,
                                      record, mark, status, open, questions, answer, quota
    discipline lenses <show|apply|check>
                                      the review lenses the project profile selects
    discipline spec-rules             spec rules and the tests that pin them
    discipline ai-evals               prompts and their eval sets
    discipline handover               size budgets of the files every session reads
    discipline doc <name>             a guide: engineering, working, stack, bootstrap, upgrade
    discipline work [--list]          this branch's work file (its continuation point)
    discipline decisions new|index|check|search
                                      the decision log: one file per decision, its index, and search
    discipline assumptions            assumptions in the docs not yet confirmed
    discipline --version

All commands act on the git repository around the current directory.
"""
from __future__ import annotations

import sys

from . import __version__

COMMANDS = {
    "init": ("init", "main"),
    "check": ("check", "main"),
    "doc": ("doc", "main"),
    "work": ("work", "main"),
    "decisions": ("decisions", "main"),
    "assumptions": ("assumptions", "main"),
    "review": ("review", "main"),
    "lenses": ("lenses", "main"),
    "spec-rules": ("spec_rules", "main"),
    "ai-evals": ("ai_evals", "main"),
    "handover": ("handover", "main"),
}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    if args[0] in ("-V", "--version", "version"):
        print(f"discipline {__version__}")
        return 0
    if args[0] not in COMMANDS:
        print(f"unknown command {args[0]!r}\n\n{__doc__.strip()}", file=sys.stderr)
        return 2
    module_name, func = COMMANDS[args[0]]
    module = __import__(f"discipline.{module_name}", fromlist=[func])
    rc = getattr(module, func)(args[1:])
    return 0 if rc is None else int(rc)
