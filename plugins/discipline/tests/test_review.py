"""Tests for the review bookkeeping and the lens, spec-rule, AI-eval and handover rules."""
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from discipline import ai_evals, handover, review, spec_rules  # noqa: E402
from discipline import lenses as lens_profile  # noqa: E402

PLUGIN = Path(__file__).resolve().parents[1]


def write_ledger(pairs: dict) -> None:
    """Write {unit: {lens: hash or [hashes]}} as ledger rows."""
    rows = [{"unit": u, "lens": l, "hash": h, "at": i}
            for u, lenses in pairs.items() for l, hs in lenses.items()
            for i, h in enumerate([hs] if isinstance(hs, str) else hs)]
    review.LEDGER.write_text("".join(__import__("json").dumps(r) + "\n" for r in rows))


def write_trees(trees: dict) -> None:
    review.TREES.write_text("".join(__import__("json").dumps({"unit": u, "tree": t, "at": 0}) + "\n" for u, t in trees.items()))

# A fixed sample configuration, so these tests don't depend on any project's units.json.
SAMPLE = {
    "lenses": {"security": "s.md", "tests": "t.md", "architecture": "a.md"},
    "globalExclude": ["**/*.png"],
    "roots": ["src/"],
    "units": [
        {"id": "core", "include": ["src/core/**"], "lenses": ["security", "tests", "architecture"]},
        {"id": "web", "include": ["src/web/**"], "lenses": ["tests"]},
    ],
}


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
    # Synthetic units, so these tests don't depend on any repository's layout.
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



class StateTest(unittest.TestCase):
    PATHS = ("STATE", "HISTORY", "USAGE", "LEDGER", "RUN", "INDEX", "TREES")

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = {k: getattr(review, k) for k in self.PATHS}
        review.STATE = self.tmp
        review.HISTORY, review.USAGE = self.tmp / "history.jsonl", self.tmp / "statusline.json"
        review.LEDGER, review.RUN, review.INDEX = self.tmp / "ledger.jsonl", self.tmp / "run.json", self.tmp / "snapshot.index"
        review.TREES = self.tmp / "trees.jsonl"
        self.units = mock.patch.object(review, "UNITS", SAMPLE)
        self.units.start()

    def tearDown(self):
        self.units.stop()
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

    def test_quota_without_limits_never_blocks(self):
        import json, time
        review.USAGE.write_text(json.dumps({"captured_at": int(time.time()),
                                            "rate_limits": {"seven_day": {"used_percentage": 99}, "five_hour": {"used_percentage": 99}}}))
        self.assertTrue(review.quota()["ok"])
        self.assertEqual(review.quota()["week"], 99)

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
        write_ledger({uid: {lens: "old"}})
        with mock.patch.object(review, "all_hashes", return_value={uid: {lens: "new"}}), \
                mock.patch.object(review, "repo_files", return_value=[]), \
                mock.patch.object(review, "snapshot_tree", return_value="tree-after"), redirect_stdout(io.StringIO()):
            review.cmd_mark(argparse.Namespace(pairs=[], no_advance=no_advance))
        return review.reviewed()[uid][lens][-1]

    def test_mark_records_tree_of_fully_current_units(self):
        import json
        u = next(u for u in review.UNITS["units"] if len(u["lenses"]) >= 2)
        review.save(review.RUN, {"tree": "t", "hashes": {}, "selected": []})
        pairs = [f"{u['id']}:{l}" for l in u["lenses"]]
        with mock.patch.object(review, "all_hashes", return_value={u["id"]: {l: "h" for l in u["lenses"]}}), \
                mock.patch.object(review, "repo_files", return_value=[]), \
                mock.patch.object(review, "snapshot_tree", return_value="T1"), redirect_stdout(io.StringIO()):
            review.cmd_mark(argparse.Namespace(pairs=pairs[:1], no_advance=True))
            self.assertNotIn(u["id"], review.latest_trees())  # partially current: no tree
            review.cmd_mark(argparse.Namespace(pairs=pairs, no_advance=True))
        self.assertEqual(review.latest_trees()[u["id"]], "T1")

    def test_plan_offers_diff_review_only_when_every_pending_lens_was_reviewed(self):
        import json
        u = next(u for u in review.UNITS["units"] if len(u["lenses"]) >= 2)
        write_trees({u["id"]: "T0"})
        args = argparse.Namespace(unit=[u["id"]], lens=None, max_units=1, stop_at=101)

        def plan(ledger):
            write_ledger(ledger)
            out = io.StringIO()
            with mock.patch.object(review, "snapshot_tree", return_value="T1"), \
                    mock.patch.object(review, "tree_exists", return_value=True), \
                    mock.patch.object(review, "changed_files", return_value=[]), redirect_stdout(out):
                review.cmd_plan(args)
            return json.loads(out.getvalue())["selected"][0]

        self.assertEqual(plan({u["id"]: {l: "stale" for l in u["lenses"]}}).get("since"), "T0")
        self.assertNotIn("since", plan({u["id"]: {u["lenses"][0]: "stale"}}))

    def test_requeue_makes_reviewed_pairs_due_again_in_full(self):
        import json
        write_ledger({"core": {"security": "h", "tests": "h"}})
        write_trees({"core": "T0"})
        hashes = {"core": {"security": "h", "tests": "h", "architecture": "h"}, "web": {"tests": "h"}}
        with mock.patch.object(review, "all_hashes", return_value=hashes), \
                mock.patch.object(review, "repo_files", return_value=[]), redirect_stdout(io.StringIO()) as out:
            review.cmd_requeue(argparse.Namespace(lens=["security", "architecture"], unit=None, reason="checklist now covers X"))
        self.assertIn("requeued 1 pairs", out.getvalue())  # architecture was never reviewed: nothing to undo
        ledger = review.reviewed()
        self.assertEqual(ledger["core"], {"security": [], "tests": ["h"]})
        self.assertEqual(review.pair_state("core", "security", "h", ledger, review.baselined()), "stale")
        self.assertEqual(review.pair_state("core", "tests", "h", ledger, review.baselined()), "ok")
        self.assertEqual(review.pair_state("core", "architecture", "h", ledger, review.baselined()), "never")
        out = io.StringIO()
        with mock.patch.object(review, "all_hashes", return_value=hashes), \
                mock.patch.object(review, "repo_files", return_value=[]), \
                mock.patch.object(review, "snapshot_tree", return_value="T1"), \
                mock.patch.object(review, "tree_exists", return_value=True), redirect_stdout(out):
            review.cmd_plan(argparse.Namespace(unit=["core"], lens=["security"], max_units=1, stop_at=101))
        picked = json.loads(out.getvalue())["selected"][0]
        self.assertEqual((picked["lenses"], picked["reason"]), (["security"], "changed"))
        self.assertNotIn("since", picked)  # a requeued pair is reviewed in full, not as a diff
        rows = [json.loads(l) for l in review.LEDGER.read_text().splitlines()]
        rows.append({"unit": "core", "lens": "security", "hash": "h", "at": rows[-1]["at"] + 1})
        review.LEDGER.write_text("".join(json.dumps(r) + "\n" for r in rows))
        self.assertEqual(review.reviewed()["core"]["security"], ["h"])  # reviewed again: current

    def test_requeue_refuses_unknown_lenses_and_units(self):
        for args in ({"lens": ["speed"], "unit": None}, {"lens": ["tests"], "unit": ["nope"]}):
            with self.assertRaises(SystemExit, msg=repr(args)):
                review.cmd_requeue(argparse.Namespace(reason="r", **args))

    def test_branches_merged_by_union_combine_their_reviews(self):
        """Two branches each reviewed the unit at different content; git's union merge concatenates their
        rows in any order. Each content counts as reviewed, and the latest tree wins by time."""
        import json
        branch_a = [{"unit": "core", "lens": "tests", "hash": "A", "at": 200}]
        branch_b = [{"unit": "core", "lens": "tests", "hash": "B", "at": 100}]
        review.LEDGER.write_text("".join(json.dumps(r) + "\n" for r in branch_a + branch_b))
        self.assertEqual(review.reviewed()["core"]["tests"], ["B", "A"])  # time order, not file order
        review.TREES.write_text(json.dumps({"unit": "core", "tree": "TA", "at": 200}) + "\n"
                                + json.dumps({"unit": "core", "tree": "TB", "at": 100}) + "\n")
        self.assertEqual(review.latest_trees(), {"core": "TA"})
        with mock.patch.object(review, "all_hashes", return_value={"core": {"security": "x", "tests": "B", "architecture": "x"},
                                                                     "web": {"tests": "x"}}), \
                mock.patch.object(review, "repo_files", return_value=[]), redirect_stdout(io.StringIO()) as out:
            review.cmd_status(argparse.Namespace())
        core = next(l for l in out.getvalue().splitlines() if l.startswith("core"))
        self.assertEqual(core.split()[1:], ["never", "ok", "never"])

    def test_history_latest_outcome_follows_time_not_file_order(self):
        import json
        later = {"unit": "u", "file": "f", "title": "T", "status": "fixed", "at": 300}
        earlier = {"unit": "u", "file": "f", "title": "T", "status": "open", "at": 100}
        review.HISTORY.write_text(json.dumps(later) + "\n" + json.dumps(earlier) + "\n")  # union merge order
        self.assertEqual(review.latest_outcomes()[("u", "f", "T")]["status"], "fixed")

    def test_record_stamps_rows_in_order(self):
        import json
        src = self.tmp / "o.json"
        src.write_text(json.dumps([{"unit": "u", "file": "f", "title": t, "status": "open"} for t in "ab"]))
        with redirect_stdout(io.StringIO()):
            review.cmd_record(argparse.Namespace(file=str(src)))
        rows = review.history()
        self.assertEqual([r["title"] for r in rows], ["a", "b"])
        self.assertLess(rows[0]["at"], rows[1]["at"])

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

    def test_pin_keeps_recorded_trees_alive_and_never_drops_another_branchs(self):
        t1 = self.commit({"a/x.txt": b"1"})
        t2 = self.commit({"a/x.txt": b"2"})
        refs = lambda: set(review._git("for-each-ref", "--format=%(refname)", review.TREE_REFS).decode().split())
        review.pin_trees({t1, t2})
        self.assertEqual(refs(), {review.TREE_REFS + t1, review.TREE_REFS + t2})
        review.pin_trees({t2, "f" * 40})  # a tree that doesn't exist is skipped, not an error
        # Pinning only adds: another branch's pins (t1) survive a pin call that doesn't know them.
        self.assertEqual(refs(), {review.TREE_REFS + t1, review.TREE_REFS + t2})
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
        with mock.patch.multiple(review, LEDGER=state / "ledger.jsonl", TREES=state / "trees.jsonl",
                                 RUN=state / "run.json", HISTORY=state / "history.jsonl", USAGE=state / "usage.json"):
            write_ledger({"u": {"tests": ["older", reviewed]}})
            write_trees({"u": "e" * 40})  # recorded base pruned long ago
            out = io.StringIO()
            with redirect_stdout(out):
                review.cmd_plan(argparse.Namespace(unit=None, lens=None, max_units=4, stop_at=101))
            selected = json.loads(out.getvalue())["selected"]
            self.assertEqual(selected[0]["since"], base)
            # Only the unit's added and changed files: what a diff review must read (a deleted one cannot be).
            self.assertEqual(selected[0]["changed"], ["a/new.txt", "a/x.txt"])
            self.assertEqual(review.latest_trees(), {"u": base})


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
        core = {"security", "behaviour", "tests", "architecture", "duplication", "simplicity", "supply-chain"}
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

    GDPR = {"gdpr": {"checklist": ".claude/agents/gdpr-reviewer.md", "why": "EU personal data"}}

    def test_custom_lenses_follow_the_built_in_ones_and_can_be_removed(self):
        decided = lens_profile.decide({**self.BASE, "customLenses": {**self.GDPR, "a11y": {
            "checklist": "review/a11y.md", "why": "public sector", "secondOpinion": True}}})
        self.assertEqual([l for l, _, _ in decided][-2:], ["gdpr", "a11y"])
        self.assertEqual(dict((l, why) for l, _, why in decided)["gdpr"], "custom: EU personal data")
        self.assertIn("gdpr", self.lenses(customLenses=self.GDPR))
        self.assertNotIn("gdpr", self.lenses(customLenses=self.GDPR, overrides={"add": {}, "remove": {"gdpr": "paused"}}))
        self.assertEqual(lens_profile.second_opinion({"customLenses": {"a11y": {"secondOpinion": True}, **self.GDPR}}),
                         ["security", "supply-chain", "a11y"])

    def test_custom_lenses_are_validated(self):
        for bad in ({"security": {"checklist": "x.md", "why": "w"}},          # a built-in name
                    {"GDPR": {"checklist": "x.md", "why": "w"}},              # not a lens name
                    {"gdpr": {"checklist": "x.md", "why": " "}},              # no reason
                    {"gdpr": {"checklist": "/etc/x.md", "why": "w"}},         # outside the repository
                    {"gdpr": {"checklist": "../x.md", "why": "w"}},
                    {"gdpr": {"checklist": "x.md", "why": "w", "secondOpinion": "yes"}},
                    {"gdpr": {"checklist": "x.md", "why": "w", "severity": "high"}},
                    {"gdpr": "x.md"}, ["gdpr"]):
            with self.assertRaises(lens_profile.ProfileError, msg=repr(bad)):
                self.lenses(customLenses=bad)

    def test_checklist_of_a_custom_lens_is_the_repository_file(self):
        profile = {"customLenses": self.GDPR}
        self.assertEqual(lens_profile.checklist_path("gdpr", profile), lens_profile.ROOT / ".claude/agents/gdpr-reviewer.md")
        self.assertEqual(lens_profile.checklist_path("security", profile).name, "security-auditor.md")
        with self.assertRaises(lens_profile.ProfileError):
            lens_profile.checklist_path("speed", profile)

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
        self.assertEqual(list(new["lenses"]), ["security", "behaviour", "tests", "architecture", "duplication", "simplicity", "performance", "supply-chain"])
        self.assertEqual(new["units"][0]["lenses"], ["security"])
        self.assertNotIn("context", new["units"][0])
        self.assertEqual(removed, {"web": ["localisation", "contracts"]})
        self.assertEqual(unused, ["behaviour", "tests", "architecture", "duplication", "simplicity", "performance", "supply-chain"])
        self.assertEqual(units["units"][0]["lenses"], ["security", "localisation", "contracts"])  # input untouched



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

    def test_an_id_defined_twice_is_a_problem(self):
        files = self.write({"docs/SPEC.md": "**R-1** a\n**R-2** b (merged from branch x)\n**R-2** c (from branch y)\nsee R-1\n",
                            "tests/t.txt": "R-1 R-2\n"})
        rep = self.report(files)
        self.assertEqual(rep["duplicates"], ["R-2"])
        self.assertIn("defined more than once", spec_rules.problems(rep)[0])

    def test_clean_report_and_missing_spec(self):
        files = self.write({"docs/SPEC.md": "R-1 x\n", "tests/a.test.ts": "it('R-1', ...)\n"})
        self.assertEqual(spec_rules.problems(self.report(files)), [])
        self.assertIn("not found", spec_rules.problems(self.report(files, spec="docs/NOPE.md"))[0])



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



class HandoverTest(unittest.TestCase):
    """Size budgets for the files every session reads (scripts/review/handover.py)."""

    def setUp(self):
        import tempfile
        self.root = Path(tempfile.mkdtemp())
        (self.root / ".agents").mkdir()
        (self.root / "docs").mkdir()

    def test_over_budget_by_lines_including_every_work_file(self):
        (self.root / ".agents/STATUS.md").write_text("x\n" * 151)
        (self.root / "CLAUDE.md").write_text("x\n" * 10)
        (self.root / ".agents/work").mkdir()
        (self.root / ".agents/work/feature--a.md").write_text("x\n" * 81)
        (self.root / ".agents/work/main.md").write_text("x\n" * 5)
        self.assertEqual(handover.over_budget_lines(self.root, {}), [
            ".agents/STATUS.md: 151 lines (budget 150)",
            ".agents/work/feature--a.md: 81 lines (budget 80)",
        ])
        # A project can change a budget; files that don't exist are not reported.
        self.assertEqual(handover.over_budget_lines(self.root, {"handoverBudgets": {
            ".agents/STATUS.md": {"lines": 200}, ".agents/work/*.md": {"lines": 100}}}), [])



@unittest.skipUnless(shutil.which("node"), "node is not installed")
class RealSkipsTest(unittest.TestCase):
    """The workflow's skip filter (review-loop.js realSkips), run with node on its own source."""

    def real_skips(self, skipped, changed, since="t"):
        import json
        candidates = [PLUGIN / "workflows" / "review-loop.js", PLUGIN.parents[1] / "kit" / "claude" / "workflows" / "review-loop.js"]
        src = next(c for c in candidates if c.exists()).read_text()
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
