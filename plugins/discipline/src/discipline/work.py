"""Per-branch work files: `discipline work [--list]`.

    discipline work          print the current branch's work file (creating it if it doesn't exist yet)
    discipline work --list   every branch in flight, read from each branch's own work file in git
                             (local and remote branches): who, roadmap item, what it owns

Each branch has its own continuation point in `.agents/work/<branch>.md` (a "/" in the branch name
becomes "--"), so people and sessions on different branches never overwrite each other's. What is
shared (the roadmap, shared open questions) stays in `.agents/STATUS.md`. Who works on what is in
each work file's header, so no branch edits a shared file to announce itself (two branches adding a
row to one table conflict on every merge); `discipline work --list` gathers them from git. When a
branch is merged, its work file is folded in: what was done goes to HISTORY.md, what is still open to
STATUS.md, and the file is deleted. `discipline check` warns about work files left on the default
branch after their branch merged.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
from pathlib import Path

from . import review

DIR = review.ROOT / ".agents" / "work"

TEMPLATE = """# Work on `{branch}` (last updated {date})

- **Who:** <!-- the person (and their sessions) working on this branch -->
- **Roadmap item:** <!-- from STATUS.md, with the proposal -->
- **Owns:** <!-- the directories this branch changes; others don't edit them meanwhile -->

<!-- This branch's continuation point and state. The shared roadmap and open questions are in
.agents/STATUS.md; `discipline work --list` shows every branch's header. Update the continuation point after every step. When the
branch is merged: move what was done to HISTORY.md, anything still open to STATUS.md, then delete
this file. Budget: 80 lines. -->

## Continuation point (start here)

<!-- The next concrete step, precise enough that a fresh session can start on it without asking. -->

## Goal of this branch

<!-- The roadmap item(s) from STATUS.md this branch delivers, with the proposal and the user's words. -->

## State

- **Done on this branch:**
- **Uncommitted:**
- **Open questions (this branch only):**

## Assumptions to confirm

<!-- Each assumption this branch works on where nothing written settles the question: the question, the
options, what was assumed (the most conservative), and where it is marked "(assumed <date>, not
confirmed)" in the spec. Removed when the user answers and a decision records it. -->
"""


def _git(*args: str) -> str | None:
    r = subprocess.run(["git", *args], cwd=review.ROOT, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def current_branch() -> str | None:
    """The checked-out branch, or None when detached (as CI often is)."""
    name = _git("rev-parse", "--abbrev-ref", "HEAD")
    return None if not name or name == "HEAD" else name


def default_branch() -> str:
    ref = _git("symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if ref and "/" in ref:
        return ref.split("/", 1)[1]
    for name in ("main", "master"):
        if _git("rev-parse", "--verify", "--quiet", f"refs/heads/{name}") is not None:
            return name
    return "main"


def file_for(branch: str) -> Path:
    return DIR / f"{branch.replace('/', '--')}.md"


def branch_of(path: Path) -> str:
    return path.stem.replace("--", "/")


HEADER_FIELDS = ("Who", "Roadmap item", "Owns")


def header(text: str) -> dict[str, str]:
    out = {}
    for field in HEADER_FIELDS:
        m = re.search(rf"^- \*\*{field}:\*\*\s*(.*)$", text, re.M)
        value = re.sub(r"<!--.*?-->", "", m.group(1)).strip() if m else ""
        out[field] = value or "?"
    return out


def in_flight() -> list[tuple[str, str, dict[str, str]]]:
    """(branch, ref, header) for every local or remote branch whose own tree has its work file."""
    refs = _git("for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes") or ""
    seen, out = set(), []
    for ref in refs.split():
        branch = ref.split("/", 1)[1] if ref.startswith(("origin/", "upstream/")) else ref
        if ref.endswith("/HEAD") or branch in seen:
            continue
        rel = file_for(branch).relative_to(review.ROOT).as_posix()
        text = _git("show", f"{ref}:{rel}")
        if text is not None:
            seen.add(branch)
            out.append((branch, ref, header(text)))
    return out


def leftovers() -> list[str]:
    """On the default branch: work files of other branches (their branch has merged)."""
    branch = current_branch()
    if branch is None or branch != default_branch() or not DIR.is_dir():
        return []
    return sorted(p.name for p in DIR.glob("*.md") if branch_of(p) != branch)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="discipline work", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--list", action="store_true")
    a = p.parse_args(argv)
    if a.list:
        rows = in_flight()
        print("| Branch | Who | Roadmap item | Owns |\n|---|---|---|---|")
        for branch, ref, h in rows:
            print(f"| {branch}{'' if ref == branch else f' ({ref})'} | {h['Who']} | {h['Roadmap item']} | {h['Owns']} |")
        here = sorted(p.name for p in DIR.glob("*.md")) if DIR.is_dir() else []
        orphans = [n for n in here if branch_of(DIR / n) not in {b for b, _, _ in rows}]
        if orphans:
            print(f"\nwork files here whose branch no longer exists: {', '.join(orphans)}")
        return 0
    branch = current_branch()
    if branch is None:
        print("not on a branch (detached HEAD): check out the branch you are working on first")
        return 2
    path = file_for(branch)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(TEMPLATE.format(branch=branch, date=dt.date.today().isoformat()))
        print(f"created {path.relative_to(review.ROOT)}")
    else:
        print(path.relative_to(review.ROOT))
    return 0
