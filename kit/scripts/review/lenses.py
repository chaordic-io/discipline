#!/usr/bin/env python3
"""Choose the review lenses from the project profile (.agents/profile.json).

    python3 scripts/review/lenses.py show    # each lens, on or off, and why
    python3 scripts/review/lenses.py apply   # write the selection into scripts/review/units.json
    python3 scripts/review/lenses.py check   # exit 1 if units.json and the profile disagree

The profile records what kind of product this is: its kinds, its languages, the interfaces that
separately built or released parts depend on, and how much performance matters. The rules in
`decide` turn that into lenses, so reviewers run only where they can find something: no localisation
review for a product in one language, no contract review without an interface. `overrides` adds or
removes a lens by hand, with the reason written next to it.

Re-run `apply` whenever the profile changes (a second language, a public API, a mobile client).
`apply` only edits the `lenses` map, the units' lens lists and their `context`; it never adds a lens
to a unit, because only you know where a newly enabled lens applies.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import spec_rules  # noqa: E402

ROOT = HERE.parents[1]
PROFILE = ROOT / ".agents" / "profile.json"
UNITS_FILE = HERE / "units.json"

# Every lens the kit knows, with its checklist. The order is the column order of `review.py status`.
CATALOGUE: dict[str, str] = {
    "security": ".claude/agents/security-auditor.md",
    "behaviour": ".claude/agents/behaviour-reviewer.md",
    "tests": ".claude/agents/test-coverage-reviewer.md",
    "architecture": ".claude/agents/architecture-reviewer.md",
    "duplication": ".claude/agents/duplication-reviewer.md",
    "performance": ".claude/agents/performance-reviewer.md",
    "supply-chain": ".claude/agents/supply-chain-reviewer.md",
    "contracts": ".claude/agents/contract-reviewer.md",
    "localisation": ".claude/agents/localisation-reviewer.md",
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
    "supply-chain": "every project has dependencies, a build or CI",
}


# The template's placeholder, spelled so that install.py doesn't list this file as still to adapt.
PLACEHOLDER = "<" + "PROJECT>"


class ProfileError(ValueError):
    pass


def load_profile(path: Path = PROFILE) -> dict:
    return json.loads(path.read_text())


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
    overrides = profile.get("overrides", {})
    for side in ("add", "remove"):
        entries = overrides.get(side, {})
        if not isinstance(entries, dict):
            problems.append(f"overrides.{side} must map a lens to the reason for the override")
            continue
        for lens, reason in entries.items():
            if lens not in CATALOGUE:
                problems.append(f"overrides.{side}: unknown lens {lens!r}")
            if not isinstance(reason, str) or not reason.strip():
                problems.append(f"overrides.{side}.{lens}: give the reason")
    problems.extend(spec_rules.validate_config(profile.get("specRules")))
    both = set(overrides.get("add", {})) & set(overrides.get("remove", {}))
    if both:
        problems.append(f"overrides both add and remove {sorted(both)}")
    if problems:
        raise ProfileError("; ".join(problems))


def decide(profile: dict) -> list[tuple[str, bool, str]]:
    """(lens, on, reason) for every lens in the catalogue, in catalogue order."""
    validate(profile)
    kinds, interfaces, langs = set(profile["kinds"]), profile.get("interfaces", []), profile["languages"]
    out: dict[str, tuple[bool, str]] = {lens: (True, why) for lens, why in CORE.items()}

    perf = profile["performance"]
    out["performance"] = (perf != "minor", f"performance: {perf} ({PERFORMANCE[perf]})")

    if interfaces:
        out["contracts"] = (True, "interfaces: " + ", ".join(interfaces))
    else:
        out["contracts"] = (False, "no interface that a separately built or released part depends on")

    ui = sorted(kinds & UI_KINDS)
    if len(langs) > 1 and ui:
        out["localisation"] = (True, f"{len(langs)} languages ({', '.join(langs)}) shown in {', '.join(ui)}")
    elif not ui:
        out["localisation"] = (False, "no user interface")
    else:
        out["localisation"] = (False, f"one language ({langs[0]})")

    overrides = profile.get("overrides", {})
    for lens, reason in overrides.get("add", {}).items():
        out[lens] = (True, f"override: {reason}")
    for lens, reason in overrides.get("remove", {}).items():
        out[lens] = (False, f"override: {reason}")
    return [(lens, *out[lens]) for lens in CATALOGUE]


def selected(profile: dict) -> dict[str, str]:
    """{lens: checklist} of the lenses the profile turns on."""
    return {lens: CATALOGUE[lens] for lens, on, _ in decide(profile) if on}


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


def check(profile: dict, units: dict, root: Path = ROOT) -> list[str]:
    """Problems that make units.json disagree with the profile (empty when they agree)."""
    want = selected(profile)
    problems = []
    if units.get("lenses") != want:
        problems.append(f"units.json lenses {sorted(units.get('lenses', {}))} != profile {sorted(want)} "
                        "(run `python3 scripts/review/lenses.py apply`)")
    for u in units["units"]:
        extra = [l for l in u["lenses"] if l not in want]
        if extra:
            problems.append(f"unit {u['id']} uses lenses the profile turns off: {extra}")
        stray = [l for l in (u.get("context") or {}) if l not in u["lenses"]]
        if stray:
            problems.append(f"unit {u['id']} has context for lenses it does not use: {stray}")
    for lens, path in want.items():
        if not (root / path).exists():
            problems.append(f"checklist for {lens} missing: {path} (copy it from the bootstrap kit)")
    return problems


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["show", "apply", "check"])
    p.add_argument("--profile", type=Path, default=PROFILE)
    p.add_argument("--units", type=Path, default=UNITS_FILE)
    a = p.parse_args(argv)
    profile = load_profile(a.profile)
    if not is_filled(profile):
        print(f"{a.profile} is still the template: fill it in first (see BOOTSTRAP.md)", file=sys.stderr)
        return 2
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
    off = [CATALOGUE[l] for l, on, _ in decisions if not on and (ROOT / CATALOGUE[l]).exists()]
    if off:
        print("\nChecklists of lenses that are off (keep them for later, or delete them):\n  " + "\n  ".join(off))
    return 0


if __name__ == "__main__":
    sys.exit(main())
