"""The Job Object supervisor, checked by reading its source. It is not checked by running it.

`native/ultron-core/src/process/supervisor.rs` is Windows-only Rust. It was written where there was no Rust
toolchain; `.github/workflows/native-build.yml` has compiled it since 2026-11-27, so it builds. NOTHING HERE
PROVES THAT THE LIMITS WORK: nothing runs the file. These tests pin the properties that were found wrong by
reading the Win32 documentation, so that an edit cannot bring them back unseen:

* The limits were set by two calls. `LimitFlags` is the list of limits in force, so the second call,
  which named only the memory limit, asked for the CPU and process-count limits to be off. The first
  call also set `JOB_OBJECT_LIMIT_PROCESS_TIME` without filling `PerProcessUserTimeLimit`, which
  means a CPU allowance of zero for every process. (A note that this file carried recommended
  setting all the flags in one call; that would have kept the zero allowance. The fix is the three
  flags that have fields: job time, active processes, job memory.)
* A failed `SetInformationJobObject` leaked the job handle, and a failed `AssignProcessToJobObject`
  leaked the process handle.
* The process handle was opened with `PROCESS_ALL_ACCESS`; assigning to a job needs only
  `PROCESS_SET_QUOTA` and `PROCESS_TERMINATE`.
* No `unsafe` block said why it was sound.

What would really settle it: start a process under the job and read the limits back with
`QueryInformationJobObject`. Until that is done the file says so in its header, and one test below
keeps that sentence from being deleted without anyone noticing.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "native" / "ultron-core" / "src" / "process" / "supervisor.rs").read_text(encoding="utf-8")


def code_only(text: str) -> str:
    """The source with line comments removed (this file has no `//` inside a string)."""
    return "\n".join(line.split("//", 1)[0] for line in text.splitlines())


CODE = code_only(SOURCE)

# Each flag in `LimitFlags` and the field the system reads when the flag is set.
FLAG_AND_FIELD = {
    "JOB_OBJECT_LIMIT_JOB_TIME": "PerJobUserTimeLimit",
    "JOB_OBJECT_LIMIT_ACTIVE_PROCESS": "ActiveProcessLimit",
    "JOB_OBJECT_LIMIT_JOB_MEMORY": "JobMemoryLimit",
    "JOB_OBJECT_LIMIT_PROCESS_TIME": "PerProcessUserTimeLimit",
}


def body_of(name: str) -> str:
    """The text of one `fn`, from its signature to the next `fn` or the end."""
    start = CODE.index(f"fn {name}")
    following = re.search(r"\n    pub fn |\nimpl |\n    fn ", CODE[start + 5:])
    return CODE[start:start + 5 + following.start()] if following else CODE[start:]


class TheLimitsAreSetOnce(unittest.TestCase):
    def test_one_call_sets_every_limit(self):
        self.assertEqual(CODE.count("SetInformationJobObject("), 1,
                         "a second call can switch off what the first one set")

    def test_each_flag_that_is_set_comes_with_the_field_it_reads(self):
        for flag, field in FLAG_AND_FIELD.items():
            with self.subTest(flag=flag):
                flag_set = flag in CODE
                field_set = re.search(rf"\b{field}\s*=", CODE) is not None
                self.assertEqual(flag_set, field_set,
                                 f"{flag} is {'set' if flag_set else 'not set'} but {field} is "
                                 f"{'filled' if field_set else 'left at 0'}; a flag with no value "
                                 "means a limit of zero")

    def test_the_three_limits_the_function_promises_are_the_three_that_are_set(self):
        for flag in ("JOB_OBJECT_LIMIT_JOB_TIME", "JOB_OBJECT_LIMIT_ACTIVE_PROCESS",
                     "JOB_OBJECT_LIMIT_JOB_MEMORY"):
            self.assertIn(flag, CODE)
        self.assertNotIn("JOB_OBJECT_LIMIT_PROCESS_TIME", CODE,
                         "a per-process time limit needs PerProcessUserTimeLimit filled in")

    def test_the_cpu_budget_is_in_100_nanosecond_ticks(self):
        self.assertRegex(CODE, r"PerJobUserTimeLimit\s*=\s*i64::from\(cpu_time_seconds\)\s*\*\s*10_000_000")

    def test_the_extended_structure_is_the_one_that_carries_the_memory_limit(self):
        self.assertIn("JobObjectExtendedLimitInformation", CODE)
        self.assertNotIn("JobObjectBasicLimitInformation", CODE)


class NoHandleIsLeaked(unittest.TestCase):
    def test_the_job_handle_has_an_owner_before_anything_can_fail(self):
        body = body_of("new_restricted")
        owner = body.index("Self { handle }")
        self.assertLess(owner, body.index("SetInformationJobObject("),
                        "if the call fails, nothing owns the handle and it is never closed")

    def test_the_job_is_returned_through_the_owner(self):
        self.assertIn("Ok(job)", body_of("new_restricted"))

    def test_the_process_handle_is_closed_before_the_result_is_looked_at(self):
        body = body_of("attach_process")
        self.assertNotRegex(body, r"AssignProcessToJobObject\([^;]*\)\s*\?",
                            "a `?` on the call itself returns before the handle is closed")
        self.assertLess(body.index("CloseHandle(process)"), body.index("assigned?"))

    def test_the_destructor_closes_the_job_handle(self):
        self.assertIn("CloseHandle(self.handle)", CODE)


class TheAccessAskedFor(unittest.TestCase):
    def test_it_is_the_two_rights_the_call_documents_and_no_more(self):
        self.assertNotIn("PROCESS_ALL_ACCESS", CODE)
        body = body_of("attach_process")
        self.assertIn("PROCESS_SET_QUOTA", body)
        self.assertIn("PROCESS_TERMINATE", body)
        self.assertEqual(len(re.findall(r"\bPROCESS_[A-Z_]+\b", re.search(r"OpenProcess\([^;]*;", body).group(0))), 2)


class EveryUnsafeBlockSaysWhy(unittest.TestCase):
    def test_a_safety_comment_sits_directly_above_each_one(self):
        lines = SOURCE.splitlines()
        blocks = [i for i, line in enumerate(lines) if re.search(r"\bunsafe\s*\{", line.split("//", 1)[0])]
        self.assertEqual(len(blocks), 3, "an unsafe block was added or removed; check it has a reason too")
        for index in blocks:
            above = []
            cursor = index - 1
            while cursor >= 0 and lines[cursor].strip().startswith("//"):
                above.append(lines[cursor])
                cursor -= 1
            self.assertTrue(any("SAFETY:" in line for line in above),
                            f"line {index + 1}: `unsafe` with no `// SAFETY:` comment above it")


def header() -> str:
    """The comment at the top of the file, as one line of words."""
    return " ".join(SOURCE[:SOURCE.index("use windows")].replace("//", " ").split())


class TheFileIsHonestAboutWhatItIs(unittest.TestCase):
    def test_the_header_says_it_was_compiled_and_not_run(self):
        self.assertTrue(header().startswith("COMPILED, NOT RUN."), "the first words of the file say what it is")
        self.assertNotIn("NOT COMPILED", header())
        self.assertIn("native-build.yml", header())
        self.assertIn("QueryInformationJobObject", header())
        # The header says a check compiles this file, so that check has to build the crate.
        workflow = (ROOT / ".github" / "workflows" / "native-build.yml").read_text(encoding="utf-8")
        self.assertIn("cargo build --locked --release --manifest-path native/ultron-core/Cargo.toml", workflow)

    def test_the_header_says_nothing_calls_it_and_that_is_true(self):
        self.assertIn("Nothing in `main.rs` calls it", header())
        main = (ROOT / "native" / "ultron-core" / "src" / "main.rs").read_text(encoding="utf-8")
        self.assertNotIn("SandboxJob", main)
        self.assertNotIn("supervisor", main)

    def test_the_wrong_advice_is_corrected_where_it_was_given(self):
        # The old note said to set all the flags together. The file now says that was wrong for one.
        flat = " ".join(SOURCE.replace("///", " ").split())
        self.assertIn("An earlier note in this file said to set all of the flags together; "
                      "that was wrong for this flag.", flat)


class TheSourceReader(unittest.TestCase):
    def test_comments_are_not_code(self):
        self.assertEqual(code_only("let a = 1; // PROCESS_ALL_ACCESS\n// SetInformationJobObject("),
                         "let a = 1; \n")

    def test_body_of_finds_one_function_only(self):
        self.assertNotIn("Drop", body_of("attach_process"))
        self.assertNotIn("attach_process", body_of("new_restricted"))


if __name__ == "__main__":
    unittest.main()
