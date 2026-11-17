"""Structured decisions (front matter: kind, who decided, area, spec, superseded-by), the front-matter
reader they rest on, listing and search (proposals included), the gate's checks, and the migration of
decisions written in the pre-0.5 bullet format."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from discipline import decisions, frontmatter, work  # noqa: E402
from test_team import Repo  # noqa: E402


class FrontMatterTest(unittest.TestCase):
    def test_reads_scalars_lists_quotes_and_comments(self):
        meta, body = frontmatter.split(
            "---\ndate: 2026-11-16\nkind: technical   # product | technical\narea: [money, \"tax, VAT\"]\n"
            "note: it's plain # a comment\nhash: \"a # b\"\ntests:\n  - tests/a.py\n  - 'tests/b.py'\n"
            "superseded-by:\n---\n# Title\n")
        self.assertEqual(meta, {"date": "2026-11-16", "kind": "technical", "area": ["money", "tax, VAT"],
                                "note": "it's plain", "hash": "a # b", "tests": ["tests/a.py", "tests/b.py"],
                                "superseded-by": ""})
        self.assertEqual(body, "# Title\n")

    def test_dump_reads_back_the_same(self):
        meta = {"a": "x", "b": ["Ann, PO", "Bob"], "c": "", "d": [], "e": "it's: odd"}
        self.assertEqual(frontmatter.split(frontmatter.dump(meta, {"a": "note"}) + "body")[0], meta)

    def test_no_front_matter_and_unreadable_front_matter(self):
        self.assertEqual(frontmatter.split("# Just a title\n"), (None, "# Just a title\n"))
        with self.assertRaises(frontmatter.FrontMatterError):
            frontmatter.split("---\nkind: a\n  nested: b\n---\n")
        with self.assertRaises(frontmatter.FrontMatterError):
            frontmatter.split("---\nkind: a\nkind: b\n---\n")
        self.assertEqual(frontmatter.read("---\nnot yaml at all\n---\n"), {})


class DecisionFileTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp()) / "docs" / "decisions"

    def tearDown(self):
        shutil.rmtree(self.dir.parents[1], ignore_errors=True)

    def write(self, name, **meta):
        fields = {"title": name[11:-3], "date": name[:10], "kind": "technical", "decided-by": "agent", "people": [], "area": ["money"],
                  "spec": [], "tests": [], "superseded-by": "", **meta}
        (self.dir / name).write_text(frontmatter.dump(fields) + "\n## Decision\n")

    def test_new_writes_front_matter_and_the_sections_for_what_was_turned_down(self):
        path = decisions.new("Use Postgres \"advisory\" locks: it's simpler", today="2026-11-16", directory=self.dir,
                             kind="technical", by="together", people=["Ann"], area=["numbering"])
        self.assertEqual(path.name, "2026-11-16-use-postgres-advisory-locks-it-s-simpler.md")
        text = path.read_text()
        meta = frontmatter.read(text)
        self.assertEqual(meta["title"], "Use Postgres \"advisory\" locks: it's simpler")
        self.assertNotIn("\n# ", text)  # the title is not repeated as a heading
        self.assertEqual((meta["kind"], meta["decided-by"], meta["people"], meta["area"]),
                         ("technical", "together", ["Ann"], ["numbering"]))
        for heading in ("## Trigger", "## Decision", "## Alternatives turned down", "## Tried and abandoned"):
            self.assertIn(heading, text)
        e = decisions.entries(self.dir)[0]
        self.assertEqual((e.title, e.who()), ("Use Postgres \"advisory\" locks: it's simpler", "together (Ann)"))

    def test_the_gate_checks_kind_who_and_superseded_by(self):
        self.dir.mkdir(parents=True)
        self.write("2026-11-01-a.md", kind="architecture")
        self.write("2026-11-02-b.md", **{"decided-by": "someone"})
        self.write("2026-11-03-c.md", **{"superseded-by": "2026-11-09-missing.md"})
        self.write("2026-11-04-d.md", kind="product")  # a product decision by an agent alone
        self.write("2026-11-05-e.md", **{"decided-by": "people"})  # nobody named
        (self.dir / "2026-11-06-f.md").write_text("---\nkind: [unclosed\n  bad: x\n---\n# F\n")
        self.write("2026-11-07-g.md", title="")
        index = self.dir.parent / "DECISIONS.md"
        index.write_text(decisions.render(decisions.entries(self.dir)))
        errs, warns = decisions.problems(self.dir, index, [])
        self.assertTrue(any("2026-11-01-a.md: kind must be" in e for e in errs), errs)
        self.assertTrue(any("2026-11-02-b.md: decided-by must be" in e for e in errs), errs)
        self.assertTrue(any("2026-11-03-c.md: superseded-by names" in e for e in errs), errs)
        self.assertTrue(any("2026-11-06-f.md: unreadable front matter" in e for e in errs), errs)
        self.assertTrue(any("2026-11-07-g.md: no title in its front matter" in e for e in errs), errs)
        self.assertFalse(any("2026-11-01-a.md: no title" in e for e in errs), errs)
        self.assertTrue(any("by an agent alone" in w and "2026-11-04-d.md" in w for w in warns), warns)
        self.assertTrue(any("aren't named" in w and "2026-11-05-e.md" in w for w in warns), warns)

    def test_list_filters_and_leaves_out_superseded_decisions(self):
        self.dir.mkdir(parents=True)
        self.write("2026-11-01-floats.md", **{"superseded-by": "2026-11-02-decimal.md"})
        self.write("2026-11-02-decimal.md", **{"decided-by": "together", "people": ["Ann"], "spec": ["3.2"]})
        self.write("2026-11-03-refunds.md", kind="product", **{"decided-by": "people", "people": ["PO"], "area": ["refunds"]})
        items = decisions.entries(self.dir)
        names = lambda found: [e.file for e in found]  # noqa: E731
        self.assertEqual(names(decisions.select(items, area="money")), ["2026-11-02-decimal.md"])
        self.assertEqual(names(decisions.select(items, area="money", include_superseded=True)),
                         ["2026-11-02-decimal.md", "2026-11-01-floats.md"])
        self.assertEqual(names(decisions.select(items, kind="product")), ["2026-11-03-refunds.md"])
        self.assertEqual(names(decisions.select(items, by="together")), ["2026-11-02-decimal.md"])
        self.assertEqual(names(decisions.select(items, spec="3")), ["2026-11-02-decimal.md"])  # its subsections too
        self.assertEqual(names(decisions.select(items, spec="3.21")), [])
        self.assertEqual(names(decisions.select(items, spec="3.2")), ["2026-11-02-decimal.md"])


LEGACY = """# Half-up rounding

- **Date:** 2026-11-04. **Kind:** user decision
- **Area:** money, invoicing
- **Trigger:** the user: "round like the tax office does"
- **Decision:** half-up to the cent, once, on the invoice total
- **Alternatives turned down:** banker's rounding (the tax office doesn't use it);
  per-line rounding (totals drift)
- **Conventions taken during the build** (optional): <choices made without asking, so they can be revisited>
- **Spec:** 3.2. **Tests:** tests/test_rounding.py
- **Superseded by:** 2026-11-10-per-line.md
- quoted: (assumed 2026-11-01, not confirmed)
"""


class MigrationTest(unittest.TestCase):
    def test_a_legacy_decision_becomes_front_matter_and_sections(self):
        text, inferred = decisions.migrate_text(LEGACY)
        self.assertTrue(inferred)
        meta, body = frontmatter.split(text)
        self.assertEqual(meta, {"title": "Half-up rounding", "date": "2026-11-04", "kind": "product", "decided-by": "people", "people": ["user"],
                                "area": ["money", "invoicing"], "spec": ["3.2"], "tests": ["tests/test_rounding.py"],
                                "superseded-by": "2026-11-10-per-line.md"})
        self.assertNotIn("# Half-up rounding", body)
        self.assertTrue(body.startswith("\n## Trigger"), body[:40])
        self.assertIn("## Alternatives turned down\n\nbanker's rounding (the tax office doesn't use it);\nper-line", body)
        self.assertNotIn("Conventions", body)  # the unfilled placeholder is dropped
        self.assertIn("## Notes\n\n- quoted: (assumed 2026-11-01, not confirmed)", body)
        self.assertEqual(decisions.migrate_text(text), (text, True))  # already migrated: unchanged

    def test_a_title_kept_in_a_heading_moves_into_the_front_matter(self):
        text = "---\ndate: 2026-11-16\nkind: technical\ndecided-by: agent\n---\n\n# Use a sequence\n\n## Decision\n\nx\n"
        migrated, _ = decisions.migrate_text(text)
        meta, body = frontmatter.split(migrated)
        self.assertEqual(list(meta)[:2], ["title", "date"])
        self.assertEqual(meta["title"], "Use a sequence")
        self.assertEqual(body, "\n## Decision\n\nx\n")

    def test_a_proposal_gets_its_title_and_status_into_front_matter(self):
        old = ("# Proposal: Refunds\n\n> **Status:** accepted, 2026-11-02. Points marked *(convention)* are settled.\n"
               "> The questions are the user's call.\n\n## Request (verbatim)\n")
        meta, body = frontmatter.split(decisions.migrate_proposal(old))
        self.assertEqual(meta, {"title": "Refunds", "status": "accepted", "date": "2026-11-02", "area": [], "decisions": []})
        self.assertTrue(body.lstrip("\n").startswith("> Points marked *(convention)* are settled.\n> The questions"), body)
        self.assertNotIn("# Proposal", body)
        current = decisions.migrate_proposal(old)
        self.assertEqual(decisions.migrate_proposal(current), current)

    def test_an_unknown_kind_is_left_for_a_person_to_fill_in(self):
        text, inferred = decisions.migrate_text("# X\n\n- **Date:** 2026-11-04. **Kind:** settled at the offsite\n")
        self.assertFalse(inferred)
        self.assertEqual(frontmatter.read(text)["kind"], "<product | technical>")

    def test_legacy_decisions_are_still_read_and_the_gate_suggests_migrating(self):
        r = Repo()
        try:
            r.write("docs/decisions/2026-11-04-half-up-rounding.md", LEGACY)
            r.write("docs/decisions/2026-11-10-per-line.md", "# Per line\n\n- **Date:** 2026-11-10. **Kind:** agent, bug fix\n- **Area:** money\n")
            r.run("decisions", "index")
            out = json.loads(r.run("check", "--json").stdout)
            self.assertEqual(out["problems"], [])
            self.assertTrue(any("pre-0.5 format" in w for w in out["warnings"]), out["warnings"])
            self.assertIn("2 migrated; 0 need kind", r.run("decisions", "migrate").stdout)
            out = json.loads(r.run("check", "--json").stdout)
            self.assertEqual(out["problems"], [])
            self.assertFalse(any("pre-0.5" in w for w in out["warnings"]), out["warnings"])
            listed = r.run("decisions", "list", "--area", "money").stdout
            self.assertIn("Per line  [technical, agent, money]", listed)
            self.assertNotIn("Half-up", listed)  # superseded
            self.assertIn("Half-up", r.run("decisions", "list", "--all").stdout)
        finally:
            r.close()


class SearchAndWorkFileTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()

    def tearDown(self):
        self.repo.close()

    def test_search_finds_turned_down_alternatives_and_dropped_proposals(self):
        r = self.repo
        r.run("decisions", "new", "Invoice numbers from a sequence", "--kind", "technical", "--by", "together",
              "--people", "Ann", "--area", "numbering")
        path = next((r.root / "docs/decisions").glob("*invoice-numbers*.md"))
        path.write_text(path.read_text().replace(
            "<!-- One bullet per option considered and not taken, with the reason it was turned down. -->",
            "- **Redis counter:** loses numbers on failover."))
        r.write("docs/proposals/NUMBERING.md", "---\ntitle: Redis numbering\nstatus: dropped\ndate: 2026-11-01\n---\n\nWhy: Redis.\n")
        hits = r.run("decisions", "search", "redis").stdout
        self.assertIn("Invoice numbers from a sequence  [technical, together (Ann), numbering]", hits)
        self.assertIn("proposal (dropped)  docs/proposals/NUMBERING.md  Redis numbering", hits)

    def test_proposals_without_front_matter_are_a_warning_until_migrated(self):
        r = self.repo
        r.write("docs/proposals/OLD.md", "# Proposal: old style\n")
        out = json.loads(r.run("check", "--json").stdout)
        self.assertTrue(any("proposals without a title and a status" in w and "OLD.md" in w for w in out["warnings"]), out["warnings"])
        self.assertIn("migrated  docs/proposals/OLD.md", r.run("decisions", "migrate").stdout)
        self.assertEqual(frontmatter.read((r.root / "docs/proposals/OLD.md").read_text())["title"], "old style")
        out = json.loads(r.run("check", "--json").stdout)
        self.assertFalse(any("proposals without" in w for w in out["warnings"]), out["warnings"])

    def test_work_file_header_comes_from_front_matter_or_old_bullets(self):
        meta = work.header("---\nbranch: x\nwho: Ann\nroadmap: numbering\nowns: [src/a/, src/b/]\n---\n# Work\n")
        self.assertEqual(meta, {"Who": "Ann", "Roadmap item": "numbering", "Owns": "src/a/, src/b/"})
        old = work.header("# Work on `x`\n\n- **Who:** Bob <!-- c -->\n- **Owns:** src/b/\n")
        self.assertEqual(old, {"Who": "Bob", "Roadmap item": "?", "Owns": "src/b/"})


if __name__ == "__main__":
    unittest.main()
