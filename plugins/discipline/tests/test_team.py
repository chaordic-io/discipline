"""Several people on several branches: per-branch work files, one file per decision, append-only review
state merged by git's union driver, and the gate checks that keep it all consistent. The merge tests use
real git repositories and real merges."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "src"))
from discipline import decisions, init  # noqa: E402

DISCIPLINE = str(PLUGIN / "bin" / "discipline")
PROFILE = {"product": "Invoicing", "kinds": ["backend-service"], "languages": ["en"], "interfaces": [],
           "performance": "minor", "data": "tenant data", "overrides": {"add": {}, "remove": {}}}


class Repo:
    """A set-up repository on `main`, with one unit `core` (src/**) and the lenses the profile selects."""

    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.invalid")
        self.git("config", "user.name", "t")
        self.git("config", "commit.gpgsign", "false")
        init.install(self.root)
        profile = json.loads((self.root / ".agents/profile.json").read_text())
        profile.update(PROFILE)
        self.write(".agents/profile.json", json.dumps(profile))
        assert self.run("lenses", "apply").returncode == 0
        units = json.loads((self.root / ".claude/review/units.json").read_text())
        units.update({"roots": ["src/"], "units": [{"id": "core", "include": ["src/**"], "lenses": list(units["lenses"])}]})
        self.write(".claude/review/units.json", json.dumps(units))
        self.write("src/a.py", "a = 1\n")
        self.write("src/b.py", "b = 1\n")
        self.commit("set up")

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True, text=True).stdout

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, msg: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)

    def run(self, *args: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        return subprocess.run([DISCIPLINE, *args], cwd=self.root, capture_output=True, text=True, env=env)

    def review_everything(self) -> None:
        """What the review loop's plan and record steps do, for every pending pair."""
        plan = json.loads(self.run("review", "plan", "--max-units", "10").stdout)
        pairs = [f"{s['unit']}:{l}" for s in plan["selected"] for l in s["lenses"]]
        out = self.root / "o.json"
        out.write_text(json.dumps([{"unit": "core", "lens": "tests", "file": "src/a.py", "title": f"finding on {self.git('branch', '--show-current').strip()}",
                                    "status": "fixed"}]))
        assert self.run("review", "record", str(out)).returncode == 0
        out.unlink()
        r = self.run("review", "mark", *pairs)
        assert r.returncode == 0, r.stderr

    def status_row(self) -> list[str]:
        out = self.run("review", "status").stdout
        return next(l for l in out.splitlines() if l.startswith("core")).split()[1:]

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


class MergeTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()

    def tearDown(self):
        self.repo.close()

    def test_two_branches_review_merge_without_conflicts_and_keep_both_reviews(self):
        r = self.repo
        r.git("checkout", "-q", "-b", "feature/a")
        r.write("src/a.py", "a = 2\n")
        r.review_everything()
        r.commit("a")
        r.git("checkout", "-q", "main")
        r.git("checkout", "-q", "-b", "feature/b")
        r.write("src/b.py", "b = 2\n")
        r.review_everything()
        r.commit("b")
        self.assertTrue(all(s == "ok" for s in r.status_row()))

        r.git("checkout", "-q", "main")
        r.git("merge", "-q", "--no-edit", "feature/a")
        self.assertTrue(all(s == "ok" for s in r.status_row()), "a fast-forward keeps branch a's review")
        merged = subprocess.run(["git", "merge", "--no-edit", "feature/b"], cwd=r.root, capture_output=True, text=True)
        self.assertEqual(merged.returncode, 0, merged.stdout + merged.stderr)  # no conflict in the review state
        self.assertNotIn("<<<<<<<", (r.root / ".claude/review/ledger.jsonl").read_text())

        # Both branches' rows survive, and both findings are in the history.
        titles = {json.loads(l)["title"] for l in (r.root / ".claude/review/history.jsonl").read_text().splitlines()}
        self.assertEqual(titles, {"finding on feature/a", "finding on feature/b"})
        # The merged content (a = 2 and b = 2 together) was reviewed on neither branch: due again, as a diff.
        self.assertTrue(all(s == "stale" for s in r.status_row()))
        plan = json.loads(r.run("review", "plan").stdout)
        self.assertIn("since", plan["selected"][0])
        self.assertEqual(r.run("check").returncode, 0, r.run("check").stdout)

    def test_decisions_from_two_branches_merge_and_the_index_is_regenerated(self):
        r = self.repo
        r.git("checkout", "-q", "-b", "x")
        self.assertEqual(r.run("decisions", "new", "Per-org numbering").returncode, 0)
        r.commit("x")
        r.git("checkout", "-q", "main")
        r.git("checkout", "-q", "-b", "y")
        self.assertEqual(r.run("decisions", "new", "Half-up rounding").returncode, 0)
        r.commit("y")
        r.git("checkout", "-q", "main")
        r.git("merge", "-q", "--no-edit", "x")
        merged = subprocess.run(["git", "merge", "--no-edit", "y"], cwd=r.root, capture_output=True, text=True)
        self.assertEqual(merged.returncode, 0, merged.stdout + merged.stderr)
        self.assertEqual(len(list((r.root / "docs/decisions").glob("20*.md"))), 2)
        # The union-merged index has both rows; if they aren't in generated order, the gate says regenerate.
        check = r.run("check")
        if check.returncode != 0:
            self.assertIn("discipline decisions index", check.stdout)
        r.run("decisions", "index")
        index = (r.root / "docs/DECISIONS.md").read_text()
        self.assertIn("Per-org numbering", index)
        self.assertIn("Half-up rounding", index)
        self.assertEqual(r.run("decisions", "check").returncode, 0)

    def test_history_entries_from_two_branches_are_both_kept(self):
        r = self.repo
        base = (r.root / ".agents/HISTORY.md").read_text()
        r.git("checkout", "-q", "-b", "x")
        r.write(".agents/HISTORY.md", base + "- **2026-11-05, branch x.** Numbering.\n")
        r.commit("x")
        r.git("checkout", "-q", "main")
        r.git("checkout", "-q", "-b", "y")
        r.write(".agents/HISTORY.md", base + "- **2026-11-05, branch y.** Rounding.\n")
        r.commit("y")
        r.git("checkout", "-q", "main")
        r.git("merge", "-q", "--no-edit", "x")
        merged = subprocess.run(["git", "merge", "--no-edit", "y"], cwd=r.root, capture_output=True, text=True)
        self.assertEqual(merged.returncode, 0, merged.stdout + merged.stderr)
        history = (r.root / ".agents/HISTORY.md").read_text()
        self.assertIn("branch x", history)
        self.assertIn("branch y", history)


class WorkFileTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()

    def tearDown(self):
        self.repo.close()

    def test_each_branch_gets_its_own_work_file(self):
        r = self.repo
        r.git("checkout", "-q", "-b", "feature/numbering")
        out = r.run("work")
        self.assertEqual(out.stdout.strip(), "created .agents/work/feature--numbering.md")
        self.assertIn("# Work on `feature/numbering`", (r.root / ".agents/work/feature--numbering.md").read_text())
        self.assertEqual(r.run("work").stdout.strip(), ".agents/work/feature--numbering.md")  # not recreated

    def test_list_shows_every_branch_in_flight_from_its_own_work_file(self):
        """Nobody edits a shared list: each branch's header is read from git, even from another branch."""
        r = self.repo
        for branch, who in (("feature/a", "Ann"), ("feature/b", "Bob")):
            r.git("checkout", "-q", "main")
            r.git("checkout", "-q", "-b", branch)
            r.run("work")
            path = r.root / ".agents/work" / f"{branch.replace('/', '--')}.md"
            path.write_text(path.read_text().replace("- **Who:** <!--", f"- **Who:** {who} <!--")
                            .replace("- **Owns:** <!--", f"- **Owns:** src/{who.lower()}/ <!--"))
            r.commit(f"start {branch}")
        listed = r.run("work", "--list").stdout  # run on feature/b: feature/a's file isn't in this checkout
        self.assertIn("| feature/a | Ann | ? | src/ann/ |", listed)
        self.assertIn("| feature/b | Bob | ? | src/bob/ |", listed)

    def test_on_the_default_branch_leftover_work_files_are_a_warning(self):
        r = self.repo
        r.git("checkout", "-q", "-b", "feature/x")
        r.run("work")
        r.commit("work on x")
        r.git("checkout", "-q", "main")
        r.git("merge", "-q", "--no-edit", "feature/x")
        out = json.loads(r.run("check", "--json").stdout)
        self.assertEqual(out["problems"], [])
        self.assertTrue(any("feature--x.md" in w for w in out["warnings"]), out["warnings"])
        r.git("checkout", "-q", "feature/x")
        out = json.loads(r.run("check", "--json").stdout)
        self.assertFalse(any("work files" in w for w in out["warnings"]), "no warning on the branch itself")

    def test_detached_head_has_no_work_file(self):
        r = self.repo
        r.git("checkout", "-q", "--detach")
        self.assertEqual(r.run("work").returncode, 2)


class DecisionsTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_new_files_are_unique_and_the_index_is_newest_first(self):
        d = self.dir / "decisions"
        a = decisions.new("Per-org numbering!", today="2026-11-04", directory=d)
        b = decisions.new("Per-org numbering!", today="2026-11-04", directory=d)
        c = decisions.new("Half-up rounding", today="2026-11-05", directory=d)
        self.assertEqual([a.name, b.name, c.name], ["2026-11-04-per-org-numbering.md", "2026-11-04-per-org-numbering-2.md",
                                                    "2026-11-05-half-up-rounding.md"])
        c.write_text(c.read_text().replace("<one or two words from the spec's areas, e.g. invoicing, permissions>", "money")
                     + "- **Superseded by:** 2026-11-06-banker.md\n")
        items = decisions.entries(d)
        self.assertEqual([e.date for e in items], ["2026-11-05", "2026-11-04", "2026-11-04"])
        index = decisions.render(items)
        self.assertIn("| 2026-11-05 | [Half-up rounding](decisions/2026-11-05-half-up-rounding.md) | money | superseded |", index)

    def test_problems_stale_index_badly_named_files_and_missing_area(self):
        d, index = self.dir / "decisions", self.dir / "DECISIONS.md"
        decisions.new("Something", today="2026-11-05", directory=d)
        (d / "notes.md").write_text("# not a decision\n")
        errs, warns = decisions.problems(d, index)
        self.assertEqual(len(errs), 2)
        self.assertIn("out of date", errs[0])
        self.assertIn("notes.md", errs[1])
        self.assertIn("without an Area", warns[0])
        index.write_text(decisions.render(decisions.entries(d)))
        (d / "notes.md").unlink()
        self.assertEqual(decisions.problems(d, index)[0], [])


class AssumptionsAndSearchTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()

    def tearDown(self):
        self.repo.close()

    def test_assumptions_are_listed_and_warned_about_until_confirmed(self):
        r = self.repo
        spec = (r.root / "docs/SPEC.md").read_text()
        r.write("docs/SPEC.md", spec + "\n- Un-voiding is admin-only (assumed 2026-11-05, not confirmed).\n")
        r.write("docs/decisions/2026-11-04-old.md", "# Old\n- **Area:** x\n- quoted: (assumed 2026-11-01, not confirmed)\n")
        r.run("decisions", "index")
        listed = r.run("assumptions").stdout
        self.assertIn("docs/SPEC.md:", listed)
        self.assertIn("1 assumptions not confirmed", listed)  # the decision quoting a marker doesn't count
        out = json.loads(r.run("check", "--json").stdout)
        self.assertEqual(out["problems"], [])
        self.assertTrue(any("1 assumptions not confirmed" in w for w in out["warnings"]), out["warnings"])
        r.write("docs/SPEC.md", spec + "\n- Un-voiding is admin-only.\n")  # confirmed: the marker goes
        out = json.loads(r.run("check", "--json").stdout)
        self.assertFalse(any("assumptions" in w for w in out["warnings"]))

    def test_search_finds_decisions_and_answered_questions_before_anyone_asks_again(self):
        r = self.repo
        r.run("decisions", "new", "Un-voiding is admin-only")
        q = r.root / "q.json"
        q.write_text(json.dumps([{"unit": "core", "lens": "behaviour", "file": "src/a.py", "title": "Rounding of negative lines?",
                                  "status": "question", "scenario": "spec silent", "fix": "half away from zero", "options": ["a", "b"]}]))
        r.run("review", "record", str(q))
        r.run("review", "answer", "1", "--reason", "half away from zero; SPEC 3.1")
        self.assertIn("Un-voiding is admin-only", r.run("decisions", "search", "un-voiding").stdout)
        hits = r.run("decisions", "search", "rounding", "negative").stdout
        self.assertIn("answered review question [core] Rounding of negative lines?: half away from zero", hits)
        self.assertIn("0 found: nothing decided", r.run("decisions", "search", "refunds").stdout)


class EvidenceTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()

    def tearDown(self):
        self.repo.close()

    def test_every_outcome_keeps_its_evidence_and_the_report_shows_it(self):
        r = self.repo
        plan = json.loads(r.run("review", "plan").stdout)
        snapshot = json.loads((r.root / ".claude/review/run.json").read_text())["tree"]
        o = r.root / "o.json"
        o.write_text(json.dumps([
            {"unit": "core", "lens": "security", "severity": "critical", "file": "src/a.py", "line": 1, "title": "SQL injection",
             "status": "fixed", "scenario": "x' OR '1'='1 returns every org", "fix": "parameterise", "verdict": "reproduced"},
            {"unit": "core", "lens": "tests", "severity": "low", "file": "src/b.py", "title": "Taste", "status": "rejected",
             "reason": "a matter of style", "scenario": "s", "verdict": "refuted: style only"},
        ]))
        self.assertEqual(r.run("review", "record", str(o)).returncode, 0)
        r.run("review", "mark", *[f"{s['unit']}:{l}" for s in plan["selected"] for l in s["lenses"]])
        row = json.loads((r.root / ".claude/review/history.jsonl").read_text().splitlines()[0])
        self.assertEqual((row["scenario"], row["verdict"], row["run"]), ("x' OR '1'='1 returns every org", "reproduced", snapshot))
        report = r.run("review", "evidence").stdout
        self.assertIn("## Coverage", report)
        self.assertRegex(report, r"\| core \| ok \d{4}-\d{2}-\d{2}")
        self.assertIn("### Fixed: 1 (1 critical)", report)
        self.assertIn("- Scenario: x' OR '1'='1 returns every org", report)
        self.assertIn("- Verifier: reproduced", report)
        self.assertIn(f"reviewed snapshot `{snapshot[:10]}`", report)
        self.assertIn("### Rejected (with the reason): 1", report)
        self.assertIn("- Reason: a matter of style", report)
        self.assertNotIn("Taste", r.run("review", "evidence", "--since", "2999-01-01").stdout)


class InitTeamTest(unittest.TestCase):
    def test_init_marks_union_merges_and_ignores_personal_preferences(self):
        root = Path(tempfile.mkdtemp())
        try:
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            init.install(root)
            init.install(root)  # idempotent
            attrs = (root / ".gitattributes").read_text()
            for line in init.GITATTRIBUTES:
                self.assertEqual(attrs.count(line), 1, line)
            self.assertTrue((root / ".agents/USER.local.md").exists())
            r = subprocess.run(["git", "check-ignore", ".agents/USER.local.md", ".agents/USER.md"], cwd=root,
                               capture_output=True, text=True)
            self.assertEqual(r.stdout.split(), [".agents/USER.local.md"])
            r = subprocess.run(["git", "check-attr", "merge", ".claude/review/ledger.jsonl"], cwd=root, capture_output=True, text=True)
            self.assertIn("merge: union", r.stdout)
            self.assertEqual((root / "docs/DECISIONS.md").read_text(), decisions.render([]))
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
