#!/usr/bin/env python3
"""Self-check of the bootstrap kit: `python3 selfcheck.py` (or `python3 -m unittest selfcheck`).

Proves that the kit works on its own: it installs the kit into an empty, freshly created git
repository and runs the review loop's own tests there, checks that the kit's texts don't depend on
the repository the kit came from, and that every path the texts mention exists after installing.

When the kit sits inside a repository that also has the live copies (scripts/review/,
.claude/workflows/review-loop.js), it also checks that the kit's copies have not drifted from them.
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

# Copied verbatim from the source repository; their test data uses synthetic example paths.
VERBATIM = {"scripts/review/review.py", "scripts/review/test_review.py"}

# Names that would tie the kit to the repository it was extracted from. Worked examples live in
# stacks/ and may name it; nothing in kit/ or BOOTSTRAP.md may.
SOURCE_NAMES = re.compile(r"Hourmark|hourmark|gethourmark|Chaordic|api/internal|web/src/i18n|\.agents/bootstrap/templates")

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
                # .claude/review/ holds state the review loop writes at run time.
                if "<" in path or "*" in path or path.startswith(".claude/review/"):
                    continue
                self.assertTrue((self.repo / path).exists(), f"{text.name} mentions {path}, which the kit does not install")


class TextTest(unittest.TestCase):
    def test_kit_does_not_name_its_source_repository(self) -> None:
        texts = [HERE / "BOOTSTRAP.md", HERE / "install.py", *[HERE / "kit" / r for r in install.kit_files() if r not in VERBATIM]]
        for text in texts:
            for n, line in enumerate(text.read_text().splitlines(), 1):
                self.assertIsNone(SOURCE_NAMES.search(line), f"{text.relative_to(HERE)}:{n}: {line.strip()}")

    def test_kit_and_stack_paths_in_bootstrap_exist(self) -> None:
        for name in ["BOOTSTRAP.md", *[p.relative_to(HERE).as_posix() for p in (HERE / "stacks").glob("*.md")]]:
            for m in KIT_PATH.finditer((HERE / name).read_text()):
                path = m.group(1) or m.group(2)
                self.assertTrue((HERE / path).exists(), f"{name} mentions {path}")

    def test_workflow_lenses_match_the_units_template(self) -> None:
        workflow = (HERE / "kit/claude/workflows/review-loop.js").read_text()
        block = workflow[workflow.index("const LENS_FILE = {"):]
        block = block[: block.index("}")]
        lens_files = dict(re.findall(r"(\w+): '([^']+)'", block))
        units = json.loads((HERE / "kit/scripts/review/units.json").read_text())
        self.assertEqual(lens_files, units["lenses"])
        for path in lens_files.values():
            self.assertEqual(install.target_of(path.replace(".claude/", "claude/", 1)), path)
            self.assertTrue((HERE / "kit" / path.replace(".claude/", "claude/", 1)).exists(), path)


class DriftTest(unittest.TestCase):
    """Only inside a repository that has the live copies; skipped once the kit stands alone."""

    ROOT = HERE.parents[1]

    def test_review_scripts_match_the_live_copies(self) -> None:
        for rel in sorted(VERBATIM):
            live = self.ROOT / rel
            if not live.exists():
                self.skipTest("no live copy next to the kit")
            self.assertEqual((HERE / "kit" / rel).read_text(), live.read_text(), f"{rel} drifted; copy the live version into kit/")

    def test_workflow_matches_the_live_copy_outside_the_project_block(self) -> None:
        live = self.ROOT / ".claude/workflows/review-loop.js"
        if not live.exists():
            self.skipTest("no live workflow next to the kit")

        def without_project(text: str) -> str:
            start = text.index("// ---------------------------------------------------------------- Project configuration")
            return text[:start] + text[text.index("// Lens → checklist."):]

        self.assertEqual(
            without_project((HERE / "kit/claude/workflows/review-loop.js").read_text()),
            without_project(live.read_text()),
            "review-loop.js drifted; copy the live version into kit/ and keep its generic PROJECT block",
        )


if __name__ == "__main__":
    unittest.main(verbosity=1)
