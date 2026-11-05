"""Assumptions not yet confirmed: `discipline assumptions`.

When work can't wait for an answer, an agent may go ahead on an assumption, but never silently. In the
spec (or any document under docs/), the assumed text carries a marker:

    Un-voiding is admin-only (assumed 2026-11-05, not confirmed).

The marker is `(assumed <YYYY-MM-DD>` followed by anything up to the closing parenthesis. This command
lists every one, and `discipline check` warns about them, so they stay visible until someone confirms
or rejects them: then the answer becomes a decision in docs/decisions/ and the marker goes.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from . import review

MARKER = re.compile(r"\((?:assumed|Assumed) (\d{4}-\d{2}-\d{2})[^)]*\)")


def find(root: Path | None = None) -> list[tuple[str, int, str, str]]:
    """(file, line, date, the line's text) for every marker in docs/**/*.md, skipping the decision log
    (a decision quoting a marker is history, not an open assumption)."""
    root = root or review.ROOT
    docs = root / "docs"
    out = []
    for path in sorted(docs.rglob("*.md")) if docs.is_dir() else []:
        rel = path.relative_to(root).as_posix()
        if rel.startswith("docs/decisions/") or rel == "docs/DECISIONS.md":
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for m in MARKER.finditer(line):
                out.append((rel, n, m.group(1), line.strip()))
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="discipline assumptions", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.parse_args(argv)
    found = find()
    for rel, n, date, text in found:
        print(f"{rel}:{n}  (since {date})  {text[:140]}")
    print(f"{len(found)} assumptions not confirmed")
    return 0
