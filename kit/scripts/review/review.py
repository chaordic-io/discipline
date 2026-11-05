#!/usr/bin/env python3
"""Bookkeeping for the incremental review loop (.claude/workflows/review-loop.js).

State lives in .claude/review/:
  ledger.json    {unit: {lens: content-hash the pair was last reviewed at}}
  history.jsonl  one line per finding outcome (confirmed/fixed, rejected, open)
  run.json       snapshot taken by `plan` (unit hashes + git tree) for `diff`/`mark`

Commands (all print to stdout; `show`, `diff`, `status` are read-only):
  plan [--max-units N] [--unit ID ...] [--lens L ...] [--stop-at P] [--stop-at-5h P]
                       pick stale (unit, lens) pairs, snapshot the tree, print JSON
  show UNIT            files of a unit + previously reported findings in it (every open and
                       rejected one; only the most recent fixed ones)
  touched [--unit U ...]
                       files changed since the `plan` snapshot (JSON list), optionally limited
                       to units: proves that read-only reviewers wrote nothing
  diff [--unit U] [--since TREE]
                       unified diff since the `plan` snapshot (or TREE), optionally limited to a unit
  record FILE.json     append finding outcomes [{unit,lens,file,line,title,status,reason}]
  mark UNIT:LENS ...   mark pairs reviewed at the current content; also advance
                       pairs that were current at `plan` time (their only changes since
                       are the fixer's, which the delta review covered)
  status               coverage matrix (units x lenses): ok / stale / never
  questions            open questions for the user (numbered): behaviour the spec, decisions and
                       proposals don't settle; the fixer never acts on them
  answer N --reason R  close question N after the user answered it (record the answer in
                       docs/SPEC.md and docs/DECISIONS.md first; R says where)
  open                 findings whose latest outcome is `open`; `plan` carries those with a
                       scenario into the next run (confirmed ones go straight to the fixer,
                       the rest are verified again first)
  quota [--stop-at P] [--stop-at-5h P]
                       weekly/5-hour usage % from the Claude Code status line; ok=false at P

Lens context: a unit may list, per lens, files outside the unit whose changes make that lens stale
for the unit ("context": {"contracts": ["api/openapi.yaml"]}). The (unit, lens) hash then covers the
unit's files plus those, so editing a contract re-queues the contract review of every unit that
implements or consumes it, and nothing else.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".claude" / "review"
UNITS = json.loads((Path(__file__).with_name("units.json")).read_text())
LEDGER = STATE / "ledger.json"
HISTORY = STATE / "history.jsonl"
RUN = STATE / "run.json"
INDEX = STATE / "snapshot.index"
TREES = STATE / "trees.json"  # {unit: git tree id of the working tree when the unit was last marked}


@lru_cache(maxsize=None)
def _rx(pattern: str) -> re.Pattern[str]:
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")


def matches(path: str, patterns: list[str]) -> bool:
    return any(_rx(p).match(path) for p in patterns)


def repo_files() -> list[str]:
    """Tracked + untracked, non-ignored files (git respects .gitignore)."""
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, check=True, capture_output=True,
    ).stdout.decode()
    files = sorted({f for f in out.split("\0") if f and (ROOT / f).is_file()})
    return [f for f in files if not matches(f, UNITS["globalExclude"])]


def unit_files(unit: dict, files: list[str]) -> list[str]:
    return [f for f in files if matches(f, unit["include"]) and not matches(f, unit.get("exclude", []))]


def unit_of(path: str) -> str | None:
    """The unit whose patterns cover path (whether or not the file still exists)."""
    path = path.split(":")[0].removeprefix("./")
    return next((u["id"] for u in UNITS["units"]
                 if matches(path, u["include"]) and not matches(path, u.get("exclude", []))), None)


def _hash(items) -> str:
    """The unit content hash over (path, bytes) pairs in path order: one definition for the
    working tree and for git trees, so a recovered base matches the ledger exactly."""
    h = hashlib.sha256()
    for p, data in items:
        h.update(p.encode() + b"\0" + data + b"\0")
    return h.hexdigest()[:16]


def unit_hash(paths: list[str]) -> str:
    return _hash((p, (ROOT / p).read_bytes()) for p in paths)


def lens_context(unit: dict, lens: str) -> list[str]:
    """Patterns of files outside the unit that this lens also depends on (see the module docstring)."""
    return (unit.get("context") or {}).get(lens, [])


def all_hashes(files: list[str]) -> dict[str, dict[str, str]]:
    """{unit: {lens: hash}}. A lens without context gets the unit's own content hash, so ledgers
    written before lens context existed stay valid."""
    out: dict[str, dict[str, str]] = {}
    for u in UNITS["units"]:
        own = unit_files(u, files)
        base = unit_hash(own)
        out[u["id"]] = {}
        for lens in u["lenses"]:
            ctx = lens_context(u, lens)
            out[u["id"]][lens] = unit_hash(sorted(set(own) | {f for f in files if matches(f, ctx)})) if ctx else base
    return out


def load(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


def save(path: Path, data) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")


def snapshot_tree() -> str:
    """Record the working tree as a git tree object (no commit, no ref, private index)."""
    env = {**os.environ, "GIT_INDEX_FILE": str(INDEX)}
    subprocess.run(["git", "add", "-A", "--", "."], cwd=ROOT, env=env, check=True, capture_output=True)
    return subprocess.run(["git", "write-tree"], cwd=ROOT, env=env, check=True, capture_output=True, text=True).stdout.strip()


def uncovered(files: list[str]) -> list[str]:
    roots = [r + "**" if r.endswith("/") else r for r in UNITS["roots"]]
    covered = set()
    for u in UNITS["units"]:
        covered.update(unit_files(u, files))
    return [f for f in files if matches(f, roots) and f not in covered]


def cmd_plan(a) -> None:
    files = repo_files()
    hashes = all_hashes(files)
    ledger = load(LEDGER, {})
    trees = load(TREES, {})
    pending, lost = [], {}
    for u in UNITS["units"]:
        if a.unit and u["id"] not in a.unit:
            continue
        done = ledger.get(u["id"], {})
        lenses = [l for l in u["lenses"] if (not a.lens or l in a.lens) and done.get(l) != hashes[u["id"]][l]]
        if lenses:
            seen = any(l in done for l in u["lenses"])
            entry = {"unit": u["id"], "lenses": lenses, "reason": "changed" if seen else "never reviewed",
                     "files": len(unit_files(u, files))}
            # Every pending lens reviewed before at a recorded tree: review only the diff since then.
            if all(l in done for l in lenses):
                since = trees.get(u["id"])
                if since and tree_exists(since):
                    entry["since"] = since
                elif len({done[l] for l in lenses}) == 1 and not any(lens_context(u, l) for l in lenses):
                    # Base gone, but one reviewed hash to look for (a hash that covers context files
                    # cannot be matched against a commit's unit content; those get a full review).
                    lost[u["id"]] = done[lenses[0]]
            pending.append(entry)
    # Recorded bases that were pruned: recover them from a commit with the reviewed content.
    recovered = recover_bases(lost)
    for entry in pending:
        if entry["unit"] in recovered:
            entry["since"] = trees[entry["unit"]] = recovered[entry["unit"]]
    if recovered:
        save(TREES, trees)
        pin_trees(set(trees.values()))
    # Never-reviewed units first (in units.json priority order), then changed ones.
    pending.sort(key=lambda p: p["reason"] != "never reviewed")
    selected = pending[: a.max_units]
    tree = snapshot_tree()
    # A diff review is complete when every changed file was read: list them, so the workflow
    # counts only those as skips (a reviewer naming an unchanged file is not a partial review).
    units = {u["id"]: u for u in UNITS["units"]}
    for entry in selected:
        if "since" in entry:
            entry["changed"] = changed_files(entry["since"], tree, units[entry["unit"]])
    save(RUN, {"tree": tree, "hashes": hashes, "selected": selected})
    print(json.dumps({
        "lenses": UNITS["lenses"],
        "quota": quota(a.stop_at, getattr(a, "stop_at_5h", None)),
        "open": carried(),
        "selected": selected,
        "remainingUnits": len(pending) - len(selected),
        "uncovered": uncovered(files)[:30],
    }))


def history() -> list[dict]:
    if not HISTORY.exists():
        return []
    return [json.loads(l) for l in HISTORY.read_text().splitlines() if l.strip()]


def latest_outcomes() -> dict[tuple, dict]:
    """The most recent ledger row per finding. This is the ledger's dedup rule: a finding is
    identified by its unit, file and title."""
    latest: dict[tuple, dict] = {}
    for h in history():
        key = (h.get("unit"), h.get("file"), h.get("title"))
        latest.pop(key, None)  # re-insert, so the dict is ordered by each finding's latest outcome
        latest[key] = h
    return latest


def latest_open() -> list[dict]:
    """Findings whose most recent outcome is `open`."""
    return [h for h in latest_outcomes().values() if h["status"] == "open"]


CARRY_KEYS = ("unit", "lens", "severity", "file", "line", "title", "scenario", "fix", "confirmed")


def carried() -> list[dict]:
    """Open findings detailed enough to act on. `confirmed` is true only for findings a verifier
    confirmed whose fix was deferred; the workflow re-verifies the others before fixing them."""
    return [{**{k: h.get(k) for k in CARRY_KEYS}, "confirmed": h.get("confirmed") is True}
            for h in latest_open() if h.get("scenario")]


STATUSES = {"fixed", "rejected", "open", "question", "answered"}
ROW_KEYS = ("unit", "lens", "severity", "file", "line", "title", "status", "reason", "scenario", "fix",
            "options", "confirmed", "run")


def open_questions() -> list[dict]:
    """Findings whose latest outcome is `question`, in the order they were raised or re-raised."""
    return [h for h in latest_outcomes().values() if h["status"] == "question"]


def cmd_questions(_a) -> None:
    qs = open_questions()
    if not qs:
        print("no open questions")
        return
    for n, q in enumerate(qs, 1):
        print(f"{n}. [{q.get('unit')}] {q['title']} ({q.get('file')}{':' + str(q['line']) if q.get('line') else ''})")
        print(f"   unclear: {q.get('scenario')}")
        for o in q.get("options") or []:
            print(f"   - option: {o}")
        print(f"   recommended: {q.get('fix')}")


def cmd_answer(a) -> None:
    qs = open_questions()
    if not 1 <= a.n <= len(qs):
        sys.exit(f"no open question {a.n} (there are {len(qs)}; see `review.py questions`)")
    if not a.reason.strip():
        sys.exit("give the answer and where it is recorded (--reason)")
    q = qs[a.n - 1]
    with HISTORY.open("a") as fh:
        fh.write(json.dumps({**{k: q.get(k) for k in ROW_KEYS}, "status": "answered", "reason": a.reason}) + "\n")
    print(f"answered: {q['title']}")


def cmd_open(_a) -> None:
    print(json.dumps(latest_open()))


USAGE = Path.home() / ".claude" / "usage" / "statusline.json"


def _pct(value) -> float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def quota(stop_at: float, stop_at_5h: float | None = None) -> dict:
    """Usage from the status line snapshot. Unknown or stale data never blocks, but is flagged.
    The 5-hour limit is checked only when stop_at_5h is given."""
    if not USAGE.exists():
        return {"ok": True, "known": False, "note": "no status line snapshot (~/.claude/usage)"}
    try:
        d = json.loads(USAGE.read_text())
        age = int(time.time()) - int(d.get("captured_at") or 0)
        pct = {k: v.get("used_percentage") for k, v in (d.get("rate_limits") or {}).items() if isinstance(v, dict)}
    except (OSError, ValueError, TypeError, AttributeError) as e:
        return {"ok": True, "known": False, "note": f"unreadable status line snapshot: {e}"}
    week, five = _pct(pct.get("seven_day")), _pct(pct.get("five_hour"))
    ok = (week is None or week < stop_at) and (stop_at_5h is None or five is None or five < stop_at_5h)
    known = week is not None or (stop_at_5h is not None and five is not None)
    return {"ok": ok, "known": known, "week": week, "five_hour": five, "stopAt": stop_at,
            "stopAt5h": stop_at_5h, "ageSeconds": age}


def cmd_quota(a) -> None:
    print(json.dumps(quota(a.stop_at, a.stop_at_5h)))


FIXED_SHOWN = 20


def cmd_show(a) -> None:
    unit = next((u for u in UNITS["units"] if u["id"] == a.unit), None)
    if unit is None:
        sys.exit(f"unknown unit {a.unit}")
    files = unit_files(unit, repo_files())
    print(f"# Unit {unit['id']} — {len(files)} files")
    for f in files:
        print(f"{f}  ({(ROOT / f).stat().st_size} bytes)")
    names = set(files)
    prior = [h for h in latest_outcomes().values() if h.get("unit") == unit["id"] or h.get("file") in names]
    # Open and rejected findings are what a reviewer must not raise again; fixed ones matter less with
    # age, so only the most recent are listed and the history stays a bounded read.
    fixed = [h for h in prior if h["status"] == "fixed"]
    dropped = max(0, len(fixed) - FIXED_SHOWN)
    shown = [h for h in prior if h["status"] != "fixed"] + fixed[dropped:]
    print(f"\n# Previously reported findings in this unit ({len(prior)}) — do not re-report these")
    if dropped:
        print(f"({dropped} older fixed findings not listed)")
    for h in shown:
        reason = (h.get("reason") or "").replace("\n", " ")[:200]
        print(f"- [{h['status']}] ({h.get('lens')}) {h.get('file')}:{h.get('line', '')} {h['title']}" + (f" — {reason}" if reason else ""))


def tree_exists(tree: str) -> bool:
    """Snapshot trees are pinned by `pin_trees`; unpinned ones (older state) may have been pruned."""
    return subprocess.run(["git", "cat-file", "-e", f"{tree}^{{tree}}"], cwd=ROOT, capture_output=True).returncode == 0


TREE_REFS = "refs/review/trees/"
_SNAPSHOT_ID = {"GIT_AUTHOR_NAME": "review-loop", "GIT_AUTHOR_EMAIL": "review-loop@localhost",
                "GIT_COMMITTER_NAME": "review-loop", "GIT_COMMITTER_EMAIL": "review-loop@localhost"}


def _git(*args: str, env: dict | None = None, data: bytes | None = None) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, input=data,
                          env={**os.environ, **(env or {})}).stdout


def pin_trees(trees: set[str]) -> None:
    """Keep every recorded review base alive: snapshot trees are otherwise unreferenced objects
    that `git gc` prunes (which silently turned every diff review into a full one). Each tree is
    wrapped in a parentless commit under refs/review/trees/<tree> (local only; never pushed by
    default); refs of trees no longer recorded are dropped."""
    have = {r.removeprefix(TREE_REFS) for r in _git("for-each-ref", "--format=%(refname)", TREE_REFS).decode().split()}
    for tree in sorted(trees - have):
        if tree_exists(tree):
            commit = _git("commit-tree", "--no-gpg-sign", tree, "-m", "review-loop snapshot", env=_SNAPSHOT_ID).decode().strip()
            _git("update-ref", TREE_REFS + tree, commit)
    for tree in sorted(have - trees):
        _git("update-ref", "-d", TREE_REFS + tree)


def unit_hash_at(unit: dict, ents: dict[str, str]) -> str:
    """unit_hash of `unit` as it is in a git tree, given that tree's {path: blob} entries."""
    paths = sorted(p for p in ents if matches(p, unit["include"]) and not matches(p, unit.get("exclude", [])))
    if not paths:
        return _hash([])
    out = _git("cat-file", "--batch", data="".join(ents[p] + "\n" for p in paths).encode())
    blobs, i = [], 0
    for _ in paths:
        header_end = out.index(b"\n", i)
        size = int(out[i:header_end].split()[2])
        blobs.append(out[header_end + 1: header_end + 1 + size])
        i = header_end + 1 + size + 1
    return _hash(zip(paths, blobs))


def tree_entries(rev: str) -> dict[str, str]:
    """{path: blob id} of the regular files in a commit's or tree's snapshot, globally excluded paths left out."""
    ents = {}
    for e in _git("ls-tree", "-r", "-z", "--full-tree", rev).decode().split("\0"):
        if not e:
            continue
        meta, path = e.split("\t", 1)
        mode, kind, sha = meta.split()
        if kind == "blob" and mode != "120000" and not matches(path, UNITS["globalExclude"]):
            ents[path] = sha
    return ents


def recover_bases(wanted: dict[str, str], depth: int = 50) -> dict[str, str]:
    """For units whose recorded base tree is gone, find a recent commit whose content for the
    unit hashes to exactly the reviewed hash ({unit: hash}). An equal hash proves the unit was
    reviewed at that content, so a diff against it is as good as the lost snapshot. Returns
    {unit: tree id}; units without a match are left out (they get a full review)."""
    if not wanted:
        return {}
    try:
        revs = _git("rev-list", f"--max-count={depth}", "HEAD").decode().split()
    except subprocess.CalledProcessError:
        return {}  # no commits yet
    units = {u["id"]: u for u in UNITS["units"]}
    found: dict[str, str] = {}
    for rev in revs:
        ents = tree_entries(rev)
        for uid, h in wanted.items():
            if uid not in found and unit_hash_at(units[uid], ents) == h:
                found[uid] = _git("rev-parse", f"{rev}^{{tree}}").decode().strip()
        if len(found) == len(wanted):
            break
    return found


def diff_pathspec(unit: dict | None) -> list[str]:
    """The unit's files and every lens's context files (a diff review must see a changed contract)."""
    excl = [f":(exclude,glob){p}" for p in UNITS["globalExclude"]]
    if unit is None:
        return [".", *excl]
    ctx = sorted({p for patterns in (unit.get("context") or {}).values() for p in patterns})
    return [*(f":(glob){p}" for p in unit["include"] + ctx),
            *(f":(exclude,glob){p}" for p in unit.get("exclude", [])), *excl]


def changed_files(since: str, tree: str, unit: dict) -> list[str]:
    """Paths of the unit that were added or changed between two trees: what a diff review must read.

    Deleted files are left out: there is nothing to read, so naming one is never a partial review."""
    out = _git("diff", "--name-only", "-z", "--diff-filter=d", since, tree, "--", *diff_pathspec(unit)).decode()
    return sorted(p for p in out.split("\0") if p)


def cmd_diff(a) -> None:
    since = a.since
    if not since:
        run = load(RUN, None)
        if not run:
            sys.exit("no snapshot: run `plan` first")
        since = run["tree"]
    unit = None
    if a.unit:
        unit = next((u for u in UNITS["units"] if u["id"] == a.unit), None)
        if unit is None:
            sys.exit(f"unknown unit {a.unit}")
    now = snapshot_tree()
    out = subprocess.run(["git", "diff", "--stat", "-p", "--find-renames", since, now, "--", *diff_pathspec(unit)],
                         cwd=ROOT, check=True, capture_output=True, text=True).stdout
    print(out or "(no changes)")


def cmd_touched(a) -> None:
    """Files changed since the plan snapshot, within the given units (or anywhere). The workflow runs
    this after the read-only phases: anything listed was written by a reviewer or a verifier."""
    run = load(RUN, None)
    if not run:
        sys.exit("no snapshot: run `plan` first")
    units = {u["id"]: u for u in UNITS["units"]}
    for uid in a.unit or []:
        if uid not in units:
            sys.exit(f"unknown unit {uid}")
    specs = [diff_pathspec(units[uid]) for uid in a.unit] if a.unit else [diff_pathspec(None)]
    now = snapshot_tree()
    files: set[str] = set()
    for spec in specs:
        out = _git("diff", "--name-only", "-z", "--no-renames", run["tree"], now, "--", *spec).decode()
        files.update(p for p in out.split("\0") if p)
    print(json.dumps(sorted(files)))


def cmd_record(a) -> None:
    rows = json.loads(Path(a.file).read_text())
    STATE.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a") as fh:
        for r in rows:
            if r.get("status") not in STATUSES:
                sys.exit(f"bad status in {r}")
            if not r.get("unit"):
                r["unit"] = unit_of(r.get("file") or "")
            fh.write(json.dumps({k: r.get(k) for k in ROW_KEYS}) + "\n")
    print(f"recorded {len(rows)}")


def cmd_mark(a) -> None:
    run = load(RUN, None)
    if not run:
        sys.exit("no snapshot: run `plan` first")
    hashes = all_hashes(repo_files())
    ledger = load(LEDGER, {})
    advanced = 0
    for uid, lenses in ([] if a.no_advance else ledger.items()):
        for lens, h in lenses.items():
            now = hashes.get(uid, {}).get(lens)
            if now is not None and h == run["hashes"].get(uid, {}).get(lens) and h != now:
                lenses[lens], advanced = now, advanced + 1
    valid = {u["id"]: set(u["lenses"]) for u in UNITS["units"]}
    for pair in a.pairs:
        uid, _, lens = pair.partition(":")
        if lens not in valid.get(uid, set()):
            sys.exit(f"bad pair {pair}")
        ledger.setdefault(uid, {})[lens] = hashes[uid][lens]
    save(LEDGER, ledger)
    # Remember the tree each fully current unit was reviewed at, so a later change is reviewed as a diff.
    tree, trees = snapshot_tree(), load(TREES, {})
    for u in UNITS["units"]:
        now = hashes.get(u["id"], {})
        if u["lenses"] and all(now.get(l) is not None and ledger.get(u["id"], {}).get(l) == now[l] for l in u["lenses"]):
            trees[u["id"]] = tree
    save(TREES, trees)
    pin_trees(set(trees.values()))
    print(f"marked {len(a.pairs)} pairs, advanced {advanced} pairs touched only by reviewed fixes")


def cmd_status(_a) -> None:
    hashes = all_hashes(repo_files())
    ledger = load(LEDGER, {})
    lenses = list(UNITS["lenses"])
    total = ok = 0
    w = max([7, *(len(l) + 2 for l in lenses)])
    print(f"{'unit':26}" + "".join(f"{l:>{w}}" for l in lenses))
    for u in UNITS["units"]:
        row = ""
        for l in lenses:
            if l not in u["lenses"]:
                row += f"{'-':>{w}}"
                continue
            total += 1
            h = ledger.get(u["id"], {}).get(l)
            state = "ok" if h == hashes[u["id"]][l] else ("stale" if h else "never")
            ok += state == "ok"
            row += f"{state:>{w}}"
        print(f"{u['id']:26}{row}")
    latest = latest_outcomes()
    counts = {s: sum(h["status"] == s for h in latest.values()) for s in ("fixed", "rejected", "open", "question", "answered")}
    print(f"\ncoverage {ok}/{total} pairs current; findings so far: {counts}")
    if counts["question"]:
        print(f"{counts['question']} open questions for the user: `python3 scripts/review/review.py questions`")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("plan")
    pl.add_argument("--max-units", type=int, default=8)
    pl.add_argument("--unit", action="append")
    pl.add_argument("--lens", action="append")
    pl.add_argument("--stop-at", type=float, default=80)
    pl.add_argument("--stop-at-5h", type=float, default=None)
    sub.add_parser("show").add_argument("unit")
    df = sub.add_parser("diff")
    df.add_argument("--unit")
    df.add_argument("--since")
    sub.add_parser("record").add_argument("file")
    mk = sub.add_parser("mark")
    mk.add_argument("pairs", nargs="*")
    mk.add_argument("--no-advance", action="store_true", help="fixer changes were not delta-reviewed")
    sub.add_parser("status")
    sub.add_parser("open")
    sub.add_parser("questions")
    an = sub.add_parser("answer")
    an.add_argument("n", type=int)
    an.add_argument("--reason", required=True)
    qu = sub.add_parser("quota")
    qu.add_argument("--stop-at", type=float, default=80)
    qu.add_argument("--stop-at-5h", type=float, default=None)
    tc = sub.add_parser("touched")
    tc.add_argument("--unit", action="append")
    a = p.parse_args()
    {"plan": cmd_plan, "show": cmd_show, "diff": cmd_diff, "record": cmd_record, "mark": cmd_mark,
     "status": cmd_status, "open": cmd_open, "quota": cmd_quota, "touched": cmd_touched,
     "questions": cmd_questions, "answer": cmd_answer}[a.cmd](a)


if __name__ == "__main__":
    main()
