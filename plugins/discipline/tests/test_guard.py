"""The read-only hook (hooks/readonly_guard.py): reviewers can't write; nobody else is affected."""
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
GUARD = PLUGIN / "hooks" / "readonly_guard.py"
spec = importlib.util.spec_from_file_location("readonly_guard", GUARD)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

READER = "discipline:review-reader"


def bash(command: str, agent: str = READER) -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "agent_type": agent, "tool_input": {"command": command}}


class GuardTest(unittest.TestCase):
    def denied(self, event: dict) -> bool:
        out = guard.decide(event)
        return bool(out) and out["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_edit_tools_are_denied_to_the_reader_only(self):
        for tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            self.assertTrue(self.denied({"tool_name": tool, "agent_type": READER}), tool)
            self.assertFalse(self.denied({"tool_name": tool, "agent_type": "discipline:security-auditor"}), tool)
            self.assertFalse(self.denied({"tool_name": tool, "agent_type": "workflow-subagent"}), tool)
            self.assertFalse(self.denied({"tool_name": tool}), tool)  # the main session

    def test_writing_bash_is_denied(self):
        for cmd in [
            "echo hi > notes.txt", "cat a >> b", "ls | tee out.log", "rm -rf src", "mv a b", "cp a b",
            "touch x", "mkdir -p y", "sed -i 's/a/b/' f.go", "perl -pi -e 's/a/b/' f", "git add -A",
            "git commit -m x", "git checkout -- f", "git stash", "git reset --hard", "git clean -fd",
            "npm install left-pad", "pnpm add x", "pip install x", "uv sync", "go mod tidy", "cargo update",
            "eslint --fix src", "prettier --write .", "gofmt -w .", "ruff format", "black src",
            "vitest -u", "jest --updateSnapshot", "go test ./... -update",
            "discipline review mark a:tests", "discipline review baseline --reason x", "discipline review record x.json", "discipline lenses apply",
            "discipline decisions new 'x'", "discipline decisions index", "discipline work",
            "cd src && rm x", "find . -name '*.tmp' | xargs rm",
        ]:
            self.assertTrue(self.denied(bash(cmd)), cmd)

    def test_reading_bash_is_allowed(self):
        for cmd in [
            "git diff HEAD~1", "git log --oneline -5", "git show HEAD:src/a.go", "grep -rn TODO src",
            "cat src/a.go", "ls -la", "go test ./internal/auth/...", "npx vitest run src/x.test.ts",
            "pytest -q tests/test_a.py 2>&1 | tail -20", "discipline review show auth", "discipline review diff",
            "discipline review checklist security", "discipline doc engineering", "npm audit --omit=dev",
            "discipline decisions search rounding", "discipline work --list", "discipline assumptions",
            "ruff check src", "black --check src", "echo done", "cat a 2>/dev/null", "go vet ./... 2>&1",
            "wc -l src/*.go > /dev/null", "jq '.a' f.json",
        ]:
            self.assertFalse(self.denied(bash(cmd)), cmd)

    def test_other_agents_bash_is_untouched(self):
        self.assertFalse(self.denied(bash("rm -rf build", agent="workflow-subagent")))
        self.assertFalse(self.denied(bash("git commit -m x", agent=None)))

    def test_the_script_never_breaks_a_session(self):
        for stdin in ("", "not json", "[]", json.dumps({"tool_name": "Bash"})):
            r = subprocess.run([sys.executable, str(GUARD)], input=stdin, capture_output=True, text=True)
            self.assertEqual((r.returncode, r.stdout), (0, ""), stdin)

    def test_the_script_denies_through_its_output(self):
        r = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(bash("rm x")), capture_output=True, text=True)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual((out["hookEventName"], out["permissionDecision"]), ("PreToolUse", "deny"))

    def test_hooks_json_points_at_the_guard(self):
        hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())["hooks"]["PreToolUse"][0]
        self.assertEqual(set(hooks["matcher"].split("|")), guard.EDIT_TOOLS | {"Bash"})
        self.assertEqual(hooks["hooks"][0]["command"], '"${CLAUDE_PLUGIN_ROOT}/hooks/readonly_guard.py"')


if __name__ == "__main__":
    unittest.main()
