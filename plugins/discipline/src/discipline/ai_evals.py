#!/usr/bin/env python3
"""Check that every prompt has its eval set, with the facets its kind of AI feature needs.

    discipline ai-evals      # report; exit 1 on a prompt without its evals

Switched on by `aiEvals` in .agents/profile.json, which is required when `ai` lists any mode:

    "ai": ["rag", "agentic"],
    "aiEvals": {
      "prompts": ["prompts/**"],              # every matching file is one prompt, named by its file stem
      "evals": "evals/{name}",                # where that prompt's eval set lives (a file or a directory)
      "facets": {                             # optional: per prompt glob, the parts its eval set must have
        "prompts/search/**": ["query", "retrieval", "answer"],
        "prompts/agents/**": ["task", "trajectory", "safety"]
      }
    }

A facet exists when the eval set has a file or directory of that name (`evals/answer-question/retrieval/`
or `evals/answer-question/retrieval.yaml`). The facets by mode:
rag → query, retrieval, answer; assistive → output; agentic → task, trajectory, safety (E10 in
`discipline doc engineering`). This check
proves the eval sets exist; the eval suite itself (live model calls, scores against thresholds) is a
slow suite, run on every prompt or model change and before a release.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path, PurePosixPath

from . import review

MODES = {
    "rag": "answers from retrieved documents",
    "assistive": "suggests or drafts; a person decides",
    "agentic": "acts through tools, in several steps",
}
FACETS = {
    "rag": ["query", "retrieval", "answer"],
    "assistive": ["output"],
    "agentic": ["task", "trajectory", "safety"],
}


def validate_config(raw, ai: list) -> list[str]:
    if not ai:
        return [] if raw is None else ["aiEvals is set but `ai` lists no mode"]
    if not isinstance(raw, dict):
        return ["aiEvals is required when `ai` lists a mode (where prompts and their eval sets live)"]
    problems = []
    prompts = raw.get("prompts")
    if not isinstance(prompts, list) or not prompts or not all(isinstance(p, str) and p for p in prompts):
        problems.append("aiEvals.prompts must list the glob patterns of the prompt files")
    evals = raw.get("evals")
    if not isinstance(evals, str) or "{name}" not in evals:
        problems.append("aiEvals.evals must be a path containing {name}, e.g. evals/{name}")
    facets = raw.get("facets", {})
    if not isinstance(facets, dict) or not all(
            isinstance(v, list) and v and all(isinstance(f, str) and f and "/" not in f for f in v) for v in facets.values()):
        problems.append("aiEvals.facets must map a prompt glob to a list of facet names")
    return problems


def _present(path: str, files: set[str]) -> bool:
    """A file at path, a file under path/, or (for a facet) a file named path.<ext>."""
    return any(f == path or f.startswith(path + "/") or (f.startswith(path + ".") and "/" not in f[len(path):])
               for f in files)


def report(cfg: dict, files: list[str]) -> dict:
    """{prompts, missing: {name: [paths]}, duplicates: {name: [prompt files]}}"""
    names: dict[str, list[str]] = {}
    for f in files:
        if review.matches(f, cfg["prompts"]):
            names.setdefault(PurePosixPath(f).stem, []).append(f)
    present = set(files)
    missing: dict[str, list[str]] = {}
    for name, sources in sorted(names.items()):
        base = cfg["evals"].format(name=name)
        need = [] if _present(base, present) else [base]
        for glob, facets in cfg.get("facets", {}).items():
            if any(review.matches(s, [glob]) for s in sources):
                need += [f"{base}/{facet}" for facet in facets if not _present(f"{base}/{facet}", present)]
        if need:
            missing[name] = sorted(set(need))
    return {"prompts": len(names), "missing": missing,
            "duplicates": {n: sorted(s) for n, s in names.items() if len(s) > 1}}


def problems(rep: dict) -> list[str]:
    out = [f"prompt {name} has no {', '.join(paths)}" for name, paths in rep["missing"].items()]
    out += [f"two prompts share the name {n}: {', '.join(fs)} (eval sets are found by name)"
            for n, fs in rep["duplicates"].items()]
    return out


def main(argv: list[str] | None = None) -> int:  # noqa: ARG001  (no options)
    path = review.ROOT / ".agents" / "profile.json"
    profile = json.loads(path.read_text()) if path.exists() else {}
    ai, cfg = profile.get("ai") or [], profile.get("aiEvals")
    bad = validate_config(cfg, ai)
    if bad:
        print("invalid profile: " + "; ".join(bad), file=sys.stderr)
        return 2
    if not ai:
        print("the profile lists no AI mode")
        return 0
    rep = report(cfg, review.repo_files())
    print(f"{rep['prompts']} prompts, {len(rep['missing'])} without their complete eval set")
    for p in problems(rep):
        print(p)
    return 1 if problems(rep) else 0

