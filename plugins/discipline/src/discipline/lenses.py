#!/usr/bin/env python3
"""Choose the review lenses from the project profile (.agents/profile.json).

    discipline lenses show    # each lens, on or off, and why
    discipline lenses apply   # write the selection into .claude/review/units.json
    discipline lenses check   # exit 1 if units.json and the profile disagree
    discipline lenses new NAME --why REASON [--checklist PATH] [--second-opinion]
                              # add a project's own lens: its checklist, profile entry and context section

The profile records what kind of product this is: its kinds, its languages, the interfaces that
separately built or released parts depend on, and how much performance matters. The rules in
`decide` turn that into lenses, so reviewers run only where they can find something: no localisation
review for a product in one language, no contract review without an interface. `overrides` adds or
removes a lens by hand, with the reason written next to it.

`customLenses` adds the project's own lenses next to the plugin's: {name: {checklist, why,
secondOpinion?}}. The checklist is a file in the repository, written like the plugin's (by default
`.claude/agents/<name>-reviewer.md`, so it also works as a project agent by hand). A custom lens is on
while it is declared; `overrides.remove` turns it off like any other. With `secondOpinion`, a refuted
critical/high finding of the lens gets a second verifier, as security and supply-chain findings do.
Editing a custom checklist does not re-queue earlier reviews; `discipline review requeue` does.

Re-run `apply` whenever the profile changes (a second language, a public API, a mobile client).
`apply` only edits the `lenses` map, the units' lens lists and their `context`; it never adds a lens
to a unit, because only you know where a newly enabled lens applies.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import ai_evals, plugin, review, spec_rules

ROOT = review.ROOT
PROFILE = ROOT / ".agents" / "profile.json"
UNITS_FILE = review.UNITS_FILE

# Every lens the plugin knows, with its checklist (an agent in the plugin's agents/ folder, also usable
# by hand as `discipline:<name>`). The order is the column order of `discipline review status`.
CATALOGUE: dict[str, str] = {
    "security": "security-auditor.md",
    "behaviour": "behaviour-reviewer.md",
    "tests": "test-coverage-reviewer.md",
    "architecture": "architecture-reviewer.md",
    "duplication": "duplication-reviewer.md",
    "simplicity": "simplicity-reviewer.md",
    "performance": "performance-reviewer.md",
    "supply-chain": "supply-chain-reviewer.md",
    "contracts": "contract-reviewer.md",
    "ai": "ai-reviewer.md",
    "localisation": "localisation-reviewer.md",
}

KINDS = {
    "web-app": "an application used in a browser",
    "mobile-app": "an iOS or Android app",
    "desktop-app": "an installed desktop application",
    "internal-tool": "an application for the organisation's own staff",
    "static-site": "a static or mostly static website (marketing, docs)",
    "public-api": "an API offered to third parties",
    "backend-service": "a service consumed by the organisation's own clients or services",
    "library": "a package other code depends on",
    "cli": "a command-line tool",
    "data-pipeline": "batch or streaming data processing, ML",
}
# Kinds whose users read text the product shows them.
UI_KINDS = {"web-app", "mobile-app", "desktop-app", "internal-tool", "static-site"}

INTERFACES = {
    "frontend-backend": "a browser client and its backend, built from the same repository or not",
    "mobile-backend": "a mobile app and its backend; old app versions stay in use",
    "public-api": "an API third parties integrate with",
    "service-to-service": "APIs, events or queues between the organisation's own services",
    "published-library": "the public exports of a published package",
}

PERFORMANCE = {
    "critical": "latency or throughput budgets are part of the product",
    "normal": "it must stay fast at the expected sizes",
    "minor": "small data, few users, or nothing on a hot path",
}

CORE = {
    "security": "every project",
    "behaviour": "every project has intended behaviour",
    "tests": "every project",
    "architecture": "every project",
    "duplication": "every project",
    "simplicity": "every project (agents tend to build more structure than the code needs)",
    "supply-chain": "every project has dependencies, a build or CI",
}


# Built-in lenses whose refuted critical/high findings get a second, independent verifier.
SECOND_OPINION = ["security", "supply-chain"]

# A custom lens name: it becomes a status column, a CLI argument and a review-context heading.
LENS_NAME = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

# The template's placeholder, spelled so that `discipline init` doesn't list this file as still to adapt.
PLACEHOLDER = "<" + "PROJECT>"


class ProfileError(ValueError):
    pass


def load_profile(path: Path = PROFILE) -> dict:
    return json.loads(path.read_text())


def project_profile() -> dict:
    """This repository's profile, or {} when there is none yet or it isn't valid JSON."""
    try:
        return load_profile()
    except (OSError, ValueError):
        return {}


def custom(profile: dict) -> dict[str, dict]:
    """The profile's own lenses ({name: {checklist, why, secondOpinion?}}), as declared."""
    entries = profile.get("customLenses") or {}
    return entries if isinstance(entries, dict) else {}


def checklist_path(lens: str, profile: dict | None = None) -> Path:
    """The checklist file of a lens: the plugin's for a built-in lens, the repository's for a custom one."""
    if lens in CATALOGUE:
        return plugin.agent_file(CATALOGUE[lens])
    own = custom(project_profile() if profile is None else profile)
    entry = own.get(lens)
    if not isinstance(entry, dict) or not isinstance(entry.get("checklist"), str):
        raise ProfileError(f"unknown lens {lens} (one of {', '.join([*CATALOGUE, *own])})")
    return ROOT / entry["checklist"]


def second_opinion(profile: dict) -> list[str]:
    """The lenses whose refuted critical/high findings get a second verifier."""
    return SECOND_OPINION + [l for l, e in custom(profile).items() if isinstance(e, dict) and e.get("secondOpinion")]


def is_filled(profile: dict) -> bool:
    """False for the template as installed (placeholders, no kinds yet)."""
    return PLACEHOLDER not in json.dumps(profile) and bool(profile.get("kinds"))


def validate(profile: dict) -> None:
    problems = []

    def known(field: str, allowed, values) -> None:
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            problems.append(f"{field} must be a list of strings")
            return
        problems.extend(f"{field}: unknown value {v!r} (one of {', '.join(allowed)})" for v in values if v not in allowed)

    known("kinds", KINDS, profile.get("kinds", []))
    known("interfaces", INTERFACES, profile.get("interfaces", []))
    langs = profile.get("languages", [])
    if not isinstance(langs, list) or not langs or not all(isinstance(v, str) and v for v in langs):
        problems.append("languages must list at least one language the product's users read")
    if profile.get("performance") not in PERFORMANCE:
        problems.append(f"performance must be one of {', '.join(PERFORMANCE)}")
    own = profile.get("customLenses", {})
    if not isinstance(own, dict):
        problems.append("customLenses must map a lens name to {checklist, why}")
        own = {}
    for lens, entry in own.items():
        if lens in CATALOGUE:
            problems.append(f"customLenses: {lens!r} is a built-in lens (use overrides.add to turn it on)")
        elif not LENS_NAME.match(lens):
            problems.append(f"customLenses: {lens!r} is not a lens name (lowercase letters, digits and hyphens)")
        if not isinstance(entry, dict):
            problems.append(f"customLenses.{lens} must be {{checklist, why}}")
            continue
        checklist = entry.get("checklist")
        if not isinstance(checklist, str) or not checklist.strip() or checklist.startswith("/") or ".." in Path(checklist).parts:
            problems.append(f"customLenses.{lens}.checklist must be a repository-relative path")
        if not isinstance(entry.get("why"), str) or not entry["why"].strip():
            problems.append(f"customLenses.{lens}.why: give the reason")
        if not isinstance(entry.get("secondOpinion", False), bool):
            problems.append(f"customLenses.{lens}.secondOpinion must be true or false")
        stray = sorted(set(entry) - {"checklist", "why", "secondOpinion"})
        if stray:
            problems.append(f"customLenses.{lens}: unknown fields {stray}")
    overrides = profile.get("overrides", {})
    for side in ("add", "remove"):
        entries = overrides.get(side, {})
        if not isinstance(entries, dict):
            problems.append(f"overrides.{side} must map a lens to the reason for the override")
            continue
        for lens, reason in entries.items():
            if lens not in CATALOGUE and lens not in own:
                problems.append(f"overrides.{side}: unknown lens {lens!r}")
            if not isinstance(reason, str) or not reason.strip():
                problems.append(f"overrides.{side}.{lens}: give the reason")
    problems.extend(spec_rules.validate_config(profile.get("specRules")))
    earlier = profile.get("decisionsElsewhere", [])
    if not isinstance(earlier, list) or not all(isinstance(d, str) and d.strip("/") for d in earlier):
        problems.append("decisionsElsewhere must be a list of folders (repository-relative)")
    ai = profile.get("ai", [])
    if not isinstance(ai, list) or not all(isinstance(m, str) for m in ai):
        problems.append("ai must be a list of modes ([] for none)")
        ai = []
    else:
        problems.extend(f"ai: unknown mode {m!r} (one of {', '.join(ai_evals.MODES)}; [] for none)" for m in ai if m not in ai_evals.MODES)
    problems.extend(ai_evals.validate_config(profile.get("aiEvals"), ai))
    both = set(overrides.get("add", {})) & set(overrides.get("remove", {}))
    if both:
        problems.append(f"overrides both add and remove {sorted(both)}")
    if problems:
        raise ProfileError("; ".join(problems))


def decide(profile: dict) -> list[tuple[str, bool, str]]:
    """(lens, on, reason) for every lens in the catalogue, in catalogue order, then the profile's own
    lenses in the order they are declared."""
    validate(profile)
    kinds, interfaces, langs = set(profile["kinds"]), profile.get("interfaces", []), profile["languages"]
    out: dict[str, tuple[bool, str]] = {lens: (True, why) for lens, why in CORE.items()}

    perf = profile["performance"]
    out["performance"] = (perf != "minor", f"performance: {perf} ({PERFORMANCE[perf]})")

    if interfaces:
        out["contracts"] = (True, "interfaces: " + ", ".join(interfaces))
    else:
        out["contracts"] = (False, "no interface that a separately built or released part depends on")

    ai = profile.get("ai", [])
    out["ai"] = (bool(ai), "calls models: " + ", ".join(ai) if ai else "calls no models")

    ui = sorted(kinds & UI_KINDS)
    if len(langs) > 1 and ui:
        out["localisation"] = (True, f"{len(langs)} languages ({', '.join(langs)}) shown in {', '.join(ui)}")
    elif not ui:
        out["localisation"] = (False, "no user interface")
    else:
        out["localisation"] = (False, f"one language ({langs[0]})")

    own = custom(profile)
    for lens, entry in own.items():
        out[lens] = (True, f"custom: {entry['why']}")

    overrides = profile.get("overrides", {})
    for lens, reason in overrides.get("add", {}).items():
        out[lens] = (True, f"override: {reason}")
    for lens, reason in overrides.get("remove", {}).items():
        out[lens] = (False, f"override: {reason}")
    return [(lens, *out[lens]) for lens in [*CATALOGUE, *own]]


def selected(profile: dict) -> list[str]:
    """The lenses the profile turns on, in catalogue order."""
    return [lens for lens, on, _ in decide(profile) if on]


def names(units: dict) -> list[str]:
    """The lens names configured in units.json (a list; older files had a {lens: path} map)."""
    return list(units.get("lenses") or [])


def apply(profile: dict, units: dict) -> tuple[dict, dict[str, list[str]], list[str]]:
    """The units with the profile's lenses: (new units, {unit: lenses removed}, enabled lenses no unit uses)."""
    lenses = selected(profile)
    removed: dict[str, list[str]] = {}
    new = {**units, "lenses": lenses, "units": []}
    for u in units["units"]:
        u = dict(u)
        gone = [l for l in u["lenses"] if l not in lenses]
        if gone:
            removed[u["id"]] = gone
        u["lenses"] = [l for l in u["lenses"] if l in lenses]
        if "context" in u:
            ctx = {l: p for l, p in u["context"].items() if l in u["lenses"]}
            if ctx:
                u["context"] = ctx
            else:
                del u["context"]
        new["units"].append(u)
    used = {l for u in new["units"] for l in u["lenses"]}
    return new, removed, [l for l in lenses if l not in used]


def check(profile: dict, units: dict) -> list[str]:
    """Problems that make units.json disagree with the profile (empty when they agree)."""
    want = selected(profile)
    problems = []
    if names(units) != want:
        problems.append(f"units.json lenses {names(units)} != profile {want} (run `discipline lenses apply`)")
    for u in units["units"]:
        extra = [l for l in u["lenses"] if l not in want]
        if extra:
            problems.append(f"unit {u['id']} uses lenses the profile turns off: {extra}")
        stray = [l for l in (u.get("context") or {}) if l not in u["lenses"]]
        if stray:
            problems.append(f"unit {u['id']} has context for lenses it does not use: {stray}")
    for lens, entry in custom(profile).items():
        if lens in want and not (ROOT / entry["checklist"]).is_file():
            problems.append(f"custom lens {lens}: checklist {entry['checklist']} does not exist")
    return problems


CONTEXT_FILE = ROOT / ".agents" / "review-context.md"


def new_lens(name: str, why: str, checklist: str | None, second: bool, profile_path: Path,
             units_path: Path) -> list[str]:
    """Add a custom lens: its checklist (from the template, never overwritten), its profile entry, its
    review-context section, and a globalExclude entry when the checklist sits under a review root.
    Returns what was done, one line each."""
    checklist = checklist or f".claude/agents/{name}-reviewer.md"
    profile = load_profile(profile_path)
    entry = {"checklist": checklist, "why": why.strip()}
    if second:
        entry["secondOpinion"] = True
    candidate = {**profile, "customLenses": {**custom(profile), name: entry}}
    validate(candidate)  # name, clash with a built-in lens, path, reason
    if name in custom(profile):
        raise ProfileError(f"{name} is already a custom lens in {profile_path.name}")
    done = []
    path = ROOT / checklist
    if path.exists():
        done.append(f"kept {checklist} (already there)")
    else:
        template = plugin.root() / "skills" / "bootstrap" / "reference" / "lens-checklist.md"
        text = template.read_text(encoding="utf-8")
        text = text.replace("{name}", name).replace("{NAME}", name.replace("-", " ").upper()).replace("{why}", why.strip())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        done.append(f"wrote {checklist} (fill in its ADAPT parts)")
    profile_path.write_text(json.dumps(candidate, indent=2, ensure_ascii=False) + "\n")
    done.append(f"added {name} to customLenses in {profile_path.name}")
    if CONTEXT_FILE.exists() and f"\n## {name}\n" not in CONTEXT_FILE.read_text(encoding="utf-8"):
        with CONTEXT_FILE.open("a", encoding="utf-8") as fh:
            fh.write(f"\n## {name}\n\n- <!-- ADAPT: this project's specifics for the {name} lens -->\n")
        done.append(f"added a ## {name} section to .agents/review-context.md")
    if units_path.exists():
        units = json.loads(units_path.read_text())
        roots = [r + "**" if r.endswith("/") else r for r in units.get("roots", [])]
        if review.matches(checklist, roots) and not review.matches(checklist, units.get("globalExclude", [])):
            units["globalExclude"] = [*units.get("globalExclude", []), checklist]
            units_path.write_text(json.dumps(units, indent=2, ensure_ascii=False) + "\n")
            done.append(f"added {checklist} to globalExclude in units.json (a checklist is not reviewed code)")
    return done


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="discipline lenses", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["show", "apply", "check", "new"])
    p.add_argument("name", nargs="?", help="new: the lens name (lowercase, hyphens)")
    p.add_argument("--why", help="new: why the project needs this lens")
    p.add_argument("--checklist", help="new: where the checklist goes (default .claude/agents/NAME-reviewer.md)")
    p.add_argument("--second-opinion", action="store_true",
                   help="new: refuted critical/high findings of this lens get a second verifier")
    p.add_argument("--profile", type=Path, default=PROFILE)
    p.add_argument("--units", type=Path, default=UNITS_FILE)
    a = p.parse_args(argv)
    profile = load_profile(a.profile)
    if not is_filled(profile):
        print(f"{a.profile} is still the template: fill it in first (see /discipline:bootstrap)", file=sys.stderr)
        return 2
    if a.cmd == "new":
        if not a.name or not (a.why or "").strip():
            print("usage: discipline lenses new NAME --why REASON [--checklist PATH] [--second-opinion]", file=sys.stderr)
            return 2
        try:
            done = new_lens(a.name, a.why, a.checklist, a.second_opinion, a.profile, a.units)
        except ProfileError as e:
            print(f"cannot add lens {a.name}: {e}", file=sys.stderr)
            return 2
        print("\n".join(done))
        print(f"\nNext: fill in the checklist and the review-context section, run `discipline lenses apply`, "
              f"then add {a.name} to the units where it applies.")
        return 0
    if a.name:
        p.error(f"{a.cmd} takes no lens name")
    try:
        decisions = decide(profile)
    except ProfileError as e:
        print(f"invalid profile: {e}", file=sys.stderr)
        return 2
    units = json.loads(a.units.read_text())
    if a.cmd == "show":
        for lens, on, why in decisions:
            print(f"{'on ' if on else 'off'}  {lens:13} {why}")
        return 0
    if a.cmd == "check":
        problems = check(profile, units)
        for problem in problems:
            print(problem)
        return 1 if problems else 0
    new, removed, unused = apply(profile, units)
    a.units.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n")
    for lens, on, why in decisions:
        print(f"{'on ' if on else 'off'}  {lens:13} {why}")
    for uid, gone in removed.items():
        print(f"removed from unit {uid}: {', '.join(gone)}")
    if unused:
        print(f"\nEnabled but used by no unit yet; add them to the units where they apply: {', '.join(unused)}")
    return 0
