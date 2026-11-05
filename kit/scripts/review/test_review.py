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
import review  # noqa: E402


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
        self.assertIn("{'fixed': 1, 'rejected': 0, 'open': 1}", out.getvalue())
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
        review.save(review.RUN, {"tree": "t", "hashes": {uid: "old"}, "selected": []})
        review.save(review.LEDGER, {uid: {lens: "old"}})
        with mock.patch.object(review, "all_hashes", return_value={uid: "new"}), \
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
        with mock.patch.object(review, "all_hashes", return_value={u["id"]: "h"}), \
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


class GitBaseTest(unittest.TestCase):
    """Review bases against a real temporary git repository: pinning and recovery."""

    UNIT = {"id": "u", "include": ["a/**"], "lenses": ["tests"]}

    def setUp(self):
        import subprocess
        import tempfile
        self.root = Path(tempfile.mkdtemp())
        self.patches = [
            mock.patch.object(review, "ROOT", self.root),
            mock.patch.object(review, "UNITS", {"globalExclude": ["**/*.png"], "roots": ["a/"], "units": [self.UNIT]}),
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
