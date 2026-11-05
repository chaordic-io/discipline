"""Print one of the plugin's guides: `discipline doc <name>`.

    discipline doc engineering   the engineering principles E1–E10 (how we build)
    discipline doc working       the way of working (request loop, verification, delegation, handover)
    discipline doc stack         choosing a stack: criteria S1–S7, shapes, the capability checklist
    discipline doc bootstrap     setting a repository up: the questions and the steps
    discipline doc upgrade       moving a repository to a newer discipline version

Inside Claude Code these are the plugin's skills (/discipline:<name>); this command gives the same text
to subagents that can't invoke a skill, and to anyone outside Claude Code.
"""
from __future__ import annotations

import argparse

from . import plugin

GUIDES = {
    "engineering": ("engineering", None),
    "working": ("working", None),
    "stack": ("stack", "reference/choosing-a-stack.md"),
    "bootstrap": ("bootstrap", None),
    "upgrade": ("upgrade", None),
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="discipline doc", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("name", choices=sorted(GUIDES))
    a = p.parse_args(argv)
    skill, extra = GUIDES[a.name]
    print(plugin.body(plugin.skill_file(skill)))
    if extra:
        print("\n" + plugin.body(plugin.root() / "skills" / skill / extra))
    return 0
