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

Resuming after a crash: the plugin's session-start hook puts this branch's continuation point, the
step that was in progress (the work file's "In progress" section, written before a step starts and
cleared when it is done) and any changes newer than the work file into every new session. Its stop
hook asks the agent, once, to bring the work file up to date when files changed after it was last
written. `discipline work` and `discipline check` warn about such a stale work file too.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import time
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

## In progress

<!-- The step being worked on now and the files it touches: written before the step starts, set back to
"nothing" when it is done. A session that finds a step here knows the last one stopped in the middle
of it, and checks those files for half-done edits before going on. -->
- nothing

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


def _git(*args: str, strip: bool = True) -> str | None:
    r = subprocess.run(["git", *args], cwd=review.ROOT, capture_output=True, text=True)
    return (r.stdout.strip() if strip else r.stdout) if r.returncode == 0 else None


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


def section(text: str, heading: str) -> str:
    """The text under `## <heading>` (up to the next `## `), without HTML comments."""
    m = re.search(rf"^## {re.escape(heading)}[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return re.sub(r"<!--.*?-->", "", m.group(1), flags=re.S).strip() if m else ""


def in_progress(text: str) -> str:
    """The step a session was in the middle of, or "" when none was."""
    value = section(text, "In progress")
    return "" if value.lstrip("- ").strip().lower() in ("", "nothing", "none") else value


# Changes to these don't make a work file stale: they are the handover itself and the review state.
NOT_WORK = (".agents/work/", ".claude/review/")


def changed_since(path: Path) -> list[str]:
    """Uncommitted files changed after the work file at `path` was last written (newest first)."""
    if not path.exists():
        return []
    since = path.stat().st_mtime + 1
    out = []
    for line in (_git("status", "--porcelain", "--untracked-files=all", strip=False) or "").splitlines():
        rel = line[3:].split(" -> ")[-1].strip('"')
        if rel.startswith(NOT_WORK):
            continue
        try:
            mtime = (review.ROOT / rel).stat().st_mtime
        except OSError:
            continue  # deleted
        if mtime > since:
            out.append((mtime, rel))
    return [rel for _, rel in sorted(out, reverse=True)]


def _age(path: Path) -> str:
    minutes = int((time.time() - path.stat().st_mtime) / 60)
    if minutes < 60:
        return f"{minutes} min ago"
    return f"{minutes // 60} h ago" if minutes < 48 * 60 else f"{minutes // 1440} days ago"


def is_set_up() -> bool:
    return (review.ROOT / ".agents" / "profile.json").exists()


def session_context() -> str | None:
    """What a new session needs to resume this branch's work, or None outside a set-up repository."""
    if not is_set_up():
        return None
    branch = current_branch()
    if branch is None:
        return None
    path = file_for(branch)
    rel = path.relative_to(review.ROOT).as_posix()
    if not path.exists():
        return (f"discipline: branch `{branch}` has no work file yet. When you start working here, run "
                f"`discipline work` to create {rel} and keep its continuation point current (.agents/README.md).")
    text = path.read_text(encoding="utf-8")
    lines = [f"discipline: resuming branch `{branch}`. Its work file is {rel}, last updated {_age(path)}. "
             "Read .agents/README.md for the rest of the handover."]
    point = section(text, "Continuation point")
    lines.append("Continuation point: " + (point if point else "(empty: ask the user what to work on, then write it)"))
    step = in_progress(text)
    if step:
        lines.append("In progress when the last session stopped (it stopped in the middle of this step): " + step
                     + "\nBefore going on, check the files it names for half-done edits, finish or undo them, "
                       "then update the work file.")
    newer = changed_since(path)
    if newer:
        shown = ", ".join(newer[:10]) + (f" and {len(newer) - 10} more" if len(newer) > 10 else "")
        lines.append(f"{len(newer)} uncommitted files changed after the work file was last updated ({shown}): "
                     "the continuation point may be behind them. Compare before relying on it.")
    return "\n\n".join(lines)


def stop_reason() -> str | None:
    """Why a session should update its work file before stopping, or None."""
    if not is_set_up():
        return None
    branch = current_branch()
    if branch is None:
        return None
    path = file_for(branch)
    rel = path.relative_to(review.ROOT).as_posix()
    if not path.exists():
        changed = [l for l in (_git("status", "--porcelain", strip=False) or "").splitlines() if not l[3:].startswith(NOT_WORK)]
        if not changed:
            return None
        return (f"Before stopping: files changed on branch `{branch}`, which has no work file. Run `discipline work` "
                f"to create {rel}, fill in its header and continuation point, so a new session can resume. "
                "If this was not work to resume (a question, an experiment), say so and stop.")
    newer = changed_since(path)
    if not newer:
        return None
    return (f"Before stopping: {len(newer)} files changed after {rel} was last updated ({', '.join(newer[:5])}"
            + ("…" if len(newer) > 5 else "") + "). Update its continuation point and state, and set "
            "\"In progress\" back to \"nothing\" if the step is done, so a crashed or new session can resume. "
            "If the work file is already right, say so and stop.")


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
        text = path.read_text(encoding="utf-8")
        if in_progress(text):
            print(f"in progress: {in_progress(text)}")
        newer = changed_since(path)
        if newer:
            print(f"warning: {len(newer)} files changed after it was last updated: {', '.join(newer[:10])}")
    return 0
