"""tests/test_publishing.py — the repo is safe to make public, and CI exists.

A repository is a distribution. These tests exist because the two things that go
wrong when a private working copy becomes a public one are quiet: a secret is
committed, or the workflow that was supposed to guard everything never runs.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class IgnoreRules(unittest.TestCase):
    """The ignore file is the last thing between a key and a public commit."""

    @classmethod
    def setUpClass(cls):
        cls.rules = (ROOT / ".gitignore").read_text(encoding="utf-8")

    def test_secrets_are_ignored(self):
        for pattern in ("config/api_keys.json", "config/certs/", ".env"):
            self.assertIn(pattern, self.rules)

    def test_personal_memory_is_ignored(self):
        self.assertIn("memory/long_term.json", self.rules)

    def test_build_noise_is_ignored(self):
        for pattern in ("__pycache__/", ".venv/", "*.log"):
            self.assertIn(pattern, self.rules)

    def test_no_pattern_carries_a_trailing_comment(self):
        # The file's own header says it: git has no trailing comments, so
        # `config/api_keys.json  # key` matches nothing while looking protected.
        patterns = [line for line in self.rules.splitlines()
                    if line.strip() and not line.lstrip().startswith("#")]
        self.assertEqual([line for line in patterns if "#" in line], [])

    def test_the_build_record_is_tracked_on_purpose(self):
        # log.txt and verification-results.txt are the project's own record and
        # test_bootstrap asserts they stay visible. Nothing here may hide them.
        import subprocess
        import tempfile
        git = __import__("shutil").which("git")
        if not git:
            self.skipTest("git is not installed here")
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            subprocess.run([git, "init", "-q", str(repo)], check=True)
            (repo / ".gitignore").write_bytes((ROOT / ".gitignore").read_bytes())
            for name in ("log.txt", "verification-results.txt", "main.py"):
                with self.subTest(name=name):
                    done = subprocess.run([git, "check-ignore", "-q", name],
                                          cwd=repo, check=False)
                    self.assertEqual(done.returncode, 1, f"{name} must stay visible")


class Workflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = ROOT / ".github" / "workflows" / "verify.yml"
        cls.text = cls.path.read_text(encoding="utf-8") if cls.path.exists() else ""

    def test_the_workflow_exists(self):
        self.assertTrue(self.path.exists(), "no CI: nothing runs on a Windows machine")

    def test_it_runs_on_push_and_pull_request(self):
        for trigger in ("push:", "pull_request:", "workflow_dispatch:"):
            self.assertIn(trigger, self.text)

    def test_it_has_a_windows_job(self):
        self.assertIn("windows-latest", self.text)

    def test_it_runs_the_three_gates(self):
        for script in ("scripts/verify.py", "scripts/proof_gate.py",
                       "scripts/verify_all.py"):
            self.assertIn(script, self.text)

    def test_it_does_not_install_the_whole_world(self):
        # Pinning the lean set keeps a red build readable. If someone swaps in
        # `pip install -r requirements.txt`, the run time triples and the failure
        # is buried in logs.
        self.assertNotIn("pip install -r requirements.txt", self.text)

    def test_no_api_key_is_written_into_the_workflow(self):
        self.assertIsNone(re.search(r"AIza[0-9A-Za-z_-]{20,}", self.text))


class Licence(unittest.TestCase):
    def test_attribution_survives(self):
        readme = (ROOT / "readme.md").read_text(encoding="utf-8")
        self.assertIn("FatihMakes", readme)
        self.assertIn("BY-NC", readme)
        self.assertIn("Creative Commons", readme)
        self.assertTrue((ROOT / "LICENSE").exists())


if __name__ == "__main__":
    unittest.main()
