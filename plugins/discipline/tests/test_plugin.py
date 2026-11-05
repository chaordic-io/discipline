"""The plugin as a whole: `discipline init` into empty repositories, the end-to-end profile flows, and
the texts (no names from the project the method came from, paths and links that resolve, principle
numbering), the workflow's read-only wiring, the manifests and the skills."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parents[1]
sys.path.insert(0, str(PLUGIN / "src"))
from discipline import __version__, init, lenses, plugin  # noqa: E402

DISCIPLINE = str(PLUGIN / "bin" / "discipline")

# Names that would tie the generic parts to the project the method was extracted from. Worked examples
# in the stack skill's reference/examples/ may name it; nothing else may.
SOURCE_NAMES = re.compile(r"Hourmark|hourmark|gethourmark|api/internal|web/src/i18n")
# Paths in backticks that point into a set-up repository.
INSTALLED_PATH = re.compile(r"`((?:\.agents|\.claude|docs)/[\w./-]+\.[a-z]+)`")
# Paths in a set-up repository that the texts mention but that are created later, not by `discipline init`.
CREATED_LATER = {"docs/history.md", ".claude/settings.json"}


def texts(*suffixes: str) -> list[Path]:
    return [p for p in sorted(PLUGIN.rglob("*")) if p.is_file() and p.suffix in suffixes
            and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts]


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class InitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cmd(self, *args: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        return subprocess.run([DISCIPLINE, *args], cwd=self.repo, capture_output=True, text=True, env=env)

    def test_every_template_has_a_destination(self) -> None:
        for rel in init.template_files():
            if rel not in init.HOME_FILES:
                self.assertIsNotNone(init.target_of(rel), rel)

    def test_init_then_check_passes_with_only_the_template_warning(self) -> None:
        r = self.run_cmd("init")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("copied: CLAUDE.md", r.stdout)
        self.assertTrue((self.repo / ".claude/review/units.json").exists())
        (self.repo / "src").mkdir()
        (self.repo / "src/main.txt").write_text("hello\n")
        check = self.run_cmd("check")
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertIn("still the template", check.stdout)
        self.assertEqual(self.run_cmd("review", "status").returncode, 0)

    def test_init_enables_the_plugin_without_touching_existing_settings(self) -> None:
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude/settings.json").write_text(json.dumps({"enabledPlugins": {"discipline@chaordic": False}, "x": 1}))
        init.install(self.repo)
        settings = json.loads((self.repo / ".claude/settings.json").read_text())
        self.assertEqual(settings["enabledPlugins"]["discipline@chaordic"], False)  # the user's choice stands
        self.assertEqual(settings["x"], 1)
        self.assertEqual(settings["extraKnownMarketplaces"]["chaordic"]["source"]["repo"], "chaordic-io/discipline")

    def test_per_run_files_are_ignored_once_and_existing_lines_kept(self) -> None:
        (self.repo / ".gitignore").write_text("node_modules/\n.claude/review/run.json")  # no final newline
        init.install(self.repo)
        init.install(self.repo)  # idempotent
        text = (self.repo / ".gitignore").read_text()
        self.assertTrue(text.startswith("node_modules/\n.claude/review/run.json\n"))
        for line in init.GITIGNORE:
            self.assertEqual(text.count(line), 1, line)
        r = subprocess.run(["git", "check-ignore", ".claude/review/snapshot.index", ".claude/review/ledger.json"],
                           cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(r.stdout.split(), [".claude/review/snapshot.index"])  # the ledger is committed

    def test_profile_is_stamped_with_the_version(self) -> None:
        init.install(self.repo)
        profile = json.loads((self.repo / ".agents/profile.json").read_text())
        self.assertEqual(profile["discipline"], __version__)
        self.assertEqual(list(profile)[:2], ["_comment", "discipline"])

    def test_never_overwrites(self) -> None:
        (self.repo / "CLAUDE.md").write_text("mine\n")
        result = init.install(self.repo)
        self.assertIn("CLAUDE.md", result["kept"])
        self.assertEqual((self.repo / "CLAUDE.md").read_text(), "mine\n")

    def test_dry_run_copies_nothing(self) -> None:
        result = init.install(self.repo, dry_run=True)
        self.assertTrue(result["new"])
        self.assertIn("CLAUDE.md", result["adapt"])
        self.assertFalse((self.repo / "CLAUDE.md").exists())
        self.assertFalse((self.repo / ".claude/settings.json").exists())

    def test_statusline_goes_to_home_only_on_request(self) -> None:
        home = self.tmp / "home"
        init.install(self.repo, home=home)
        self.assertFalse((home / ".claude/statusline-usage.sh").exists())
        init.install(self.repo, statusline=True, home=home)
        self.assertTrue((home / ".claude/statusline-usage.sh").exists())

    def test_a_filled_profile_selects_the_lenses_and_check_holds_it(self) -> None:
        init.install(self.repo)
        (self.repo / "src").mkdir()
        (self.repo / "src/main.txt").write_text("hello\n")
        self.assertEqual(self.run_cmd("lenses", "check").returncode, 2, "the template profile must be refused")
        profile = json.loads((self.repo / ".agents/profile.json").read_text())
        profile.update({"product": "A static marketing site", "kinds": ["static-site"], "languages": ["en"],
                        "interfaces": [], "performance": "minor", "data": "none"})
        (self.repo / ".agents/profile.json").write_text(json.dumps(profile))
        failing = self.run_cmd("check")
        self.assertNotEqual(failing.returncode, 0)
        self.assertIn("discipline lenses apply", failing.stdout)
        self.assertEqual(self.run_cmd("lenses", "apply").returncode, 0)
        units = json.loads((self.repo / ".claude/review/units.json").read_text())
        self.assertEqual(units["lenses"], ["security", "behaviour", "tests", "architecture", "duplication", "simplicity", "supply-chain"])
        passing = self.run_cmd("check")
        self.assertEqual(passing.returncode, 0, passing.stdout)

    def test_every_installed_path_the_texts_mention_exists(self) -> None:
        init.install(self.repo)
        for text in texts(".md"):
            for m in INSTALLED_PATH.finditer(text.read_text()):
                path = m.group(1)
                if "<" in path or "*" in path or path.startswith(".claude/review/") and not path.endswith(("units.json", "project.json")) or path in CREATED_LATER:
                    continue
                self.assertTrue((self.repo / path).exists(), f"{text.relative_to(PLUGIN)} mentions {path}, which init does not create")


class TextTest(unittest.TestCase):
    def test_generic_parts_do_not_name_the_source_project(self) -> None:
        examples = PLUGIN / "skills" / "stack" / "reference" / "examples"
        for text in texts(".md", ".json", ".js", ".py", ".sh"):
            if examples in text.parents or text.parent.name == "tests":
                continue
            for n, line in enumerate(text.read_text().splitlines(), 1):
                self.assertIsNone(SOURCE_NAMES.search(line), f"{text.relative_to(PLUGIN)}:{n}: {line.strip()}")

    def test_relative_links_resolve(self) -> None:
        for doc in texts(".md"):
            for target in re.findall(r"\]\(([^)#:]+)\)", doc.read_text()):
                self.assertTrue((doc.parent / target).exists(), f"{doc.relative_to(PLUGIN)} links to {target}")
        readme = REPO / "README.md"
        if readme.exists():
            for target in re.findall(r"\]\(([^)#:]+)\)", readme.read_text()):
                self.assertTrue((REPO / target).exists(), f"README.md links to {target}")

    def test_principles_and_criteria_are_numbered_and_every_citation_exists(self) -> None:
        """E1..En (/discipline:engineering) and S1..Sn (/discipline:stack): numbered without gaps; every
        E- or S-number cited anywhere exists."""
        series = {
            "E": set(re.findall(r"\*\*(E\d+)\. ", plugin.skill_file("engineering").read_text())),
            "S": set(re.findall(r"\*\*(S\d+)\. ", (PLUGIN / "skills/stack/reference/choosing-a-stack.md").read_text())),
        }
        for prefix, ids in series.items():
            self.assertTrue(ids, prefix)
            self.assertEqual(ids, {f"{prefix}{n}" for n in range(1, len(ids) + 1)}, f"{prefix} numbered without gaps")
        docs = texts(".md", ".js", ".py") + ([REPO / "README.md"] if (REPO / "README.md").exists() else [])
        for doc in docs:
            if doc.parent.name == "tests":
                continue
            text = re.sub(r"noqa:[^\n]*", "", doc.read_text())  # linter codes such as E402 are not citations
            text = text.replace("E11 onwards", "")  # where a project's own principles start
            for prefix, ids in series.items():
                for cited in re.findall(rf"\b{prefix}(\d+)\b", text):
                    self.assertIn(f"{prefix}{cited}", ids, f"{doc} cites {prefix}{cited}")

    def test_checklists_and_workflow_are_generic(self) -> None:
        for path in [*(PLUGIN / "agents").glob("*.md"), PLUGIN / "workflows" / "review-loop.js"]:
            text = path.read_text()
            self.assertNotIn("ADAPT", text, path.name)
            self.assertNotIn("<PROJECT>", text, path.name)

    def test_checklists_are_numbered_from_one_without_gaps(self) -> None:
        for path in sorted((PLUGIN / "agents").glob("*.md")):
            nums = [int(n) for n in re.findall(r"^(\d+)\.", path.read_text(), re.M)]
            if nums:
                self.assertEqual(nums, list(range(1, len(nums) + 1)), path.name)

    def test_every_lens_has_its_checklist_and_the_example_units_use_them_all(self) -> None:
        for lens, name in lenses.CATALOGUE.items():
            path = plugin.agent_file(name)
            self.assertTrue(path.exists(), lens)
            self.assertIn(f"`{lens}` section of `.agents/review-context.md`", path.read_text(), lens)
        units = json.loads((init.templates() / "claude/review/units.json").read_text())
        self.assertEqual(units["lenses"], list(lenses.CATALOGUE))
        self.assertEqual({l for u in units["units"] for l in u["lenses"]}, set(lenses.CATALOGUE))
        context = (init.templates() / "agents-folder/review-context.md").read_text()
        for lens in lenses.CATALOGUE:
            self.assertIn(f"\n## {lens}\n", context, lens)

    def test_workflow_takes_its_lenses_from_the_plan_and_runs_reviewers_read_only(self) -> None:
        workflow = (PLUGIN / "workflows" / "review-loop.js").read_text()
        self.assertIn("const LENSES = Array.isArray(plan.lenses)", workflow)
        self.assertIn("const READER = 'discipline:review-reader'", workflow)
        self.assertIn("const RP = 'discipline review'", workflow)
        self.assertTrue((PLUGIN / "agents" / "review-reader.md").exists())
        for label in ("review:", "verify:", "verify2:", "delta:"):
            call = workflow[workflow.index(f"label: `{label}"):]
            self.assertIn("agentType: READER", call[: call.index("\n")], label)
        self.assertIn("name: 'review-loop'", workflow)


class ManifestTest(unittest.TestCase):
    def test_plugin_and_marketplace_agree(self) -> None:
        manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual(manifest["name"], "discipline")
        self.assertEqual(manifest["version"], __version__)
        market = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
        self.assertEqual(market["name"], init.MARKETPLACE)
        entry = next(p for p in market["plugins"] if p["name"] == manifest["name"])
        self.assertEqual((REPO / entry["source"]).resolve(), PLUGIN)

    def test_changelog_has_this_version(self) -> None:
        changelog = REPO / "CHANGELOG.md"
        self.assertTrue(changelog.exists())
        self.assertIn(f"## {__version__}", changelog.read_text())

    def test_skills_have_frontmatter_and_stay_small(self) -> None:
        for skill in sorted((PLUGIN / "skills").iterdir()):
            text = (skill / "SKILL.md").read_text()
            front = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
            self.assertIsNotNone(front, skill.name)
            self.assertIn(f"name: {skill.name}\n", front.group(1) + "\n", skill.name)
            self.assertRegex(front.group(1), r"description: \S", skill.name)
            self.assertLess(len(text.splitlines()), 500, skill.name)

    def test_agents_have_frontmatter_with_read_only_tools(self) -> None:
        for agent in sorted((PLUGIN / "agents").glob("*.md")):
            front = re.match(r"\A---\n(.*?)\n---\n", agent.read_text(), re.S).group(1)
            self.assertIn(f"name: {agent.stem}\n", front + "\n")
            tools = re.search(r"^tools: (.*)$", front, re.M).group(1)
            self.assertEqual({t.strip() for t in tools.split(",")}, {"Read", "Grep", "Glob", "Bash"}, agent.name)

    def test_doc_and_checklist_commands_print_every_guide(self) -> None:
        for name in ("engineering", "working", "stack", "bootstrap", "upgrade"):
            r = subprocess.run([DISCIPLINE, "doc", name], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, (name, r.stderr))
            self.assertNotIn("\n---\n", r.stdout[:20], name)  # frontmatter stripped
        for lens in lenses.CATALOGUE:
            r = subprocess.run([DISCIPLINE, "review", "checklist", lens], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, (lens, r.stderr))
            self.assertIn("READ-ONLY", r.stdout, lens)


if __name__ == "__main__":
    unittest.main()
