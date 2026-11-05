"""`discipline check` and the command line, run as a real command against throwaway repositories."""
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
from discipline import __version__, lenses  # noqa: E402

FILLED = {"product": "Invoicing", "kinds": ["web-app"], "languages": ["en"], "interfaces": [],
          "performance": "minor", "data": "customer data", "overrides": {"add": {}, "remove": {}}}


class Repo:
    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def units(self, units: list, lenses_map: dict | None = None, roots=("src/",), **extra) -> None:
        cfg = {"lenses": lenses_map if lenses_map is not None else ["tests"],
               "globalExclude": [], "roots": list(roots), "units": units, **extra}
        self.write(".claude/review/units.json", json.dumps(cfg))

    def profile(self, **changes) -> None:
        self.write(".agents/profile.json", json.dumps({**FILLED, **changes}))

    def run(self, *args: str, cwd: str = "") -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        return subprocess.run([str(PLUGIN / "bin" / "discipline"), *args], cwd=self.root / cwd,
                              capture_output=True, text=True, env=env)

    def check(self, cwd: str = "") -> dict:
        r = self.run("check", "--json", cwd=cwd)
        out = json.loads(r.stdout)
        out["rc"] = r.returncode
        return out

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)




class CheckTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()

    def tearDown(self):
        self.repo.close()

    def test_without_units_it_says_to_bootstrap(self):
        out = self.repo.check()
        self.assertEqual(out["rc"], 1)
        self.assertIn("no review units configured", out["problems"][0])

    def test_unit_problems(self):
        self.repo.write("src/a/x.txt", "x")
        self.repo.write("src/b/y.txt", "y")
        self.repo.write("src/c/z.txt", "z")
        self.repo.units([
            {"id": "a", "include": ["src/a/**", "src/b/**"], "lenses": ["tests", "speed"], "context": {"contracts": ["api/**"]}},
            {"id": "a", "include": ["src/b/**"], "lenses": ["tests"]},
        ])
        problems = "\n".join(self.repo.check()["problems"])
        self.assertIn("unit id 'a' is used more than once", problems)
        self.assertIn("lenses that are not configured: ['speed']", problems)
        self.assertIn("context for lenses it does not use: ['contracts']", problems)
        self.assertIn("src/b/y.txt belongs to several units", problems)
        self.assertIn("no unit covers (add them to a unit): src/c/z.txt", problems)

    def test_profile_template_is_a_warning_and_a_filled_profile_must_match_the_units(self):
        self.repo.write("src/x.txt", "x")
        self.repo.units([{"id": "all", "include": ["src/**"], "lenses": ["tests"]}])
        self.repo.write(".agents/profile.json", json.dumps({**FILLED, "product": "<" + "PROJECT>: x", "kinds": []}))
        out = self.repo.check()
        self.assertEqual((out["rc"], out["problems"]), (0, []))
        self.assertIn("still the template", out["warnings"][0])

        self.repo.profile()
        out = self.repo.check()
        self.assertEqual(out["rc"], 1)
        self.assertIn("discipline lenses apply", out["problems"][0])

        applied = self.repo.run("lenses", "apply")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        units = json.loads((self.repo.root / ".claude/review/units.json").read_text())
        units["units"][0]["lenses"] = list(units["lenses"])
        self.repo.write(".claude/review/units.json", json.dumps(units))
        out = self.repo.check()
        self.assertEqual((out["rc"], out["problems"]), (0, []), out)

    def configured(self, **profile) -> None:
        self.repo.profile(**profile)
        chosen = lenses.selected({**FILLED, **profile})
        self.repo.units([{"id": "all", "include": ["src/**", "tests/**", "prompts/**", "evals/**"], "lenses": list(chosen)}],
                        lenses_map=chosen, roots=["src/", "tests/", "prompts/", "evals/"])

    def test_spec_rules_fail_until_pinned(self):
        self.configured(specRules={"tests": ["tests/**"]})
        self.repo.write("docs/SPEC.md", "**R-1** Invoice numbers have no gaps.\n")
        self.repo.write("tests/numbering.txt", "placeholder\n")
        out = self.repo.check()
        self.assertEqual(out["rc"], 1)
        self.assertIn("R-1", out["problems"][0])
        self.repo.write("tests/numbering.txt", "pins R-1\n")
        self.assertEqual(self.repo.check()["rc"], 0)

    def test_ai_eval_facets_fail_until_present(self):
        self.configured(ai=["rag"], aiEvals={"prompts": ["prompts/**"], "evals": "evals/{name}",
                                             "facets": {"prompts/**": ["query", "retrieval", "answer"]}})
        self.repo.write("prompts/answer.md", "Answer from the documents.\n")
        self.repo.write("evals/answer/query.yaml", "[]\n")
        out = self.repo.check()
        self.assertEqual(out["rc"], 1)
        self.assertIn("evals/answer/retrieval", out["problems"][0])
        for facet in ("retrieval", "answer"):
            self.repo.write(f"evals/answer/{facet}.yaml", "[]\n")
        self.assertEqual(self.repo.check()["rc"], 0)

    def test_handover_over_budget_warns_but_passes(self):
        self.configured()
        self.repo.write(".agents/STATUS.md", "x\n" * 151)
        out = self.repo.check()
        self.assertEqual((out["rc"], out["problems"]), (0, []))
        self.assertIn(".agents/STATUS.md: 151 lines (budget 150)", out["warnings"][0])

    def test_runs_from_a_subdirectory_against_the_enclosing_repository(self):
        self.configured()
        self.repo.write("src/deep/er/x.txt", "x")
        out = self.repo.check(cwd="src/deep")
        self.assertEqual((out["rc"], out["problems"]), (0, []), out)


class CliTest(unittest.TestCase):
    def test_version_matches_the_package_and_the_wrapper_runs_from_anywhere(self):
        r = subprocess.run([str(PLUGIN / "bin" / "discipline"), "--version"], cwd=tempfile.gettempdir(),
                           capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), f"discipline {__version__}")

    def test_unknown_command(self):
        r = subprocess.run([str(PLUGIN / "bin" / "discipline"), "nope"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown command", r.stderr)

    def test_every_command_has_help(self):
        for cmd in ("check", "review", "lenses"):
            r = subprocess.run([str(PLUGIN / "bin" / "discipline"), cmd, "--help"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, (cmd, r.stderr))


if __name__ == "__main__":
    unittest.main()
