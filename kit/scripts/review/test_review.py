"""Tests for the review bookkeeping script: `python3 -m unittest discover scripts/review`."""
import argparse
import io
import re
import shutil
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lenses as lens_profile  # noqa: E402
import review  # noqa: E402
import ai_evals  # noqa: E402
import handover  # noqa: E402
import spec_rules  # noqa: E402


class GlobTest(unittest.TestCase):
    def test_single_star_stays_in_segment(self):
        self.assertTrue(review.matches("web/src/features/session.ts", ["web/src/features/*.ts"]))
        self.assertFalse(review.matches("web/src/features/time/x.ts", ["web/src/features/*.ts"]))

    def test_double_star_crosses_segments(self):
        self.assertTrue(review.matches("api/internal/auth/a/b.go", ["api/internal/auth/**"]))
        self.assertTrue(review.matches("web/node_modules/x/y.js", ["**/node_modules/**"]))
        self.assertTrue(review.matches("x.png", ["**/*.png"]))

    def test_literal_characters_are_escaped(self):
        self.assertFalse(review.matches("apiXcoverage", ["api.coverage"]))


class UnitTest(unittest.TestCase):
    def test_every_unit_lens_is_known(self):
        for u in review.UNITS["units"]:
            self.assertTrue(set(u["lenses"]) <= set(review.UNITS["lenses"]), u["id"])

    def test_context_only_for_lenses_the_unit_uses(self):
        for u in review.UNITS["units"]:
            self.assertTrue(set(u.get("context") or {}) <= set(u["lenses"]), u["id"])

    def test_every_lens_has_its_checklist_installed(self):
        for lens, path in review.UNITS["lenses"].items():
            self.assertEqual(lens_profile.CATALOGUE.get(lens), path, lens)
            self.assertTrue((review.ROOT / path).exists(), f"{lens}: {path} missing")

    def test_unit_ids_unique(self):
        ids = [u["id"] for u in review.UNITS["units"]]
        self.assertEqual(len(ids), len(set(ids)))

    # Synthetic units, so these tests don't depend on this repository's layout (the script and its
    # tests are copied verbatim into other repositories; see .agents/bootstrap/BOOTSTRAP.md).
    SAMPLE_UNITS = [
        {"id": "core", "include": ["src/core/**"], "exclude": ["src/core/jobs/**"], "lenses": ["tests"]},
        {"id": "jobs", "include": ["src/core/jobs/**"], "lenses": ["tests"]},
        {"id": "infra", "include": ["deploy/**", ".gitlab-ci.yml", ".jscpd.json"], "lenses": ["security"]},
    ]

    def test_unit_of_respects_excludes(self):
        with mock.patch.dict(review.UNITS, {"units": self.SAMPLE_UNITS}):
            self.assertEqual(review.unit_of("src/core/service.go"), "core")
            self.assertEqual(review.unit_of("src/core/jobs/recurring.go"), "jobs")
            self.assertIsNone(review.unit_of("docs/SPEC.md"))

    def test_unit_of_keeps_leading_dots_of_dotfiles(self):
        # lstrip("./") would turn ".gitlab-ci.yml" into "gitlab-ci.yml" and miss the unit.
        with mock.patch.dict(review.UNITS, {"units": self.SAMPLE_UNITS}):
            self.assertEqual(review.unit_of("deploy/Caddyfile"), "infra")
            self.assertEqual(review.unit_of(".gitlab-ci.yml"), "infra")
            self.assertEqual(review.unit_of(".jscpd.json:3"), "infra")
            self.assertEqual(review.unit_of("./.gitlab-ci.yml"), "infra")
            self.assertEqual(review.unit_of("./deploy/Caddyfile:1"), "infra")

    def test_no_file_in_two_units(self):
        files = review.repo_files()
        for f in files:
            owners = [u["id"] for u in review.UNITS["units"] if f in review.unit_files(u, [f])]
            self.assertLessEqual(len(owners), 1, f"{f} in {owners}")

    def test_repo_fully_covered(self):
        self.assertEqual(review.uncovered(review.repo_files()), [])


class StateTest(unittest.TestCase):
    PATHS = ("STATE", "HISTORY", "USAGE", "LEDGER", "RUN", "INDEX", "TREES")

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = {k: getattr(review, k) for k in self.PATHS}
        review.STATE = self.tmp
        review.HISTORY, review.USAGE = self.tmp / "history.jsonl", self.tmp / "statusline.json"
        review.LEDGER, review.RUN, review.INDEX = self.tmp / "ledger.json", self.tmp / "run.json", self.tmp / "snapshot.index"
        review.TREES = self.tmp / "trees.json"

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(review, k, v)

    def write_history(self, *rows):
        review.HISTORY.write_text("".join(__import__("json").dumps(r) + "\n" for r in rows))

    def test_latest_outcome_wins(self):
        a = {"unit": "u", "file": "f", "title": "A", "status": "open"}
        b = {"unit": "u", "file": "f", "title": "B", "status": "open"}
        self.write_history(a, b, {**a, "status": "fixed"})
        self.assertEqual([h["title"] for h in review.latest_open()], ["B"])

    def test_status_counts_use_the_same_latest_outcome_rule(self):
        a = {"unit": "u", "file": "f", "title": "A", "status": "open"}
        b = {"unit": "u", "file": "f", "title": "B", "status": "open"}
        self.write_history(a, b, {**a, "status": "fixed"}, {**b, "status": "rejected"}, {**b, "status": "open"})
        self.assertEqual({k: v["status"] for k, v in review.latest_outcomes().items()},
                         {("u", "f", "A"): "fixed", ("u", "f", "B"): "open"})
        out = io.StringIO()
        with redirect_stdout(out):
            review.cmd_status(argparse.Namespace())
        self.assertIn("{'fixed': 1, 'rejected': 0, 'open': 1, 'question': 0, 'answered': 0}", out.getvalue())
        self.assertEqual([h["title"] for h in review.latest_open()], ["B"])

    def test_quota_unknown_never_blocks(self):
        self.assertEqual(review.quota(80)["ok"], True)
        self.assertEqual(review.quota(80)["known"], False)

    def test_quota_threshold(self):
        import json, time
        snap = {"captured_at": int(time.time()), "rate_limits": {"seven_day": {"used_percentage": 80}}}
        review.USAGE.write_text(json.dumps(snap))
        self.assertFalse(review.quota(80)["ok"])
        self.assertTrue(review.quota(81)["ok"])
        self.assertEqual(review.quota(80)["week"], 80)

    def test_quota_malformed_snapshot_never_blocks(self):
        for body in ("", '{"captured_', "[]", '{"captured_at": "x"}', '{"rate_limits": []}'):
            review.USAGE.write_text(body)
            q = review.quota(80)
            self.assertEqual((q["ok"], q["known"]), (True, False), body)
        review.USAGE.write_text('{"captured_at": null, "rate_limits": {"seven_day": {"used_percentage": 90}}}')
        self.assertEqual((review.quota(80)["ok"], review.quota(80)["week"]), (False, 90))
        review.USAGE.write_text('{"rate_limits": {"seven_day": {"used_percentage": "90"}}}')
        self.assertEqual((review.quota(80)["ok"], review.quota(80)["known"]), (True, False))

    def test_quota_five_hour_limit_only_when_asked(self):
        import json, time
        snap = {"captured_at": int(time.time()),
                "rate_limits": {"seven_day": {"used_percentage": 10}, "five_hour": {"used_percentage": 95}}}
        review.USAGE.write_text(json.dumps(snap))
        self.assertTrue(review.quota(80)["ok"])
        self.assertFalse(review.quota(80, 90)["ok"])
        self.assertTrue(review.quota(80, 96)["ok"])
        self.assertEqual(review.quota(80, 90)["five_hour"], 95)
        snap["rate_limits"] = {"seven_day": {"used_percentage": 10}}  # no 5-hour figure: never blocks
        review.USAGE.write_text(json.dumps(snap))
        self.assertTrue(review.quota(80, 1)["ok"])

    def test_show_lists_open_and_rejected_and_only_recent_fixed(self):
        unit = {"id": "u", "include": ["src/**"], "lenses": ["tests"]}
        rows = [{"unit": "u", "file": "src/a", "title": f"fixed {i}", "status": "fixed"} for i in range(25)]
        rows += [{"unit": "u", "file": "src/a", "title": "kept out", "status": "rejected", "reason": "by design"},
                 {"unit": "u", "file": "src/a", "title": "pending", "status": "open"},
                 {"unit": "u", "file": "src/a", "title": "fixed 0", "status": "open"},  # reopened: latest wins
                 {"unit": "other", "file": "elsewhere", "title": "not ours", "status": "open"}]
        self.write_history(*rows)
        out = io.StringIO()
        with mock.patch.dict(review.UNITS, {"units": [unit]}), \
                mock.patch.object(review, "repo_files", return_value=[]), redirect_stdout(out):
            review.cmd_show(argparse.Namespace(unit="u"))
        text = out.getvalue()
        self.assertIn("kept out — by design", text)
        self.assertIn("[open] (None) src/a: pending", text)
        self.assertIn("[open] (None) src/a: fixed 0", text)
        self.assertIn("(4 older fixed findings not listed)", text)  # 24 fixed, 20 shown
        self.assertNotIn("fixed 4\n", text)
        self.assertIn("fixed 5\n", text)
        self.assertNotIn("not ours", text)

    def test_questions_are_listed_answered_and_never_carried_to_the_fixer(self):
        import json
        src = self.tmp / "outcomes.json"
        q = {"unit": "u", "lens": "behaviour", "severity": "medium", "file": "src/a", "line": 4, "title": "lockout limit?",
             "status": "question", "scenario": "spec is silent", "fix": "keep 5", "options": ["5", "10"]}
        src.write_text(json.dumps([q, {**q, "title": "rounding?"}]))
        with redirect_stdout(io.StringIO()):
            review.cmd_record(argparse.Namespace(file=str(src)))
        self.assertEqual([r["title"] for r in review.open_questions()], ["lockout limit?", "rounding?"])
        self.assertEqual(review.carried(), [])
        out = io.StringIO()
        with redirect_stdout(out):
            review.cmd_questions(argparse.Namespace())
        self.assertIn("1. [u] lockout limit? (src/a:4)", out.getvalue())
        self.assertIn("- option: 10", out.getvalue())
        with redirect_stdout(io.StringIO()):
            review.cmd_answer(argparse.Namespace(n=2, reason="half-up; SPEC 3.2, DECISIONS 2026-11-05"))
        self.assertEqual([r["title"] for r in review.open_questions()], ["lockout limit?"])
        answered = review.latest_outcomes()[("u", "src/a", "rounding?")]
        self.assertEqual((answered["status"], answered["options"]), ("answered", ["5", "10"]))
        with self.assertRaises(SystemExit):
            review.cmd_answer(argparse.Namespace(n=5, reason="x"))
        with self.assertRaises(SystemExit):
            review.cmd_answer(argparse.Namespace(n=1, reason="  "))

    def test_record_rejects_unknown_status(self):
        import json
        src = self.tmp / "outcomes.json"
        src.write_text(json.dumps([{"unit": "u", "file": "f", "title": "T", "status": "maybe"}]))
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()):
            review.cmd_record(argparse.Namespace(file=str(src)))

    def test_carried_only_actionable_rows_and_confirmed_flag(self):
        base = {"unit": "u", "lens": "tests", "severity": "low", "file": "f", "line": 3, "status": "open",
                "scenario": "s", "fix": "x", "reason": "r", "run": 1}
        self.write_history(
            {**base, "title": "deferred", "confirmed": True},
            {**base, "title": "unverified", "confirmed": False},
            {**base, "title": "legacy"},  # written before the flag existed
            {**base, "title": "no scenario", "scenario": None, "confirmed": True},
        )
        rows = {r["title"]: r for r in review.carried()}
        self.assertEqual(set(rows), {"deferred", "unverified", "legacy"})
        self.assertEqual({t: r["confirmed"] for t, r in rows.items()},
                         {"deferred": True, "unverified": False, "legacy": False})
        self.assertEqual(set(rows["deferred"]), set(review.CARRY_KEYS))
        self.assertNotIn("reason", rows["deferred"])

    def test_record_keeps_confirmed_flag(self):
        import json
        src = self.tmp / "outcomes.json"
        src.write_text(json.dumps([{"unit": "u", "file": "f", "title": "T", "status": "open",
                                    "scenario": "s", "fix": "x", "confirmed": True}]))
        with redirect_stdout(io.StringIO()):
            review.cmd_record(argparse.Namespace(file=str(src)))
        self.assertEqual([r["confirmed"] for r in review.carried()], [True])

    def test_plan_emits_open_and_quota(self):
        import json
        self.write_history({"unit": "u", "lens": "tests", "severity": "low", "file": "f", "line": 1, "title": "T",
                            "status": "open", "scenario": "s", "fix": "x", "confirmed": True, "reason": "r"})
        args = argparse.Namespace(unit=None, lens=None, max_units=1, stop_at=101)
        out = io.StringIO()
        with mock.patch.object(review, "snapshot_tree", return_value="tree"), redirect_stdout(out):
            review.cmd_plan(args)
        plan = json.loads(out.getvalue())
        self.assertEqual(plan["open"], [{"unit": "u", "lens": "tests", "severity": "low", "file": "f", "line": 1,
                                         "title": "T", "scenario": "s", "fix": "x", "confirmed": True}])
        self.assertEqual((plan["quota"]["ok"], plan["quota"]["known"]), (True, False))
        self.assertLessEqual(len(plan["selected"]), 1)
        self.assertEqual(json.loads(review.RUN.read_text())["tree"], "tree")

    def mark(self, no_advance: bool) -> dict:
        import json
        uid = review.UNITS["units"][0]["id"]
        lens = review.UNITS["units"][0]["lenses"][0]
        review.save(review.RUN, {"tree": "t", "hashes": {uid: {lens: "old"}}, "selected": []})
        review.save(review.LEDGER, {uid: {lens: "old"}})
        with mock.patch.object(review, "all_hashes", return_value={uid: {lens: "new"}}), \
                mock.patch.object(review, "repo_files", return_value=[]), \
                mock.patch.object(review, "snapshot_tree", return_value="tree-after"), redirect_stdout(io.StringIO()):
            review.cmd_mark(argparse.Namespace(pairs=[], no_advance=no_advance))
        return json.loads(review.LEDGER.read_text())[uid][lens]

    def test_mark_records_tree_of_fully_current_units(self):
        import json
        u = next(u for u in review.UNITS["units"] if len(u["lenses"]) >= 2)
        review.save(review.RUN, {"tree": "t", "hashes": {}, "selected": []})
        review.save(review.LEDGER, {})
        pairs = [f"{u['id']}:{l}" for l in u["lenses"]]
        with mock.patch.object(review, "all_hashes", return_value={u["id"]: {l: "h" for l in u["lenses"]}}), \
                mock.patch.object(review, "repo_files", return_value=[]), \
                mock.patch.object(review, "snapshot_tree", return_value="T1"), redirect_stdout(io.StringIO()):
            review.cmd_mark(argparse.Namespace(pairs=pairs[:1], no_advance=True))
            self.assertNotIn(u["id"], json.loads(review.TREES.read_text()))  # partially current: no tree
            review.cmd_mark(argparse.Namespace(pairs=pairs, no_advance=True))
        self.assertEqual(json.loads(review.TREES.read_text())[u["id"]], "T1")

    def test_plan_offers_diff_review_only_when_every_pending_lens_was_reviewed(self):
        import json
        u = next(u for u in review.UNITS["units"] if len(u["lenses"]) >= 2)
        review.save(review.TREES, {u["id"]: "T0"})
        args = argparse.Namespace(unit=[u["id"]], lens=None, max_units=1, stop_at=101)

        def plan(ledger):
            review.save(review.LEDGER, ledger)
            out = io.StringIO()
            with mock.patch.object(review, "snapshot_tree", return_value="T1"), \
                    mock.patch.object(review, "tree_exists", return_value=True), \
                    mock.patch.object(review, "changed_files", return_value=[]), redirect_stdout(out):
                review.cmd_plan(args)
            return json.loads(out.getvalue())["selected"][0]

        self.assertEqual(plan({u["id"]: {l: "stale" for l in u["lenses"]}}).get("since"), "T0")
        self.assertNotIn("since", plan({u["id"]: {u["lenses"][0]: "stale"}}))

    def test_mark_advances_pairs_current_at_plan(self):
        self.assertEqual(self.mark(no_advance=False), "new")

    def test_mark_no_advance_keeps_unreviewed_fixer_changes_stale(self):
        self.assertEqual(self.mark(no_advance=True), "old")


class GitRepoCase(unittest.TestCase):
    """A real temporary git repository with one unit `u` (UNIT) under a/."""

    UNIT = {"id": "u", "include": ["a/**"], "lenses": ["tests"]}

    def setUp(self):
        import subprocess
        import tempfile
        self.root = Path(tempfile.mkdtemp())
        self.patches = [
            mock.patch.object(review, "ROOT", self.root),
            mock.patch.object(review, "UNITS", {"lenses": {l: f"{l}.md" for l in self.UNIT["lenses"]},
                                                "globalExclude": ["**/*.png"], "roots": ["a/"], "units": [self.UNIT]}),
            mock.patch.object(review, "INDEX", self.root / ".git" / "review.index"),
        ]
        for p in self.patches:
            p.start()
        self.env = {**review._SNAPSHOT_ID}
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def commit(self, files: dict[str, bytes]) -> str:
        for name, data in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        review._git("add", "-A")
        review._git("-c", "commit.gpgsign=false", "commit", "-q", "-m", "c", env=self.env)
        return review._git("rev-parse", "HEAD^{tree}").decode().strip()

    def working_hash(self) -> str:
        return review.unit_hash(review.unit_files(self.UNIT, review.repo_files()))


class GitBaseTest(GitRepoCase):
    """Review bases against a real temporary git repository: pinning and recovery."""

    def test_hash_at_tree_equals_working_tree_hash(self):
        tree = self.commit({"a/x.txt": b"1\n", "a/y/z.txt": b"\x00bin", "b/other.txt": b"o", "a/logo.png": b"p"})
        self.assertEqual(review.unit_hash_at(self.UNIT, review.tree_entries(tree)), self.working_hash())

    def test_recover_finds_the_commit_with_the_reviewed_content(self):
        reviewed_tree = self.commit({"a/x.txt": b"1"})
        reviewed = self.working_hash()
        self.commit({"a/x.txt": b"2"})
        self.commit({"b/unrelated.txt": b"u"})  # newer commit, same unit content as the one before
        self.assertEqual(review.recover_bases({"u": reviewed}), {"u": reviewed_tree})
        self.assertEqual(review.recover_bases({"u": "0" * 16}), {})  # never reviewed content: no base

    def test_recover_without_commits_finds_nothing(self):
        self.assertEqual(review.recover_bases({"u": "0" * 16}), {})

    def test_pin_keeps_recorded_trees_alive_and_drops_the_rest(self):
        t1 = self.commit({"a/x.txt": b"1"})
        t2 = self.commit({"a/x.txt": b"2"})
        refs = lambda: set(review._git("for-each-ref", "--format=%(refname)", review.TREE_REFS).decode().split())
        review.pin_trees({t1, t2})
        self.assertEqual(refs(), {review.TREE_REFS + t1, review.TREE_REFS + t2})
        review.pin_trees({t2, "f" * 40})  # a tree that doesn't exist is skipped, not an error
        self.assertEqual(refs(), {review.TREE_REFS + t2})
        # A pinned tree survives an aggressive gc even once no branch points at it.
        review._git("update-ref", "-d", "HEAD")
        review._git("reflog", "expire", "--expire=now", "--all")
        review._git("gc", "-q", "--prune=now")
        self.assertTrue(review.tree_exists(t2))

    def test_pin_does_not_sign_even_when_the_developer_signs_commits(self):
        t = self.commit({"a/x.txt": b"1"})
        # A signing setup that always fails: pinning must not try to sign the snapshot commit.
        review._git("config", "commit.gpgsign", "true")
        review._git("config", "gpg.program", "false")
        self.commit({"a/x.txt": b"2"})  # the test helper itself ignores the setting too
        review.pin_trees({t})
        self.assertEqual(review._git("for-each-ref", "--format=%(refname)", review.TREE_REFS).decode().split(), [review.TREE_REFS + t])

    def test_plan_reviews_a_diff_against_a_recovered_base(self):
        import json
        base = self.commit({"a/x.txt": b"1", "a/same.txt": b"s", "a/gone.txt": b"g", "b/other.txt": b"o"})
        reviewed = self.working_hash()
        (self.root / "a" / "x.txt").write_bytes(b"changed")
        (self.root / "a" / "gone.txt").unlink()
        (self.root / "a" / "new.txt").write_bytes(b"n")
        (self.root / "b" / "other.txt").write_bytes(b"outside the unit")
        state = Path(self.root / ".git" / "state")
        state.mkdir()
        with mock.patch.multiple(review, LEDGER=state / "ledger.json", TREES=state / "trees.json",
                                 RUN=state / "run.json", HISTORY=state / "history.jsonl", USAGE=state / "usage.json"):
            review.save(review.LEDGER, {"u": {"tests": reviewed}})
            review.save(review.TREES, {"u": "e" * 40})  # recorded base pruned long ago
            out = io.StringIO()
            with redirect_stdout(out):
                review.cmd_plan(argparse.Namespace(unit=None, lens=None, max_units=4, stop_at=101))
            selected = json.loads(out.getvalue())["selected"]
            self.assertEqual(selected[0]["since"], base)
            # Only the unit's added and changed files: what a diff review must read (a deleted one cannot be).
            self.assertEqual(selected[0]["changed"], ["a/new.txt", "a/x.txt"])
            self.assertEqual(json.loads(review.TREES.read_text()), {"u": base})


class ContextTest(GitRepoCase):
    """Lens context: a contract outside the unit makes only the contracts lens stale."""

    UNIT = {"id": "u", "include": ["a/**"], "lenses": ["tests", "contracts"], "context": {"contracts": ["api/**"]}}

    def test_context_change_restales_only_its_lens(self):
        self.commit({"a/x.txt": b"1", "api/openapi.yaml": b"v1", "b/other.txt": b"o"})
        before = review.all_hashes(review.repo_files())["u"]
        # Without context the lens hash is the unit hash, so older ledgers stay valid.
        self.assertEqual(before["tests"], self.working_hash())
        (self.root / "api" / "openapi.yaml").write_bytes(b"v2")
        (self.root / "b" / "other.txt").write_bytes(b"changed, but neither in the unit nor its context")
        after = review.all_hashes(review.repo_files())["u"]
        self.assertEqual(after["tests"], before["tests"])
        self.assertNotEqual(after["contracts"], before["contracts"])

    def test_diff_scope_includes_context(self):
        base = self.commit({"a/x.txt": b"1", "api/openapi.yaml": b"v1"})
        (self.root / "api" / "openapi.yaml").write_bytes(b"v2")
        now = review.snapshot_tree()
        self.assertEqual(review.changed_files(base, now, self.UNIT), ["api/openapi.yaml"])

    def test_touched_lists_changes_since_plan_within_the_units(self):
        import json
        base = self.commit({"a/x.txt": b"1", "b/other.txt": b"o"})
        state = Path(self.root / ".git" / "state")
        state.mkdir()
        with mock.patch.multiple(review, RUN=state / "run.json"):
            review.save(review.RUN, {"tree": base, "hashes": {}, "selected": []})
            (self.root / "a" / "x.txt").write_bytes(b"written by a reviewer")
            (self.root / "b" / "other.txt").write_bytes(b"another session's work")
            out = io.StringIO()
            with redirect_stdout(out):
                review.cmd_touched(argparse.Namespace(unit=["u"]))
            self.assertEqual(json.loads(out.getvalue()), ["a/x.txt"])
            out = io.StringIO()
            with redirect_stdout(out):
                review.cmd_touched(argparse.Namespace(unit=None))
            self.assertEqual(json.loads(out.getvalue()), ["a/x.txt", "b/other.txt"])


class ProfileTest(unittest.TestCase):
    """The rules that turn .agents/profile.json into lenses (scripts/review/lenses.py)."""

    BASE = {"product": "x", "kinds": ["web-app"], "languages": ["en"], "interfaces": [], "performance": "normal",
            "overrides": {"add": {}, "remove": {}}}

    def lenses(self, **changes):
        return {l for l, on, _ in lens_profile.decide({**self.BASE, **changes}) if on}

    def test_core_lenses_always_on(self):
        core = {"security", "behaviour", "tests", "architecture", "duplication", "supply-chain"}
        self.assertTrue(core <= self.lenses(kinds=["cli"], performance="minor"))

    def test_localisation_needs_a_user_interface_and_several_languages(self):
        self.assertNotIn("localisation", self.lenses())
        self.assertIn("localisation", self.lenses(languages=["en", "de"]))
        self.assertIn("localisation", self.lenses(kinds=["internal-tool"], languages=["en", "sv"]))
        self.assertNotIn("localisation", self.lenses(kinds=["public-api", "library"], languages=["en", "de"]))

    def test_contracts_need_an_interface(self):
        self.assertNotIn("contracts", self.lenses(kinds=["static-site"]))
        self.assertIn("contracts", self.lenses(kinds=["mobile-app"], interfaces=["mobile-backend"]))
        self.assertIn("contracts", self.lenses(kinds=["library"], interfaces=["published-library"]))

    def test_ai_lens_needs_a_mode_and_eval_locations(self):
        self.assertNotIn("ai", self.lenses())
        evals = {"prompts": ["prompts/**"], "evals": "evals/{name}"}
        self.assertIn("ai", self.lenses(ai=["rag", "agentic"], aiEvals=evals))
        for bad in ({"ai": ["chatbot"], "aiEvals": evals}, {"ai": ["rag"]}, {"ai": [], "aiEvals": evals},
                    {"ai": ["rag"], "aiEvals": {"prompts": ["p/**"], "evals": "evals/"}}, {"ai": "rag"}):
            with self.assertRaises(lens_profile.ProfileError, msg=repr(bad)):
                self.lenses(**bad)

    def test_performance_off_only_when_minor(self):
        self.assertIn("performance", self.lenses(performance="critical"))
        self.assertNotIn("performance", self.lenses(performance="minor"))

    def test_overrides_win_and_need_a_reason(self):
        on = self.lenses(overrides={"add": {"localisation": "launching in Germany next quarter"},
                                    "remove": {"duplication": "generated SDK only"}})
        self.assertIn("localisation", on)
        self.assertNotIn("duplication", on)
        with self.assertRaises(lens_profile.ProfileError):
            self.lenses(overrides={"add": {"localisation": ""}})
        with self.assertRaises(lens_profile.ProfileError):
            self.lenses(overrides={"add": {"speed": "typo"}})

    def test_invalid_values_are_reported_together(self):
        with self.assertRaises(lens_profile.ProfileError) as e:
            lens_profile.decide({**self.BASE, "kinds": ["webapp"], "interfaces": ["rest"], "performance": "fast"})
        for word in ("webapp", "rest", "performance"):
            self.assertIn(word, str(e.exception))

    def test_spec_rules_config_is_validated_with_the_profile(self):
        self.lenses(specRules=None)
        self.lenses(specRules={"tests": ["**/*_test.go"], "exempt": {"R-1": "manual"}})
        for bad in ({}, {"tests": []}, {"tests": ["x"], "pattern": "("}, {"tests": ["x"], "exempt": {"R-1": ""}}, "yes"):
            with self.assertRaises(lens_profile.ProfileError, msg=repr(bad)):
                self.lenses(specRules=bad)

    def test_apply_keeps_units_and_drops_disabled_lenses(self):
        units = {"lenses": dict(lens_profile.CATALOGUE), "globalExclude": [], "roots": [], "units": [
            {"id": "web", "include": ["web/**"], "lenses": ["security", "localisation", "contracts"],
             "context": {"contracts": ["api/**"]}},
        ]}
        new, removed, unused = lens_profile.apply(self.BASE, units)
        self.assertEqual(list(new["lenses"]), ["security", "behaviour", "tests", "architecture", "duplication", "performance", "supply-chain"])
        self.assertEqual(new["units"][0]["lenses"], ["security"])
        self.assertNotIn("context", new["units"][0])
        self.assertEqual(removed, {"web": ["localisation", "contracts"]})
        self.assertEqual(unused, ["behaviour", "tests", "architecture", "duplication", "performance", "supply-chain"])
        self.assertEqual(units["units"][0]["lenses"], ["security", "localisation", "contracts"])  # input untouched

    def test_units_follow_the_profile(self):
        """In a configured repository, units.json must match .agents/profile.json."""
        if not lens_profile.PROFILE.exists():
            self.skipTest("no .agents/profile.json")
        profile = lens_profile.load_profile()
        if not lens_profile.is_filled(profile):
            self.skipTest(".agents/profile.json is still the template")
        self.assertEqual(lens_profile.check(profile, review.UNITS), [])


class SpecRulesTest(unittest.TestCase):
    """Every spec rule pinned by a test (scripts/review/spec_rules.py)."""

    def setUp(self):
        import tempfile
        self.root = Path(tempfile.mkdtemp())

    def write(self, files: dict[str, str]) -> list[str]:
        for name, text in files.items():
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_text(text)
        return sorted(files)

    def report(self, files, **cfg):
        return spec_rules.report(spec_rules.config({"specRules": {"tests": ["tests/**"], **cfg}}), self.root, files)

    def test_whole_ids_only(self):
        rx = spec_rules.id_regex(spec_rules.DEFAULTS["pattern"])
        self.assertEqual(spec_rules.ids_in("**R-3.2.1** and R-3.2, (R-10).", rx), {"R-3.2.1", "R-3.2", "R-10"})
        self.assertEqual(spec_rules.ids_in("XR-1 R-1a R-1-b PR-2 version 1.R-3", rx), set())
        self.assertEqual(spec_rules.ids_in("ends a sentence: R-4.", rx), {"R-4"})

    def test_untested_unknown_and_stale_exempt(self):
        files = self.write({
            "docs/SPEC.md": "**R-1** Invoices are numbered.\n**R-2** Totals round half-up.\n**R-2.1** Per line.\n**R-3** Support replies within a day.\n",
            "tests/invoice_test.go": "// pins R-1\nfunc TestRounding_R_2() {} // R-2\n",
            "tests/old_test.go": "// R-9 was removed from the spec\n",
            "src/main.go": "// R-2.1 mentioned in code, not in a test\n",
        })
        rep = self.report(files, exempt={"R-3": "a support promise", "R-7": "gone"})
        self.assertEqual(rep["rules"], 4)
        self.assertEqual(rep["untested"], ["R-2.1"])  # R-2 does not pin R-2.1; code is not a test
        self.assertEqual(rep["unknown"], {"R-9": ["tests/old_test.go"]})
        self.assertEqual(rep["staleExempt"], ["R-7"])
        self.assertEqual(len(spec_rules.problems(rep)), 3)

    def test_clean_report_and_missing_spec(self):
        files = self.write({"docs/SPEC.md": "R-1 x\n", "tests/a.test.ts": "it('R-1', ...)\n"})
        self.assertEqual(spec_rules.problems(self.report(files)), [])
        self.assertIn("not found", spec_rules.problems(self.report(files, spec="docs/NOPE.md"))[0])

    def test_spec_rules_are_pinned(self):
        """The gate check, when the profile switches it on."""
        if not lens_profile.PROFILE.exists():
            self.skipTest("no .agents/profile.json")
        profile = lens_profile.load_profile()
        cfg = spec_rules.config(profile) if lens_profile.is_filled(profile) else None
        if cfg is None:
            self.skipTest("specRules is off")
        self.assertEqual(spec_rules.problems(spec_rules.report(cfg, review.ROOT, review.repo_files())), [])


class AiEvalsTest(unittest.TestCase):
    """Every prompt has its eval set and facets (scripts/review/ai_evals.py)."""

    CFG = {"prompts": ["prompts/**"], "evals": "evals/{name}",
           "facets": {"prompts/search/**": ai_evals.FACETS["rag"], "prompts/agents/**": ai_evals.FACETS["agentic"]}}

    def test_missing_sets_facets_and_duplicates(self):
        files = [
            "prompts/search/answer.md", "evals/answer/query.yaml", "evals/answer/retrieval/cases.jsonl",
            "evals/answer/answers.yaml",  # not the `answer` facet: a facet is a whole name
            "prompts/agents/book.md",
            "prompts/draft-email.txt", "evals/draft-email.yaml",
            "prompts/a/summary.md", "prompts/b/summary.md", "evals/summary/output.yaml",
        ]
        rep = ai_evals.report(self.CFG, files)
        self.assertEqual(rep["prompts"], 4)
        self.assertEqual(rep["missing"], {
            "answer": ["evals/answer/answer"],
            "book": ["evals/book", "evals/book/safety", "evals/book/task", "evals/book/trajectory"],
        })
        self.assertEqual(rep["duplicates"], {"summary": ["prompts/a/summary.md", "prompts/b/summary.md"]})
        self.assertEqual(len(ai_evals.problems(rep)), 3)

    def test_complete(self):
        files = ["prompts/search/q.md", "evals/q/query.yaml", "evals/q/retrieval.yaml", "evals/q/answer/x.jsonl"]
        self.assertEqual(ai_evals.problems(ai_evals.report(self.CFG, files)), [])

    def test_every_prompt_has_its_evals(self):
        """The gate check, when the profile lists an AI mode."""
        if not lens_profile.PROFILE.exists():
            self.skipTest("no .agents/profile.json")
        profile = lens_profile.load_profile()
        if not (lens_profile.is_filled(profile) and profile.get("ai")):
            self.skipTest("the profile lists no AI mode")
        rep = ai_evals.report(profile["aiEvals"], review.repo_files())
        self.assertEqual(ai_evals.problems(rep), [])


class HandoverTest(unittest.TestCase):
    """Size budgets for the files every session reads (scripts/review/handover.py)."""

    def setUp(self):
        import tempfile
        self.root = Path(tempfile.mkdtemp())
        (self.root / ".agents").mkdir()
        (self.root / "docs").mkdir()

    def test_over_budget_by_lines_and_by_decision_entries(self):
        (self.root / ".agents/STATUS.md").write_text("x\n" * 151)
        (self.root / "CLAUDE.md").write_text("x\n" * 10)
        entries = "".join(f"## 2026-01-{d:02d}: decision {d}\n- **Area:** a\n\n" for d in range(1, 29)) * 4
        (self.root / "docs/DECISIONS.md").write_text("# Decisions\n\n<!-- ## <YYYY-MM-DD>: format -->\n" + entries)
        self.assertEqual(handover.over_budget_lines(self.root, {}), [
            ".agents/STATUS.md: 151 lines (budget 150)",
            "docs/DECISIONS.md: 112 entries (budget 100)",
        ])
        # A project can change a budget; files that don't exist are not reported.
        self.assertEqual(handover.over_budget_lines(self.root, {"handoverBudgets": {
            ".agents/STATUS.md": {"lines": 200}, "docs/DECISIONS.md": {"entries": 200}}}), [])

    def test_handover_files_within_budget(self):
        """The gate's soft guard: warns, never fails."""
        import warnings
        for line in handover.over_budget_lines(review.ROOT, review.UNITS):
            warnings.warn(f"handover file over budget: {line} (see .agents/WORKING.md)", stacklevel=1)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class RealSkipsTest(unittest.TestCase):
    """The workflow's skip filter (review-loop.js realSkips), run with node on its own source."""

    def real_skips(self, skipped, changed, since="t"):
        import json
        src = (Path(review.ROOT) / ".claude" / "workflows" / "review-loop.js").read_text()
        m = re.search(r"^const realSkips = \(r\) => \{\n.*?^\}\n", src, re.S | re.M)
        self.assertIsNotNone(m, "realSkips not found in review-loop.js")
        r = {"rev": {"skipped": skipped}, "sel": {"since": since, "changed": changed}}
        script = f"{m.group(0)}\nprocess.stdout.write(JSON.stringify(realSkips({json.dumps(r)})))"
        out = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True).stdout
        return json.loads(out)

    def test_a_skip_naming_a_changed_file_in_free_text_counts(self):
        changed = ["api/internal/foo/service.go", "web/src/x.ts"]
        skipped = [
            "api/internal/foo/service.go: read lines 1-2000 only",
            "partially read api/internal/foo/service.go",
            "api/internal/foo/service.go",
            "`web/src/x.ts` (too long).",
            "/workspace/api/internal/foo/service.go (truncated)",
        ]
        self.assertEqual(self.real_skips(skipped, changed), skipped)

    def test_a_skip_naming_only_unchanged_files_does_not_count(self):
        changed = ["web/src/x.ts", "a/b.go"]
        skipped = ["web/src/x.tsx (unchanged)", "web/src/x.ts.snap", "a/b.go_test (unchanged)", "other/c.go"]
        self.assertEqual(self.real_skips(skipped, changed), [])

    def test_a_full_review_counts_every_skip(self):
        self.assertEqual(self.real_skips(["anything"], ["a/x.go"], since=None), ["anything"])


if __name__ == "__main__":
    unittest.main()
