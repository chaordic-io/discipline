"""Set a repository up with the working method: `discipline init [TARGET] [--dry-run] [--statusline]`.

Copies the bootstrap templates into TARGET (default: the current directory): CLAUDE.md, .agents/,
.claude/review/ and docs/. Existing files are never overwritten: they are listed as "kept", so you can
merge by hand. It also enables the discipline plugin for everyone working in the repository, in
.claude/settings.json (adding keys, never changing ones that are there), adds the review loop's
per-run scratch files and each person's own .agents/USER.local.md to .gitignore, marks the
append-only files for git's union merge in .gitattributes (so branches never conflict on them), and
stamps the version into a new .agents/profile.json. --statusline also installs the usage status line into ~/.claude/ (see the
usage guard in /discipline:bootstrap). At the end it lists every file that still has ADAPT markers or
<PROJECT> placeholders to fill in.

/discipline:bootstrap runs this as its first step, then walks through the questions.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
from pathlib import Path

from . import __version__, plugin

# Template path prefix → target path prefix. Names Claude Code treats specially (CLAUDE.md, .claude/)
# are stored under neutral names in the templates, so they don't act as instructions inside the plugin.
MAPPING: list[tuple[str, str]] = [
    ("CLAUDE.template.md", "CLAUDE.md"),
    ("agents-folder/", ".agents/"),
    ("claude/", ".claude/"),
    ("docs/", "docs/"),
]
HOME_FILES = {"home/statusline-usage.sh": ".claude/statusline-usage.sh"}
EMPTY_DIRS = [".claude/review"]
MARKERS = ("ADAPT", "<PROJECT>")

# Per-run files of the review loop: the ledger, history and trees are committed (shared review state);
# these are scratch files of a single run and are never committed.
GITIGNORE = [
    "# discipline: per-run review-loop files (ledger, history and trees are committed); personal preferences",
    ".claude/review/run.json",
    ".claude/review/snapshot.index",
    ".claude/review/outcomes.tmp.json",
    ".agents/USER.local.md",
]
# Append-only files that branches add to: git's built-in union merge keeps both sides' lines, so
# merging two branches never conflicts on them. The decision index is regenerated after a merge.
GITATTRIBUTES = [
    "# discipline: append-only files, merged by keeping both sides",
    ".claude/review/ledger.jsonl merge=union",
    ".claude/review/history.jsonl merge=union",
    ".claude/review/trees.jsonl merge=union",
    ".agents/HISTORY.md merge=union",
    "docs/DECISIONS.md merge=union",
]

MARKETPLACE = "chaordic"
MARKETPLACE_SOURCE = {"source": {"source": "github", "repo": "chaordic-io/discipline"}}
PLUGIN_ID = f"discipline@{MARKETPLACE}"


def templates() -> Path:
    return plugin.root() / "skills" / "bootstrap" / "templates"


def target_of(rel: str) -> str | None:
    """Where a template goes, relative to the target repository; None for home files."""
    if rel in HOME_FILES:
        return None
    for src, dst in MAPPING:
        if rel == src or (src.endswith("/") and rel.startswith(src)):
            return dst + rel[len(src):]
    raise ValueError(f"template without a destination: {rel}")


def template_files() -> list[str]:
    base = templates()
    return [p.relative_to(base).as_posix() for p in sorted(base.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts]


def _copy(src: Path, dst: Path, dry_run: bool) -> str:
    if dst.exists():
        return "kept"
    if not dry_run:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if dst.suffix in {".py", ".sh"}:
            dst.chmod(dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return "new"


def needs_adapting(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError):
        return False
    return any(m in text for m in MARKERS)


def enable_plugin(target: Path, dry_run: bool) -> list[str]:
    """Add the marketplace and enable the plugin in the project's .claude/settings.json. Returns what was
    added; existing keys (even a disabled plugin) are left as they are."""
    path = target / ".claude" / "settings.json"
    settings = json.loads(path.read_text()) if path.exists() else {}
    added = []
    markets = settings.setdefault("extraKnownMarketplaces", {})
    if MARKETPLACE not in markets:
        markets[MARKETPLACE] = MARKETPLACE_SOURCE
        added.append(f"extraKnownMarketplaces.{MARKETPLACE}")
    enabled = settings.setdefault("enabledPlugins", {})
    if PLUGIN_ID not in enabled:
        enabled[PLUGIN_ID] = True
        added.append(f"enabledPlugins.{PLUGIN_ID}")
    if added and not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings, indent=2) + "\n")
    return added


def add_lines(path: Path, lines: list[str], dry_run: bool) -> list[str]:
    """Add the lines that are missing (the first is a comment heading the block). Returns those added."""
    text = path.read_text() if path.exists() else ""
    have = {line.strip() for line in text.splitlines()}
    missing = [line for line in lines[1:] if line not in have]
    if missing and not dry_run:
        block = ([lines[0]] if lines[0].splitlines()[0] not in have else []) + missing
        prefix = "" if not text or text.endswith("\n") else "\n"
        path.write_text(text + prefix + ("\n" if text else "") + "\n".join(block) + "\n")
    return missing


def ignore_run_files(target: Path, dry_run: bool) -> list[str]:
    return add_lines(target / ".gitignore", GITIGNORE, dry_run)


def stamp_profile(target: Path) -> None:
    path = target / ".agents" / "profile.json"
    profile = json.loads(path.read_text())
    stamped = {"discipline": __version__, **{k: v for k, v in profile.items() if k != "discipline"}}
    if "_comment" in profile:  # keep the comment first
        stamped = {"_comment": profile["_comment"], "discipline": __version__,
                   **{k: v for k, v in profile.items() if k not in ("_comment", "discipline")}}
    path.write_text(json.dumps(stamped, indent=2, ensure_ascii=False) + "\n")


def install(target: Path, dry_run: bool = False, statusline: bool = False, home: Path | None = None) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {"new": [], "kept": [], "adapt": [], "settings": [], "gitignore": [], "gitattributes": []}
    base = templates()
    for rel in template_files():
        dst_rel = target_of(rel)
        if dst_rel is None:
            continue
        outcome = _copy(base / rel, target / dst_rel, dry_run)
        result[outcome].append(dst_rel)
    if not dry_run:
        for d in EMPTY_DIRS:
            (target / d).mkdir(parents=True, exist_ok=True)
        if ".agents/profile.json" in result["new"]:
            stamp_profile(target)
    result["settings"] = enable_plugin(target, dry_run)
    result["gitignore"] = ignore_run_files(target, dry_run)
    result["gitattributes"] = add_lines(target / ".gitattributes", GITATTRIBUTES, dry_run)
    if statusline:
        home = home or Path(os.path.expanduser("~"))
        for rel, dst_rel in HOME_FILES.items():
            outcome = _copy(base / rel, home / dst_rel, dry_run)
            result[outcome].append(f"~/{dst_rel}")
    for dst_rel in result["new"] + result["kept"]:
        if dst_rel.startswith("~"):
            continue
        source = target / dst_rel if not dry_run else base / source_of(dst_rel)
        if needs_adapting(source):
            result["adapt"].append(dst_rel)
    return result


def source_of(dst_rel: str) -> str:
    for src, dst in MAPPING:
        if dst_rel == dst or (dst.endswith("/") and dst_rel.startswith(dst)):
            return src + dst_rel[len(dst):]
    raise ValueError(dst_rel)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="discipline init", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("target", nargs="?", default=".")
    p.add_argument("--dry-run", action="store_true", help="show what would be copied, copy nothing")
    p.add_argument("--statusline", action="store_true", help="also install ~/.claude/statusline-usage.sh")
    a = p.parse_args(argv)
    target = Path(a.target).resolve()
    if not target.is_dir():
        print(f"not a directory: {target}")
        return 2
    result = install(target, dry_run=a.dry_run, statusline=a.statusline)
    verb = "would copy" if a.dry_run else "copied"
    for f in result["new"]:
        print(f"{verb}: {f}")
    for f in result["kept"]:
        print(f"kept (exists, merge by hand): {f}")
    for key in result["settings"]:
        print(f"{'would add' if a.dry_run else 'added'} to .claude/settings.json: {key}")
    for line in result["gitignore"]:
        print(f"{'would add' if a.dry_run else 'added'} to .gitignore: {line}")
    for line in result["gitattributes"]:
        print(f"{'would add' if a.dry_run else 'added'} to .gitattributes: {line}")
    if result["adapt"]:
        print("\nStill to adapt (ADAPT markers or <PROJECT> placeholders):")
        for f in result["adapt"]:
            print(f"  {f}")
    print("\nNext: the questions in /discipline:bootstrap (step 3 onwards).")
    return 0
