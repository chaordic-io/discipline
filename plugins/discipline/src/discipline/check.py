"""The gate checks: `discipline check`.

Run by every project's gate (locally and in CI). Problems fail the gate; warnings are printed and
don't. Each check reads only the project's own files:

- review units (`.claude/review/units.json`): every file under `roots` belongs to exactly one unit, unit
  IDs are unique, every lens a unit uses is configured, `context` names only lenses the unit uses;
- the profile (`.agents/profile.json`): once filled in, the units' lenses are exactly the ones it
  selects, and each custom lens's checklist exists (one without a review-context section is a warning);
  a profile set up with an older discipline version is a warning (run /discipline:upgrade);
- spec rules (`specRules` in the profile): every rule in the spec is named by a test;
- AI evals (`ai`/`aiEvals` in the profile): every prompt has its eval set and facets;
- the decision log: docs/DECISIONS.md is the current index of docs/decisions/ (and each decision has
  an Area, a warning);
- assumptions: text in docs/ marked "(assumed <date> …)" that nobody has confirmed yet (warnings);
- work files: on the default branch, work files of merged branches left behind (warnings);
- handover budgets: files every session reads that have grown past their budget (warnings).
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__, ai_evals, assumptions, decisions, handover, lenses, review, spec_rules, work


def _older(a: str, b: str) -> bool:
    def parts(v: str) -> tuple:
        return tuple(int(x) if x.isdigit() else 0 for x in v.split(".")[:3])
    return parts(a) < parts(b)


@dataclass
class Result:
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def section(self, name: str, problems: list[str] = (), warnings: list[str] = ()) -> None:
        self.problems += [f"{name}: {p}" for p in problems]
        self.warnings += [f"{name}: {w}" for w in warnings]


def check_units(units: dict, files: list[str]) -> list[str]:
    out = []
    if not units.get("units"):
        return [f"no review units configured in {review.UNITS_FILE.relative_to(review.ROOT)} (run /discipline:bootstrap)"]
    ids = [u["id"] for u in units["units"]]
    out += [f"unit id {i!r} is used more than once" for i in sorted({i for i in ids if ids.count(i) > 1})]
    for u in units["units"]:
        unknown = [l for l in u["lenses"] if l not in lenses.names(units)]
        if unknown:
            out.append(f"unit {u['id']} uses lenses that are not configured: {unknown}")
        stray = [l for l in (u.get("context") or {}) if l not in u["lenses"]]
        if stray:
            out.append(f"unit {u['id']} has context for lenses it does not use: {stray}")
    for f in files:
        owners = [u["id"] for u in units["units"] if review.unit_files(u, [f])]
        if len(owners) > 1:
            out.append(f"{f} belongs to several units: {owners}")
    uncovered = review.uncovered(files)
    if uncovered:
        more = f" (and {len(uncovered) - 20} more)" if len(uncovered) > 20 else ""
        out.append(f"files under the roots that no unit covers (add them to a unit): {', '.join(uncovered[:20])}{more}")
    return out


def run(root: Path | None = None) -> Result:
    root = root or review.ROOT
    res = Result()
    units = review.UNITS
    files = review.repo_files()
    res.section("units", check_units(units, files))

    profile_path = root / ".agents" / "profile.json"
    profile = json.loads(profile_path.read_text()) if profile_path.exists() else None
    if profile is None:
        res.section("profile", warnings=[".agents/profile.json is missing (run /discipline:bootstrap)"])
        return res
    if profile.get("discipline") and _older(str(profile["discipline"]), __version__):
        res.section("profile", warnings=[f"set up with discipline {profile['discipline']}; this is {__version__}: "
                                         "run /discipline:upgrade"])
    if not lenses.is_filled(profile):
        res.section("profile", warnings=[".agents/profile.json is still the template: fill it in, then `discipline lenses apply`"])
    else:
        try:
            problems = lenses.check(profile, units)
            used = {l for u in units.get("units", []) for l in u["lenses"]}
            unused = [] if problems or not units.get("units") else [l for l in lenses.selected(profile) if l not in used]
            warns = [f"lenses on but used by no unit (add them where they apply): {', '.join(unused)}"] if unused else []
            context = root / ".agents" / "review-context.md"
            text = context.read_text(encoding="utf-8") if context.exists() else ""
            own = [l for l in lenses.custom(profile) if l in lenses.selected(profile)]
            missing = [l for l in own if f"\n## {l}\n" not in text]
            if missing and context.exists():
                warns.append(f"custom lenses without a section in .agents/review-context.md: {', '.join(missing)}")
            res.section("profile", problems, warns)
        except lenses.ProfileError as e:
            res.section("profile", [f"invalid: {e}"])
            return res
        cfg = spec_rules.config(profile)
        if cfg is not None:
            res.section("spec rules", spec_rules.problems(spec_rules.report(cfg, root, files)))
        if profile.get("ai"):
            res.section("ai evals", ai_evals.problems(ai_evals.report(profile["aiEvals"], files)))
    errs, warns = decisions.problems(root / "docs" / "decisions", root / "docs" / "DECISIONS.md")
    res.section("decisions", errs, warns)
    assumed = assumptions.find(root)
    if assumed:
        res.section("assumptions", warnings=[f"{len(assumed)} assumptions not confirmed (`discipline assumptions`): "
                                             + ", ".join(f"{f}:{n}" for f, n, _, _ in assumed[:10])
                                             + (" …" if len(assumed) > 10 else "")])
    left = work.leftovers()
    if left:
        res.section("work files", warnings=[f"on the default branch, work files of merged branches remain: {', '.join(left)} "
                                            "(fold them into STATUS.md and HISTORY.md, then delete them)"])
    branch = work.current_branch()
    newer = work.changed_since(work.file_for(branch)) if branch else []
    if newer:
        res.section("work files", warnings=[f"{len(newer)} files changed after this branch's work file was last updated "
                                            f"({', '.join(newer[:5])}{' …' if len(newer) > 5 else ''}): update its continuation point"])
    res.section("handover", warnings=[f"{line} (trim it: /discipline:working, \"Keeping the handover files small\")"
                                      for line in handover.over_budget_lines(root, units)])
    return res


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="discipline check", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--json", action="store_true", help="print the result as JSON")
    a = p.parse_args(argv)
    res = run()
    if a.json:
        print(json.dumps({"problems": res.problems, "warnings": res.warnings}, indent=1))
    else:
        for w in res.warnings:
            print(f"warning  {w}")
        for pr in res.problems:
            print(f"PROBLEM  {pr}")
        print(f"discipline check: {len(res.problems)} problems, {len(res.warnings)} warnings")
    return 1 if res.problems else 0
