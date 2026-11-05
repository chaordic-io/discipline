#!/usr/bin/env python3
"""Install the bootstrap kit into a repository.

    python3 install.py [TARGET] [--dry-run] [--statusline]

TARGET defaults to the current directory. Files are copied from kit/ to their places in TARGET
(CLAUDE.md, .agents/, .claude/, scripts/review/, docs/). Existing files are never overwritten: they are
listed as "kept", so you can merge by hand. --statusline also installs the usage status line into
~/.claude/ (see BOOTSTRAP.md, "The usage guard"). At the end the script lists every file that still has
ADAPT markers or <PROJECT> placeholders to fill in.

Needs only Python 3.10+; the kit itself needs nothing else from the repository it came from.
"""
from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent / "kit"

# Kit path prefix → target path prefix. Names that Claude Code treats specially (CLAUDE.md, .claude/)
# are stored under neutral names in the kit, so they don't act as instructions while the kit itself is
# being edited.
MAPPING: list[tuple[str, str]] = [
    ("CLAUDE.template.md", "CLAUDE.md"),
    ("agents-folder/", ".agents/"),
    ("claude/", ".claude/"),
    ("scripts/", "scripts/"),
    ("docs/", "docs/"),
]

# Files installed elsewhere (home directory), only on request.
HOME_FILES = {"home/statusline-usage.sh": ".claude/statusline-usage.sh"}

# Empty directories the review loop writes into.
EMPTY_DIRS = [".claude/review"]

MARKERS = ("ADAPT", "<PROJECT>")


def target_of(rel: str) -> str | None:
    """Where a kit file goes, relative to the target repository; None for home files."""
    if rel in HOME_FILES:
        return None
    for src, dst in MAPPING:
        if rel == src or (src.endswith("/") and rel.startswith(src)):
            return dst + rel[len(src):]
    raise ValueError(f"kit file without a destination: {rel}")


def kit_files() -> list[str]:
    files = []
    for path in sorted(KIT.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            files.append(path.relative_to(KIT).as_posix())
    return files


def copy(src: Path, dst: Path, dry_run: bool) -> str:
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


def install(target: Path, dry_run: bool = False, statusline: bool = False, home: Path | None = None) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {"new": [], "kept": [], "adapt": []}
    for rel in kit_files():
        dst_rel = target_of(rel)
        if dst_rel is None:
            continue
        outcome = copy(KIT / rel, target / dst_rel, dry_run)
        result[outcome].append(dst_rel)
    for d in EMPTY_DIRS:
        if not dry_run:
            (target / d).mkdir(parents=True, exist_ok=True)
    if statusline:
        home = home or Path(os.path.expanduser("~"))
        for rel, dst_rel in HOME_FILES.items():
            outcome = copy(KIT / rel, home / dst_rel, dry_run)
            result[outcome].append(f"~/{dst_rel}")
    for dst_rel in result["new"] + result["kept"]:
        if not dst_rel.startswith("~") and needs_adapting(target / dst_rel if not dry_run else KIT / source_of(dst_rel)):
            result["adapt"].append(dst_rel)
    return result


def source_of(dst_rel: str) -> str:
    for src, dst in MAPPING:
        if dst_rel == dst or (dst.endswith("/") and dst_rel.startswith(dst)):
            return src + dst_rel[len(dst):]
    raise ValueError(dst_rel)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", default=".")
    parser.add_argument("--dry-run", action="store_true", help="show what would be copied, copy nothing")
    parser.add_argument("--statusline", action="store_true", help="also install ~/.claude/statusline-usage.sh")
    args = parser.parse_args(argv)
    target = Path(args.target).resolve()
    if not target.is_dir():
        print(f"not a directory: {target}", file=sys.stderr)
        return 2
    result = install(target, dry_run=args.dry_run, statusline=args.statusline)
    verb = "would copy" if args.dry_run else "copied"
    for f in result["new"]:
        print(f"{verb}: {f}")
    for f in result["kept"]:
        print(f"kept (exists, merge by hand): {f}")
    if result["adapt"]:
        print("\nStill to adapt (ADAPT markers or <PROJECT> placeholders):")
        for f in result["adapt"]:
            print(f"  {f}")
    print("\nNext: follow BOOTSTRAP.md, 'Set up a repository', from step 3.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
