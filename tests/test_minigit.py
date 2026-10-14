import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "mini_git.py"

class MiniGitCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = os.environ.copy()
        self.env["PYTHONIOENCODING"] = "utf-8"

    def tearDown(self):
        self.temp.cleanup()

    def run_git(self, *args, ok=True):
        result = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.root,
                                env=self.env, text=True, capture_output=True)
        if ok and result.returncode != 0:
            self.fail(f"Command {args} failed: {result.stderr}\n{result.stdout}")
        if not ok and result.returncode == 0:
            self.fail(f"Command {args} unexpectedly succeeded: {result.stdout}")
        return result

    def commit_file(self, name, content, message):
        (self.root / name).write_text(content, encoding="utf-8")
        self.run_git("add", name)
        self.run_git("commit", "-m", message)

    def test_commit_show_and_log(self):
        self.run_git("init")
        self.commit_file("hello.txt", "one\n", "first")
        shown = self.run_git("show", "HEAD").stdout
        self.assertIn("Message: first", shown)
        self.assertIn("hello.txt", shown)
        self.assertIn("first", self.run_git("log").stdout)

    def test_branch_checkout_fast_forward_merge(self):
        self.run_git("init")
        self.commit_file("a.txt", "base", "base")
        self.run_git("branch", "feature")
        self.run_git("checkout", "feature")
        self.commit_file("b.txt", "feature", "feature change")
        self.run_git("checkout", "main")
        self.run_git("merge", "feature")
        self.assertEqual((self.root / "b.txt").read_text(encoding="utf-8"), "feature")
        self.assertIn("feature change", self.run_git("log").stdout)

    def test_tag_and_reset(self):
        self.run_git("init")
        self.commit_file("a.txt", "one", "one")
        first = self.run_git("show", "HEAD").stdout.splitlines()[0].split(": ", 1)[1]
        self.run_git("tag", "v1.0")
        self.commit_file("a.txt", "two", "two")
        self.run_git("reset", first)
        self.assertIn("v1.0", self.run_git("tag").stdout)
        self.assertIn("one", self.run_git("log").stdout)

    def test_ignore_rule(self):
        self.run_git("init")
        (self.root / ".gitignore").write_text("*.tmp\n", encoding="utf-8")
        (self.root / "temp.tmp").write_text("no", encoding="utf-8")
        result = self.run_git("add", "temp.tmp", ok=False)
        self.assertIn("ignored", result.stderr)

    def test_invalid_commit_reference_fails(self):
        self.run_git("init")
        result = self.run_git("show", "does-not-exist", ok=False)
        self.assertNotEqual(result.returncode, 0)

    def test_duplicate_tag_is_handled(self):
        self.run_git("init")
        self.commit_file("a.txt", "one", "first commit")
        self.run_git("tag", "v1.0")
        result = self.run_git("tag", "v1.0", ok=False)
        self.assertNotEqual(result.returncode, 0)

    def test_merge_with_diverged_branches(self):
        self.run_git("init")
        self.commit_file("a.txt", "base\n", "base commit")
        self.run_git("branch", "feature")
        self.commit_file("a.txt", "main change\n", "main change")
        self.run_git("checkout", "feature")
        self.commit_file("a.txt", "feature change\n", "feature change")
        self.run_git("checkout", "main")
        result = self.run_git("merge", "feature", ok=False)
        self.assertNotEqual(result.returncode, 0)

if __name__ == "__main__":
    unittest.main(verbosity=2)
