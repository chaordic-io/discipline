#!/usr/bin/env python3
"""Size budgets for the files every session (or every reviewer) reads.

    python3 scripts/review/handover.py      # each budgeted file, its size and its budget

A file over budget is a prompt to trim it, as described in `.agents/WORKING.md` ("Keeping the
handover files small"); nothing here trims or fails. `review.py status` prints the files over budget,
and the gate warns about them. Budgets can be changed per project in scripts/review/units.json:

    "handoverBudgets": {".agents/STATUS.md": {"lines": 200}}

Measures: "lines" counts lines; "entries" counts decision entries (`## YYYY-MM-DD: ...` headings).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

DEFAULTS: dict[str, dict[str, int]] = {
    "CLAUDE.md": {"lines": 200},              # always in context: the most expensive place to grow
    ".agents/STATUS.md": {"lines": 150},      # read first by every session: a snapshot, not a log
    ".agents/HISTORY.md": {"lines": 200},     # sessions read the recent phases; older ones move out
    "docs/DECISIONS.md": {"entries": 100},    # read by reviewers: past this, split by year with an index
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
    for rel, budget in budgets(units).items():
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for kind, limit in budget.items():
            size = measure(text, kind)
            rows.append({"file": rel, "measure": kind, "size": size, "budget": limit, "over": size > limit})
    return rows


def over_budget_lines(root: Path, units: dict) -> list[str]:
    return [f"{r['file']}: {r['size']} {r['measure']} (budget {r['budget']})" for r in report(root, units) if r["over"]]


def main() -> int:
    here = Path(__file__).resolve().parent
    root = here.parents[1]
    units = json.loads((here / "units.json").read_text())
    for r in report(root, units):
        flag = "OVER" if r["over"] else "ok"
        print(f"{flag:4}  {r['file']:22} {r['size']:5} {r['measure']} (budget {r['budget']})")
    if any(r["over"] for r in report(root, units)):
        print("\nTrim as described in .agents/WORKING.md, \"Keeping the handover files small\".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
