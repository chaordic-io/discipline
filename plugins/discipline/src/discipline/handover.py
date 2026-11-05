#!/usr/bin/env python3
"""Size budgets for the files every session (or every reviewer) reads.

    discipline handover      # each budgeted file, its size and its budget

A file over budget is a prompt to trim it, as described in /discipline:working ("Keeping the
handover files small"); nothing here trims or fails. `review.py status` prints the files over budget,
and the gate warns about them. Budgets can be changed per project in .claude/review/units.json:

    "handoverBudgets": {".agents/STATUS.md": {"lines": 200}}

Measures: "lines" counts lines; "entries" counts `## YYYY-MM-DD: ...` headings. A pattern with `*`
(".agents/work/*.md") budgets every matching file.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

DEFAULTS: dict[str, dict[str, int]] = {
    "CLAUDE.md": {"lines": 200},              # always in context: the most expensive place to grow
    ".agents/STATUS.md": {"lines": 150},      # read first by every session: the shared snapshot
    ".agents/work/*.md": {"lines": 80},       # each branch's continuation point: a snapshot, not a log
    ".agents/HISTORY.md": {"lines": 200},     # sessions read the recent phases; older ones move out
}

DECISION = re.compile(r"^## \d{4}-\d{2}-\d{2}\b", re.M)


def budgets(units: dict) -> dict[str, dict[str, int]]:
    return {**DEFAULTS, **(units.get("handoverBudgets") or {})}


def measure(text: str, kind: str) -> int:
    if kind == "entries":
        return len(DECISION.findall(text))
    return len(text.splitlines())


def report(root: Path, units: dict) -> list[dict]:
    """One row per budgeted file that exists: {file, measure, size, budget, over}."""
    rows = []
    for pattern, budget in budgets(units).items():
        paths = sorted(root.glob(pattern)) if "*" in pattern else [root / pattern]
        for path in paths:
            if not path.exists():
                continue
            rel = path.relative_to(root).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            for kind, limit in budget.items():
                size = measure(text, kind)
                rows.append({"file": rel, "measure": kind, "size": size, "budget": limit, "over": size > limit})
    return rows


def over_budget_lines(root: Path, units: dict) -> list[str]:
    return [f"{r['file']}: {r['size']} {r['measure']} (budget {r['budget']})" for r in report(root, units) if r["over"]]


def main(argv: list[str] | None = None) -> int:  # noqa: ARG001  (no options)
    from . import review  # noqa: PLC0415  (review imports this module lazily too)
    root, units = review.ROOT, review.UNITS
    for r in report(root, units):
        flag = "OVER" if r["over"] else "ok"
        print(f"{flag:4}  {r['file']:22} {r['size']:5} {r['measure']} (budget {r['budget']})")
    if any(r["over"] for r in report(root, units)):
        print("\nTrim as described in /discipline:working, \"Keeping the handover files small\".")
    return 0

