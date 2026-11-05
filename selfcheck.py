#!/usr/bin/env python3
"""Self-check of the bootstrap kit: `python3 selfcheck.py` (or `python3 -m unittest selfcheck`).

Proves that the kit works on its own: it installs the kit into an empty, freshly created git
repository and runs the review loop's own tests there, checks that the kit's texts don't depend on
the repository the kit came from, and that every path the texts mention exists after installing.

The kit is the master copy of the review scripts and the workflow. When it sits inside a repository
that has installed copies (scripts/review/, .claude/workflows/review-loop.js), it also checks that
those have not drifted from the kit; outside such a repository (e.g. the kit's own repository) the
drift tests skip.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import install  # noqa: E402

# Installed verbatim into every repository; their test data uses synthetic example paths.
VERBATIM = {"scripts/review/review.py", "scripts/review/test_review.py", "scripts/review/lenses.py",
            "scripts/review/spec_rules.py", "scripts/review/ai_evals.py", "scripts/review/handover.py"}

# Names that would tie the kit to the repository it was extracted from. Worked examples live in
# stacks/ and may name it; nothing in kit/ or BOOTSTRAP.md may.
SOURCE_NAMES = re.compile(r"Hourmark|hourmark|gethourmark|Chaordic|api/internal|web/src/i18n|\.agents/bootstrap/templates")

# Installed-repository paths the texts mention that are created later, not by install.py.
CREATED_LATER = {"docs/history.md"}

# Paths in backticks that point into an installed repository.
INSTALLED_PATH = re.compile(r"`((?:\.agents|\.claude|scripts/review|docs)/[\w./-]+\.[a-z]+)`")
KIT_PATH = re.compile(r"`((?:kit|stacks)/[\w./-]+\.[a-z]+)`|\]\(((?:kit|stacks)/[\w./-]+\.[a-z]+)\)")


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class InstallTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "kit@example.invalid")
        git(self.repo, "config", "user.name", "kit")
        git(self.repo, "config", "commit.gpgsign", "false")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_every_kit_file_has_a_destination(self) -> None:
        for rel in install.kit_files():
            if rel not in install.HOME_FILES:
                self.assertIsNotNone(install.target_of(rel), rel)

    def test_installs_into_an_empty_repository_and_its_review_tests_pass(self) -> None:
        result = install.install(self.repo)
        self.assertIn("CLAUDE.md", result["new"])
        self.assertIn(".claude/workflows/review-loop.js", result["new"])
        self.assertTrue((self.repo / ".claude/review").is_dir())
        # A repository with one file under a unit, so coverage has something to check.
        (self.repo / "src").mkdir()
        (self.repo / "src/main.txt").write_text("hello\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")
        run = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "scripts/review", "-q"],
            cwd=self.repo, capture_output=True, text=True,
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        status = subprocess.run([sys.executable, "scripts/review/review.py", "status"], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(status.returncode, 0, status.stderr)

    def test_a_filled_profile_selects_the_lenses_and_the_tests_hold_it(self) -> None:
        install.install(self.repo)
        (self.repo / "src").mkdir()
        (self.repo / "src/main.txt").write_text("hello\n")
        lenses = [sys.executable, "scripts/review/lenses.py"]
        tests = [sys.executable, "-m", "unittest", "discover", "-s", "scripts/review", "-q"]
        run = lambda cmd: subprocess.run(cmd, cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(run(lenses + ["check"]).returncode, 2, "the template profile must be refused")
        (self.repo / ".agents/profile.json").write_text(json.dumps({
            "product": "A static marketing site", "kinds": ["static-site"], "languages": ["en"],
            "interfaces": [], "performance": "minor", "data": "none", "overrides": {"add": {}, "remove": {}}}))
        self.assertEqual(run(lenses + ["check"]).returncode, 1)
        failing = run(tests)
        self.assertNotEqual(failing.returncode, 0, "the gate must fail while units.json disagrees with the profile")
        self.assertIn("test_units_follow_the_profile", failing.stderr)
        applied = run(lenses + ["apply"])
        self.assertEqual(applied.returncode, 0, applied.stderr)
        units = json.loads((self.repo / "scripts/review/units.json").read_text())
        self.assertEqual(list(units["lenses"]), ["security", "behaviour", "tests", "architecture", "duplication", "supply-chain"])
        passing = run(tests)
        self.assertEqual(passing.returncode, 0, passing.stdout + passing.stderr)

    def test_an_ai_profile_turns_on_the_ai_lens_and_the_tests_require_eval_facets(self) -> None:
        install.install(self.repo)
        lenses = [sys.executable, "scripts/review/lenses.py"]
        tests = [sys.executable, "-m", "unittest", "discover", "-s", "scripts/review", "-q"]
        run = lambda cmd: subprocess.run(cmd, cwd=self.repo, capture_output=True, text=True)
        (self.repo / ".agents/profile.json").write_text(json.dumps({
            "product": "Support assistant", "kinds": ["web-app"], "languages": ["en"], "interfaces": [],
            "performance": "normal", "data": "customer tickets", "overrides": {"add": {}, "remove": {}},
            "ai": ["rag"], "aiEvals": {"prompts": ["prompts/**"], "evals": "evals/{name}",
                                       "facets": {"prompts/**": ["query", "retrieval", "answer"]}}}))
        self.assertEqual(run(lenses + ["apply"]).returncode, 0)
        units = json.loads((self.repo / "scripts/review/units.json").read_text())
        self.assertIn("ai", units["lenses"])
        (self.repo / "prompts").mkdir()
        (self.repo / "prompts/answer.md").write_text("Answer from the documents.\n")
        (self.repo / "evals/answer").mkdir(parents=True)
        (self.repo / "evals/answer/query.yaml").write_text("[]\n")
        failing = run(tests)
        self.assertNotEqual(failing.returncode, 0)
        self.assertIn("evals/answer/retrieval", failing.stderr)
        for facet in ("retrieval", "answer"):
            (self.repo / f"evals/answer/{facet}.yaml").write_text("[]\n")
        passing = run(tests)
        self.assertEqual(passing.returncode, 0, passing.stdout + passing.stderr)

    def test_spec_rules_switched_on_fail_the_tests_until_every_rule_is_pinned(self) -> None:
        install.install(self.repo)
        (self.repo / "tests").mkdir()
        lenses = [sys.executable, "scripts/review/lenses.py"]
        tests = [sys.executable, "-m", "unittest", "discover", "-s", "scripts/review", "-q"]
        run = lambda cmd: subprocess.run(cmd, cwd=self.repo, capture_output=True, text=True)
        (self.repo / ".agents/profile.json").write_text(json.dumps({
            "product": "Invoicing", "kinds": ["web-app"], "languages": ["en"], "interfaces": [],
            "performance": "normal", "data": "customer data", "overrides": {"add": {}, "remove": {}},
            "specRules": {"tests": ["tests/**"]}}))
        self.assertEqual(run(lenses + ["apply"]).returncode, 0)
        spec = self.repo / "docs/SPEC.md"
        spec.write_text(spec.read_text() + "\n**R-1** Invoice numbers have no gaps.\n")
        (self.repo / "tests/test_numbering.txt").write_text("placeholder\n")
        failing = run(tests)
        self.assertNotEqual(failing.returncode, 0)
        self.assertIn("R-1", failing.stderr)
        (self.repo / "tests/test_numbering.txt").write_text("pins R-1\n")
        passing = run(tests)
        self.assertEqual(passing.returncode, 0, passing.stdout + passing.stderr)

    def test_never_overwrites(self) -> None:
        (self.repo / "CLAUDE.md").write_text("mine\n")
        result = install.install(self.repo)
        self.assertIn("CLAUDE.md", result["kept"])
        self.assertEqual((self.repo / "CLAUDE.md").read_text(), "mine\n")

    def test_dry_run_copies_nothing(self) -> None:
        result = install.install(self.repo, dry_run=True)
        self.assertTrue(result["new"])
        self.assertFalse((self.repo / "CLAUDE.md").exists())
        self.assertIn("CLAUDE.md", result["adapt"])

    def test_statusline_goes_to_home_only_on_request(self) -> None:
        home = self.tmp / "home"
        install.install(self.repo, home=home)
        self.assertFalse((home / ".claude/statusline-usage.sh").exists())
        install.install(self.repo, statusline=True, home=home)
        self.assertTrue((home / ".claude/statusline-usage.sh").exists())

    def test_every_installed_path_the_texts_mention_exists(self) -> None:
        install.install(self.repo)
        texts = [HERE / "BOOTSTRAP.md", *[HERE / "kit" / r for r in install.kit_files() if r.endswith(".md")]]
        for text in texts:
            for m in INSTALLED_PATH.finditer(text.read_text()):
                path = m.group(1)
                # .claude/review/ holds state the review loop writes at run time; the archives are
                # created when a handover file passes its budget (WORKING.md).
                if "<" in path or "*" in path or path.startswith(".claude/review/") or path in CREATED_LATER:
                    continue
                self.assertTrue((self.repo / path).exists(), f"{text.name} mentions {path}, which the kit does not install")


class TextTest(unittest.TestCase):
    def test_kit_does_not_name_its_source_repository(self) -> None:
        texts = [HERE / "BOOTSTRAP.md", HERE / "install.py", *[HERE / "kit" / r for r in install.kit_files() if r not in VERBATIM]]
        for text in texts:
            for n, line in enumerate(text.read_text().splitlines(), 1):
                self.assertIsNone(SOURCE_NAMES.search(line), f"{text.relative_to(HERE)}:{n}: {line.strip()}")

    def test_kit_and_stack_paths_in_bootstrap_exist(self) -> None:
        for name in ["BOOTSTRAP.md", *[p.relative_to(HERE).as_posix() for p in (HERE / "stacks").rglob("*.md")]]:
            for m in KIT_PATH.finditer((HERE / name).read_text()):
                path = m.group(1) or m.group(2)
                self.assertTrue((HERE / path).exists(), f"{name} mentions {path}")

    def test_relative_links_in_stacks_resolve(self) -> None:
        for doc in (HERE / "stacks").rglob("*.md"):
            for target in re.findall(r"\]\(([^)#:]+)\)", doc.read_text()):
                self.assertTrue((doc.parent / target).exists(), f"{doc.relative_to(HERE)} links to {target}")

    def test_principles_and_criteria_are_numbered_and_every_citation_exists(self) -> None:
        """E1..En (how we build, kit/agents-folder/ENGINEERING.md) and S1..Sn (stack selection,
        stacks/README.md): numbered without gaps; every E- or S-number cited anywhere exists; no
        citation of the retired P-numbers remains."""
        series = {
            "E": set(re.findall(r"\*\*(E\d+)\. ", (HERE / "kit/agents-folder/ENGINEERING.md").read_text())),
            "S": set(re.findall(r"\*\*(S\d+)\. ", (HERE / "stacks/README.md").read_text())),
        }
        for prefix, ids in series.items():
            self.assertTrue(ids, prefix)
            self.assertEqual(ids, {f"{prefix}{n}" for n in range(1, len(ids) + 1)}, f"{prefix} numbered without gaps")
        docs = [HERE / "BOOTSTRAP.md", *(HERE / "stacks").rglob("*.md"),
                *[HERE / "kit" / r for r in install.kit_files() if r.endswith((".md", ".js", ".py"))]]
        for doc in docs:
            text = re.sub(r"noqa:[^\n]*", "", doc.read_text())  # linter codes such as E402 are not citations
            for prefix, ids in series.items():
                for cited in re.findall(rf"\b{prefix}(\d+)\b", text):
                    self.assertIn(f"{prefix}{cited}", ids, f"{doc.relative_to(HERE)} cites {prefix}{cited}")
            self.assertEqual(re.findall(r"\bP\d+\b", text), [], f"{doc.relative_to(HERE)} cites a retired P-number")

    def test_every_lens_in_the_catalogue_has_its_checklist_and_the_example_units_use_them_all(self) -> None:
        sys.path.insert(0, str(HERE / "kit/scripts/review"))
        try:
            import lenses
        finally:
            sys.path.pop(0)
        units = json.loads((HERE / "kit/scripts/review/units.json").read_text())
        self.assertEqual(units["lenses"], lenses.CATALOGUE)
        self.assertEqual({l for u in units["units"] for l in u["lenses"]}, set(lenses.CATALOGUE))
        for path in lenses.CATALOGUE.values():
            kit_path = path.replace(".claude/", "claude/", 1)
            self.assertEqual(install.target_of(kit_path), path)
            self.assertTrue((HERE / "kit" / kit_path).exists(), path)

    def test_workflow_takes_its_lenses_from_the_plan_and_runs_reviewers_read_only(self) -> None:
        workflow = (HERE / "kit/claude/workflows/review-loop.js").read_text()
        self.assertIn("const LENS_FILE = plan.lenses", workflow)
        self.assertIn("const READER = 'review-reader'", workflow)
        self.assertTrue((HERE / "kit/claude/agents/review-reader.md").exists())
        for label in ("review:", "verify:", "verify2:", "delta:"):
            call = workflow[workflow.index(f"label: `{label}"):]
            self.assertIn("agentType: READER", call[: call.index("\n")], label)


class DriftTest(unittest.TestCase):
    """Only inside a repository that has the live copies; skipped once the kit stands alone."""

    # The kit installed as <repo>/.agents/bootstrap/ has the repository two levels up.
    ROOT = HERE.parents[1] if len(HERE.parents) > 1 else HERE

    def test_review_scripts_match_the_live_copies(self) -> None:
        for rel in sorted(VERBATIM):
            live = self.ROOT / rel
            if not live.exists():
                self.skipTest("no live copy next to the kit")
            self.assertEqual((HERE / "kit" / rel).read_text(), live.read_text(), f"{rel} differs from the kit (the master copy): copy the kit's version into the repository, or bring the repository's improvement back into kit/")

    def test_workflow_matches_the_live_copy_outside_the_project_block(self) -> None:
        live = self.ROOT / ".claude/workflows/review-loop.js"
        if not live.exists():
            self.skipTest("no live workflow next to the kit")

        def without_project(text: str) -> str:
            start = text.index("// ---------------------------------------------------------------- Project configuration")
            return text[:start] + text[text.index("\nconst QUOTA = {"):]

        self.assertEqual(
            without_project((HERE / "kit/claude/workflows/review-loop.js").read_text()),
            without_project(live.read_text()),
            "review-loop.js differs from the kit (the master copy) outside the PROJECT block: copy the kit's version in and keep the project's PROJECT block, or bring the improvement back into kit/",
        )


if __name__ == "__main__":
    unittest.main(verbosity=1)
