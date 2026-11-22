"""The workflows: a gate that cannot fail is not a gate, and a job gets only the access it needs.

Two faults sat in `.github/workflows/verify.yml`, both found by reading how GitHub runs a step:

* The Linux 'Proof gate' step has no `shell:` key, so GitHub runs `bash -e {0}`, which has no `pipefail`.
  Its command was `python scripts/proof_gate.py ... | tee file`, so the step took `tee`'s exit status (0)
  and a gate that exited 1 could not turn the run red. (`actions/runner`, ScriptHandler.cs: an unspecified
  shell gets `-e {0}`; an explicit `bash` gets `-e -o pipefail {0}`.) The Windows job had `shell: bash`
  on the same pattern; Linux did not.
* The file declared no `permissions:`, so the jobs ran with whatever token scope the repository defaults
  to, which nobody had written down. Nothing there writes to the repository.

These tests read the workflow text, so they need no YAML library and no network. One of them runs the
step's own script under the flags GitHub uses and checks that a failing gate fails the step.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))


def steps(text: str) -> list[str]:
    """The text of every step: from one `      - ` item (six spaces, a dash) to the next."""
    blocks: list[list[str]] = []
    current = None
    for line in text.splitlines():
        if line.startswith("      - "):
            current = [line]
            blocks.append(current)
        elif current is not None and (line.startswith("        ") or not line.strip()
                                      or line.startswith("      #")):
            current.append(line)
        elif current is not None and re.match(r"^(\S|  \S|    \S)", line):
            current = None                      # dedented: out of the steps
    return ["\n".join(block) for block in blocks]


def a_bash_we_can_drive() -> str | None:
    """The `bash` these tests run, or None where there is not one they can drive.

    Not on Windows. A `bash` on a Windows PATH is usually `System32\\bash.exe`, the launcher for the
    Linux subsystem, which exits 1 when no distribution is installed; the first Windows run of these
    two tests saw exactly that (exit 1 where 0 was expected; the cause is inferred from that, not
    confirmed). The tests also hand bash a POSIX `PATH`. Nothing is lost: they run the very step
    text that both jobs use, and the Linux job runs them under a real bash.
    """
    return None if os.name == "nt" else shutil.which("bash")


def run_script(step: str) -> str:
    """The `run: |` block of one step, dedented."""
    lines = step.splitlines()
    for index, line in enumerate(lines):
        if re.match(r"^\s+run: \|\s*$", line):
            body = []
            for follower in lines[index + 1:]:
                if follower.strip() and not follower.startswith("          "):
                    break
                body.append(follower)
            return textwrap.dedent("\n".join(body))
    return ""


class EveryWorkflow(unittest.TestCase):
    def test_there_are_workflows_to_check(self):
        self.assertGreaterEqual(len(WORKFLOWS), 5)

    def test_each_declares_the_access_it_needs(self):
        for path in WORKFLOWS:
            text = path.read_text(encoding="utf-8")
            self.assertRegex(text, r"(?m)^permissions:", f"{path.name} has no top-level `permissions:`")

    def test_a_step_that_pipes_into_tee_can_fail_the_job(self):
        for path in WORKFLOWS:
            for step in steps(path.read_text(encoding="utf-8")):
                script = run_script(step)
                if re.search(r"\|\s*tee\b", script):
                    explicit = re.search(r"(?m)^\s+shell:\s*bash\s*$", step) or "pipefail" in script
                    self.assertTrue(explicit, f"{path.name}: a step pipes into `tee` under the default "
                                              f"shell, which has no pipefail:\n{script[:200]}")


class TheVerifyWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / ".github" / "workflows" / "verify.yml").read_text(encoding="utf-8")
        cls.gates = [s for s in steps(cls.text) if "name: Proof gate" in s]

    def test_both_jobs_run_the_proof_gate(self):
        self.assertEqual(len(self.gates), 2, "one on Linux and one on Windows")

    def test_a_commit_on_main_is_never_cancelled_by_the_next(self):
        self.assertIn("cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}", self.text)
        self.assertIn("github.ref == 'refs/heads/main' && github.sha || github.ref", self.text,
                      "on main every commit needs a group of its own")

    @unittest.skipUnless(a_bash_we_can_drive(), "no POSIX bash to drive here (Windows skips; Linux runs it)")
    def test_a_failing_gate_fails_the_step_and_the_summary_is_still_written(self):
        for gate in self.gates:
            script = run_script(gate)
            self.assertIn("proof_gate.py", script)
            for gate_exit in (0, 3):
                with tempfile.TemporaryDirectory() as folder:
                    work = Path(folder)
                    (work / "scripts").mkdir()
                    (work / "verification").mkdir()      # the Windows job's earlier step makes it
                    (work / "scripts" / "proof_gate.py").write_text(
                        f"import sys\nprint('the gate says so')\nsys.exit({gate_exit})\n", encoding="utf-8")
                    summary = work / "summary.md"
                    summary.write_text("", encoding="utf-8")
                    # The flags GitHub runs `shell: bash` with.
                    done = subprocess.run(
                        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
                        cwd=work, capture_output=True, text=True,
                        env={"PATH": str(Path(sys.executable).parent) + ":/usr/bin:/bin",
                             "GITHUB_STEP_SUMMARY": str(summary)})
                    self.assertEqual(done.returncode, gate_exit, done.stderr)
                    self.assertIn("Proof gate", summary.read_text(encoding="utf-8"),
                                  "the summary is written whether or not the gate passed")

    def test_the_old_form_of_the_step_really_did_swallow_the_failure(self):
        # The control for the test above: the same pipe under `bash -e` (what a step with no `shell:`
        # gets) passes whatever the gate exits. If this ever stops being true, the lesson has moved.
        if not a_bash_we_can_drive():
            self.skipTest("no POSIX bash to drive here (Windows skips; Linux runs it)")
        done = subprocess.run(["bash", "-e", "-c", "false | tee /dev/null"], capture_output=True)
        self.assertEqual(done.returncode, 0)


class TheStepReader(unittest.TestCase):
    def test_it_splits_steps_and_finds_the_run_block(self):
        text = ("jobs:\n  a:\n    steps:\n      - uses: x@1\n\n      # a note\n"
                "      - name: Two\n        shell: bash\n        run: |\n          echo hi\n          echo ho\n"
                "      - name: Three\n        run: echo no\n")
        found = steps(text)
        self.assertEqual(len(found), 3)
        self.assertEqual(run_script(found[1]), "echo hi\necho ho")
        self.assertEqual(run_script(found[2]), "", "a one-line `run:` is not a block")


if __name__ == "__main__":
    unittest.main()
