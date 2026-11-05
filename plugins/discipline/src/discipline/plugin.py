"""Where the plugin's files are: the agents (lens checklists), the skills (with the bootstrap templates)
and the workflow.

Run from the plugin (Claude Code's `bin/discipline`, or a checkout), the package sits at
`<plugin>/src/discipline`, two levels below the plugin root. Installed as a wheel (`uvx`, `uv tool
install`), the same files are bundled inside the package as `discipline/_plugin/`.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent


def root() -> Path:
    for candidate in (os.environ.get("DISCIPLINE_PLUGIN_ROOT"), PACKAGE.parents[1], PACKAGE / "_plugin"):
        if candidate and (Path(candidate) / "agents").is_dir():
            return Path(candidate)
    raise FileNotFoundError("the discipline plugin's files (agents/, skills/) were not found next to the package")


def agent_file(name: str) -> Path:
    return root() / "agents" / name


def skill_file(skill: str) -> Path:
    return root() / "skills" / skill / "SKILL.md"


FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.S)


def body(path: Path) -> str:
    """A markdown file without its YAML frontmatter."""
    return FRONTMATTER.sub("", path.read_text(encoding="utf-8"), count=1).lstrip("\n")
