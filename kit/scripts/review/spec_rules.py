#!/usr/bin/env python3
"""Check that every business rule in the spec is pinned by a test, and that no test cites a rule
that no longer exists.

    python3 scripts/review/spec_rules.py      # report; exit 1 on untested rules or unknown references

Switched on by `specRules` in .agents/profile.json (null switches it off):

    "specRules": {
      "spec": "docs/SPEC.md",                 # optional, this is the default
      "pattern": "R-[0-9]+(?:\\\\.[0-9]+)*",     # optional: the rule-ID format (this is the default)
      "tests": ["**/*_test.go", "web/src/**/*.test.ts"],
      "exempt": {"R-7.1": "a support-time promise; checked by the support process, not by code"}
    }

The convention: each rule in the spec starts with its ID (`**R-3.2.1** Invoices are numbered ...`),
and each test that pins a rule names the ID in its name or a comment. An ID matches only as a whole,
so `R-3.2` does not count as a test of `R-3.2.1`. Rules that no automated test can pin go in `exempt`
with the reason. This is stack-independent: it only reads text.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review  # noqa: E402

DEFAULTS = {"spec": "docs/SPEC.md", "pattern": r"R-[0-9]+(?:\.[0-9]+)*"}


def config(profile: dict) -> dict | None:
    raw = profile.get("specRules")
    return None if raw is None else {**DEFAULTS, "exempt": {}, **raw}


def validate_config(raw) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, dict):
        return ["specRules must be null or an object"]
    problems = []
    tests = raw.get("tests")
    if not isinstance(tests, list) or not tests or not all(isinstance(t, str) and t for t in tests):
        problems.append("specRules.tests must list the glob patterns of the test files")
    try:
        re.compile(raw.get("pattern", DEFAULTS["pattern"]))
    except (re.error, TypeError) as e:
        problems.append(f"specRules.pattern is not a valid regular expression: {e}")
    exempt = raw.get("exempt", {})
    if not isinstance(exempt, dict) or not all(isinstance(r, str) and r.strip() for r in exempt.values()):
        problems.append("specRules.exempt must map a rule ID to the reason it has no test")
    return problems


def id_regex(pattern: str) -> re.Pattern[str]:
    """Whole IDs only: no word character or dash around them, and no further `.digit` part."""
    return re.compile(rf"(?<![\w.-])({pattern})(?![\w-]|\.\d)")


def ids_in(text: str, rx: re.Pattern[str]) -> set[str]:
    return {m.group(1) for m in rx.finditer(text)}


def report(cfg: dict, root: Path, files: list[str]) -> dict:
    """{rules, untested: [ids], unknown: {id: [test files]}, staleExempt: [ids]}"""
    rx = id_regex(cfg["pattern"])
    spec_path = root / cfg["spec"]
    rules = ids_in(spec_path.read_text(encoding="utf-8"), rx) if spec_path.exists() else set()
    cited: dict[str, list[str]] = {}
    for f in files:
        if review.matches(f, cfg["tests"]):
            for rid in ids_in((root / f).read_text(encoding="utf-8", errors="replace"), rx):
                cited.setdefault(rid, []).append(f)
    exempt = set(cfg["exempt"])
    return {
        "spec": cfg["spec"],
        "specFound": spec_path.exists(),
        "rules": len(rules),
        "untested": sorted(rules - set(cited) - exempt),
        "unknown": {rid: sorted(fs) for rid, fs in sorted(cited.items()) if rid not in rules},
        "staleExempt": sorted(exempt - rules),
    }


def problems(rep: dict) -> list[str]:
    out = []
    if not rep["specFound"]:
        out.append(f"{rep['spec']} not found")
    if rep["untested"]:
        out.append(f"rules no test cites (pin them, or exempt them with a reason): {', '.join(rep['untested'])}")
    for rid, fs in rep["unknown"].items():
        out.append(f"{rid} is cited by {', '.join(fs)} but is not in {rep['spec']} (renamed or removed?)")
    if rep["staleExempt"]:
        out.append(f"exempt rules no longer in {rep['spec']}: {', '.join(rep['staleExempt'])}")
    return out


def main() -> int:
    profile_path = review.ROOT / ".agents" / "profile.json"
    profile = json.loads(profile_path.read_text()) if profile_path.exists() else {}
    cfg = config(profile)
    if cfg is None:
        print("specRules is off in .agents/profile.json")
        return 0
    bad = validate_config(profile["specRules"])
    if bad:
        print("invalid specRules: " + "; ".join(bad), file=sys.stderr)
        return 2
    rep = report(cfg, review.ROOT, review.repo_files())
    print(f"{rep['rules']} rules in {rep['spec']}, {len(rep['untested'])} untested, {len(cfg['exempt'])} exempt")
    for p in problems(rep):
        print(p)
    return 1 if problems(rep) else 0


if __name__ == "__main__":
    sys.exit(main())
