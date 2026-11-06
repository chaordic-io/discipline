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

`--survey` copies nothing: it lists what the repository already has that the method also covers
(agent instructions, specs, decision records, a gate and CI, handover-like files), files that would
be kept, uncommitted changes, and the size of the code. /discipline:bootstrap runs it first and asks
what to do with each before anything is copied.

/discipline:bootstrap runs this as its first step, then walks through the questions.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
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


# What an existing repository may already have that the method also covers: (kind, what bootstrap asks).
SURVEY_KINDS = {
    "instructions": "agent instructions: keep and add the method's rules as their own section, merge, or import them",
    "spec": "specs or requirements: link from docs/SPEC.md, or move into it",
    "decisions": "decision records: keep where they are (decisionsElsewhere), or migrate to docs/decisions/",
    "architecture": "architecture notes: link from docs/SPEC.md's architecture section",
    "handover": "status, roadmap or history notes: fold into .agents/STATUS.md and HISTORY.md, or link",
    "gate": "an existing gate or CI: add `discipline check` to it rather than a second gate",
    "agent-config": "existing Claude Code or agent configuration: kept; check it doesn't conflict",
}
_INSTRUCTIONS = ["CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", "GEMINI.md", ".cursorrules",
                 ".cursor/rules", ".windsurfrules", ".clinerules", ".github/copilot-instructions.md", "CONVENTIONS.md"]
_GATE = ["Makefile", "justfile", "Justfile", "Taskfile.yml", "package.json", ".github/workflows", ".gitlab-ci.yml",
         ".circleci", "Jenkinsfile", "azure-pipelines.yml", "bitbucket-pipelines.yml", ".travis.yml", ".buildkite", ".pre-commit-config.yaml",
         "mise.toml", ".tool-versions"]
_HANDOVER = ["STATUS.md", "TODO.md", "ROADMAP.md", "HISTORY.md", "CHANGELOG.md", "NOTES.md", ".agents"]
_AGENT_CONFIG = [".claude/settings.json", ".claude/agents", ".claude/commands", ".claude/skills", ".claude/workflows", ".mcp.json"]
_DOC_DIRS = ["docs", "doc", "documentation", "adr", "adrs", "decisions", "architecture"]
_SPEC_NAME = re.compile(r"(spec|requirement|prd|product|functional)", re.I)
_ARCH_NAME = re.compile(r"architecture|design", re.I)
_DECISION_DIR = re.compile(r"^(adrs?|decisions?|decision-records?|architecture-decisions?)$", re.I)


def _git_lines(target: Path, *args: str) -> list[str] | None:
    r = subprocess.run(["git", *args], cwd=target, capture_output=True, text=True)
    return r.stdout.splitlines() if r.returncode == 0 else None


def survey(target: Path) -> dict:
    """What the repository already has: {"found": [(kind, path, note)], "dirty": [...], "files": n, "lines": n}."""
    found: list[tuple[str, str, str]] = []

    def add(kind: str, rel: str, note: str = "") -> None:
        if not any(p == rel for _, p, _ in found):
            found.append((kind, rel, note))

    for rel in _INSTRUCTIONS:
        if (target / rel).exists():
            add("instructions", rel)
    for rel in ("SPEC.md", "REQUIREMENTS.md", "PRD.md", "docs/SPEC.md"):
        if (target / rel).exists():
            add("spec", rel)
    for rel in ("ARCHITECTURE.md",):
        if (target / rel).exists():
            add("architecture", rel)
    for top in _DOC_DIRS:
        base = target / top
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            rel = path.relative_to(target).as_posix()
            if len(path.relative_to(target).parts) > 4 or "node_modules" in path.parts:
                continue
            if path.is_dir() and _DECISION_DIR.match(path.name):
                n = len(list(path.glob("*.md")))
                if rel == "docs/decisions":
                    from . import decisions  # noqa: PLC0415
                    odd = [p.name for p in path.glob("*.md") if p.name != "README.md" and not decisions.NAME.match(p.name)]
                    if odd:
                        add("decisions", rel, f"{len(odd)} files not named <YYYY-MM-DD>-<slug>.md: the gate would fail; "
                                              "rename them or move them to their own folder")
                else:
                    add("decisions", rel, f"{n} files")
            elif path.is_file() and path.suffix == ".md" and not any(_DECISION_DIR.match(part) for part in path.parts[:-1]):
                if _SPEC_NAME.search(path.stem):
                    add("spec", rel)
                elif _ARCH_NAME.search(path.stem):
                    add("architecture", rel)
        if _DECISION_DIR.match(top) and base.is_dir():
            add("decisions", top, f"{len(list(base.glob('*.md')))} files")
    if (target / "DECISIONS.md").exists():
        add("decisions", "DECISIONS.md")
    for rel in _HANDOVER:
        if (target / rel).exists():
            add("handover", rel)
    for rel in _GATE:
        if (target / rel).exists():
            add("gate", rel)
    for rel in _AGENT_CONFIG:
        if (target / rel).exists():
            add("agent-config", rel)
    tracked = _git_lines(target, "ls-files") or []
    dirty = _git_lines(target, "status", "--porcelain") or []
    lines = 0
    for rel in tracked:
        try:
            with open(target / rel, "rb") as fh:
                lines += sum(1 for _ in fh)
        except OSError:
            pass
    return {"found": found, "dirty": dirty, "files": len(tracked), "lines": lines}


def print_survey(target: Path) -> None:
    s = survey(target)
    print(f"Code: {s['files']} tracked files, about {s['lines']} lines.")
    if s["dirty"]:
        print(f"Uncommitted changes: {len(s['dirty'])} paths (commit or stash them first, so bootstrap's files "
              "don't mix with work in progress).")
    if not s["found"]:
        print("Nothing found that the method also covers: a fresh setup.")
        return
    print("\nFound (bootstrap asks what to do with each before copying anything):")
    for kind in SURVEY_KINDS:
        items = [(p, n) for k, p, n in s["found"] if k == kind]
        if items:
            print(f"  {kind}: {SURVEY_KINDS[kind]}")
            for p, n in items:
                print(f"    {p}" + (f"  ({n})" if n else ""))
    kept = [target_of(rel) for rel in template_files() if target_of(rel) and (target / target_of(rel)).exists()]
    if kept:
        print("\nTemplates that would be kept, not copied (same name exists): " + ", ".join(kept))


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
    p.add_argument("--survey", action="store_true", help="list what the repository already has; copy nothing")
    a = p.parse_args(argv)
    target = Path(a.target).resolve()
    if not target.is_dir():
        print(f"not a directory: {target}")
        return 2
    if a.survey:
        print_survey(target)
        return 0
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
    print("\nNext: the questions in /discipline:bootstrap.")
    return 0
