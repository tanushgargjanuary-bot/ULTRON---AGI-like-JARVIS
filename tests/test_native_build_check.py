"""The check that builds `native/ultron-core`, and what it is allowed to claim.

`native/ultron-core` is a Rust program that nothing in Ultron starts. Until 2026-11-26 nothing built it either: the
notes beside it said "NOT COMPILED, NOT RUN", and a test file said that nothing proved the code compiles. The owner
kept it ("I think it may be needed") and then wrote: "Please build it. add a build check too."

`.github/workflows/native-build.yml` is that check. One job, on Windows, because the crate uses Win32 (named pipes,
shared memory, job objects). It builds from the versions in `Cargo.lock`, runs the crate's own unit tests, starts the
program it built and runs the end-to-end test that was written for it and skipped for want of a binary
(`tests/test_hybrid_ipc.py`, `TestHybridIPCE2E`), and keeps the program as a download.

It is not a required check. These tests hold the workflow to what it says, and hold the lock file to the manifest, so
that a changed dependency fails here in seconds and not after a Windows build.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "native-build.yml"
CRATE = ROOT / "native" / "ultron-core"


def text_of(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def job_text(workflow: str, job: str) -> str:
    """The text of one job: from its `  name:` line to the next job or the end of the file."""
    found = re.search(rf"(?ms)^  {job}:\n(.*?)(?=^  [\w-]+:\n|\Z)", workflow)
    return found.group(1) if found else ""


class TheNativeBuildCheck(unittest.TestCase):
    WATCHED = ("native/**", ".github/workflows/native-build.yml")
    REQUIRED_CHECKS = ("fast offline gate", "linux \u2014 suite and instruments",
                       "windows \u2014 the machine the claims are about")

    @classmethod
    def setUpClass(cls):
        cls.text = text_of(WORKFLOW)
        cls.build = job_text(cls.text, "build")
        cls.triggers = cls.text.split("\npermissions:")[0]

    def event_block(self, event: str) -> str:
        found = re.search(rf"(?ms)^  {event}:\n(.*?)(?=^  \S|\Z)", self.triggers)
        return found.group(1) if found else ""

    def test_the_workflow_exists_with_a_build_job(self):
        self.assertTrue(self.text, ".github/workflows/native-build.yml is missing")
        self.assertTrue(self.build, "no `build` job")

    def test_it_builds_from_the_versions_in_the_lock_file_on_windows(self):
        self.assertIn("runs-on: windows-latest", self.build, "the crate uses Win32 and does not build elsewhere")
        self.assertRegex(self.build, r"cargo build --locked --release --manifest-path native/ultron-core/Cargo\.toml")

    def test_it_runs_the_crates_own_unit_tests(self):
        self.assertRegex(self.build, r"cargo test --locked --manifest-path native/ultron-core/Cargo\.toml")

    def test_it_starts_the_program_it_built_and_a_skipped_test_fails_the_job(self):
        # The end-to-end test skips when the binary is not where it looks. A skip is not a pass.
        self.assertIn("tests.test_hybrid_ipc.TestHybridIPCE2E", self.build)
        self.assertRegex(self.build, r"(?s)grep -q \"skipped\".*?exit 1")

    def test_the_end_to_end_test_looks_where_the_build_puts_the_program(self):
        manifest = text_of(CRATE / "Cargo.toml")
        name = re.search(r'(?m)^name\s*=\s*"([^"]+)"', manifest)
        self.assertTrue(name, "Cargo.toml names no package")
        built = f"native/ultron-core/target/release/{name.group(1)}.exe"
        looks = text_of(ROOT / "tests" / "test_hybrid_ipc.py")
        self.assertIn('"native", "ultron-core", "target", "release", "ultron-core.exe"', looks)
        self.assertEqual(name.group(1), "ultron-core")
        self.assertRegex(self.build, rf"(?s)upload-artifact@[0-9a-f]{{40}}.*?path:\s*{re.escape(built)}\s*\n",
                         "the program is kept from a different path than the one the test looks in")

    def test_the_program_is_kept_for_download_and_a_missing_one_fails_the_job(self):
        self.assertRegex(self.build, r"(?s)upload-artifact@[0-9a-f]{40}.*?name:\s*ultron-core-windows-x64")
        self.assertRegex(self.build, r"(?m)^\s+if-no-files-found:\s*error\s*$")
        self.assertRegex(self.build, r"(?m)^\s+retention-days:\s*\d+\s*$")

    def test_it_runs_when_native_or_the_workflow_changes(self):
        listed = {event: re.findall(r'(?m)^\s+-\s+"([^"]+)"\s*$', self.event_block(event))
                  for event in ("pull_request", "push")}
        for event, paths in listed.items():
            with self.subTest(event=event):
                self.assertEqual(sorted(paths), sorted(self.WATCHED), f"the paths that start a {event} run")

    def test_it_also_runs_every_month_and_by_hand(self):
        # The compiler on the runner moves even when the code does not.
        self.assertRegex(self.triggers, r'(?m)^\s+-\s+cron:\s+"\d+ \d+ \d+ \* \*"')
        self.assertRegex(self.triggers, r"(?m)^  workflow_dispatch:")

    def test_a_step_that_fails_leaves_the_log_readable(self):
        self.assertRegex(self.text, r"(?m)^\s+CARGO_TERM_COLOR:\s*never\s*$")

    def test_every_run_step_uses_bash_as_the_other_windows_jobs_do(self):
        self.assertRegex(self.build, r"(?m)^    defaults:\n      run:\n(?:        #[^\n]*\n)*        shell: bash\s*$")

    def test_the_job_has_a_time_limit(self):
        self.assertRegex(self.build, r"(?m)^    timeout-minutes:\s*\d+\s*$")

    def test_it_only_reads_the_repository(self):
        self.assertRegex(self.text, r"(?m)^permissions:\n  contents: read\s*$")
        self.assertNotIn("secrets.", self.text)
        self.assertNotIn("pull_request_target", self.text)

    def test_a_commit_on_main_is_never_cancelled_by_the_next(self):
        self.assertIn("cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}", self.text)
        self.assertIn("github.ref == 'refs/heads/main' && github.sha || github.ref", self.text)

    def test_no_job_takes_the_name_of_a_required_check(self):
        for required in self.REQUIRED_CHECKS:
            with self.subTest(required=required):
                self.assertNotIn(required, self.text,
                                 "a job named like a required check could stand in for it, or block a merge")

    def test_it_says_what_it_does_not_show(self):
        # A green build is not a working feature. The file must keep saying so.
        self.assertRegex(self.text, r"(?is)does not show.*?works")


class TheLockFileAgreesWithTheManifest(unittest.TestCase):
    """What `cargo build --locked` checks, checked here in seconds: the lock names every direct dependency."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = text_of(CRATE / "Cargo.toml")
        cls.lock = text_of(CRATE / "Cargo.lock")

    def direct_dependencies(self) -> dict[str, str]:
        section = re.search(r"(?ms)^\[dependencies\]\n(.*?)(?=^\[|\Z)", self.manifest)
        self.assertTrue(section, "Cargo.toml has no [dependencies] section")
        found: dict[str, str] = {}
        for match in re.finditer(r'(?ms)^([A-Za-z0-9_-]+)\s*=\s*(?:"([^"]+)"|\{[^}]*?version\s*=\s*"([^"]+)")',
                                 section.group(1)):
            found[match.group(1)] = match.group(2) or match.group(3)
        return found

    def locked(self) -> dict[str, list[str]]:
        found: dict[str, list[str]] = {}
        for match in re.finditer(r'(?m)^name = "([^"]+)"\nversion = "([^"]+)"', self.lock):
            found.setdefault(match.group(1), []).append(match.group(2))
        return found

    def test_the_lock_file_is_there(self):
        self.assertTrue(self.lock, "native/ultron-core/Cargo.lock is missing: the build would not be reproducible")
        self.assertRegex(self.lock, r"(?m)^version = \d+$")

    def test_every_direct_dependency_is_locked_at_a_version_the_manifest_allows(self):
        direct = self.direct_dependencies()
        self.assertGreaterEqual(len(direct), 4, "the manifest was not read: the pattern no longer matches it")
        locked = self.locked()
        for name, requirement in direct.items():
            with self.subTest(dependency=name):
                self.assertIn(name, locked, f"{name} is in Cargo.toml but not in Cargo.lock: cargo would refuse --locked")
                parts = requirement.lstrip("^~=").split(".")
                prefix = ".".join(parts[:2] if parts[0] == "0" else parts[:1]) + "."
                self.assertTrue(any(version.startswith(prefix) for version in locked[name]),
                                f"{name} {requirement} does not allow any locked version {locked[name]}")

    def test_the_crate_itself_is_in_the_lock_at_its_manifest_version(self):
        name = re.search(r'(?m)^name\s*=\s*"([^"]+)"', self.manifest).group(1)
        version = re.search(r'(?m)^version\s*=\s*"([^"]+)"', self.manifest).group(1)
        self.assertIn(version, self.locked().get(name, []))


class TheRingHeaderMatchesThePythonReader(unittest.TestCase):
    """`core/audio_ring.py` reads the write cursor at byte 0 and the frames from byte `HEADER_BYTES`.

    The Rust header has to be exactly that long. It was 128 bytes, with 46 bytes of padding where 40 fit, and nothing
    noticed, because nothing had ever built it. Found on 2026-11-27 while reading the code before its first build.
    The layout is worked out here from the struct as written (Rust's `repr(C)` rules), so the fast gate catches a drift in
    seconds; the build check makes the compiler say the same, through a `const` assertion in the source.
    """

    SIZES = {"AtomicU64": (8, 8), "u64": (8, 8), "u32": (4, 4), "u16": (2, 2), "u8": (1, 1)}

    @classmethod
    def setUpClass(cls):
        cls.rust = text_of(CRATE / "src" / "audio" / "shared_ring.rs")
        cls.python = text_of(ROOT / "core" / "audio_ring.py")

    def layout(self) -> tuple[dict[str, int], int]:
        found = re.search(r"#\[repr\(C, align\((\d+)\)\)\]\s*pub struct RingHeader \{(.*?)\n\}", self.rust, re.S)
        self.assertTrue(found, "shared_ring.rs no longer declares RingHeader as repr(C, align(N))")
        alignment, body = int(found.group(1)), found.group(2)
        offset, offsets = 0, {}
        for name, kind in re.findall(r"(?m)^\s*(?:pub\s+)?(\w+):\s*([^,]+),", body):
            kind = kind.strip()
            padding = re.fullmatch(r"\[u8;\s*(\d+)\]", kind)
            size, align = (int(padding.group(1)), 1) if padding else self.SIZES[kind]
            offset = -(-offset // align) * align
            offsets[name] = offset
            offset += size
        return offsets, -(-offset // alignment) * alignment

    def python_constant(self, name: str) -> int:
        found = re.search(rf"(?m)^{name}\s*=\s*(\d+)\s*$", self.python)
        self.assertTrue(found, f"core/audio_ring.py no longer says {name} = <number>")
        return int(found.group(1))

    def rust_constant(self, name: str) -> int:
        found = re.search(rf"pub const {name}: usize = (\d+);", self.rust)
        self.assertTrue(found, f"shared_ring.rs no longer says pub const {name}: usize = <number>")
        return int(found.group(1))

    def test_the_header_is_exactly_as_long_as_the_python_reader_assumes(self):
        offsets, size = self.layout()
        self.assertEqual(size, self.python_constant("HEADER_BYTES"),
                         "the Rust header and core/audio_ring.py disagree about where the frames start")
        self.assertEqual(offsets["write_cursor"], 0, "the Python reader takes the write cursor from byte 0")

    def test_the_source_makes_the_compiler_say_the_same(self):
        self.assertRegex(self.rust, rf"const _: \(\) = assert!\(std::mem::size_of::<RingHeader>\(\) == {self.python_constant('HEADER_BYTES')}\);")
        self.assertRegex(self.rust, r"const _: \(\) = assert!\(std::mem::offset_of!\(RingHeader, write_cursor\) == 0\);")

    def test_the_two_ends_agree_on_the_frame_size_the_count_and_the_name(self):
        self.assertEqual(self.rust_constant("FRAME_SAMPLES"), self.python_constant("FRAME_SAMPLES"))
        self.assertEqual(self.rust_constant("CAPACITY_FRAMES"), self.python_constant("CAPACITY_FRAMES"))
        rust_name = re.search(r'pub const RING_NAME: &str = "([^"]+)";', self.rust)
        python_name = re.search(r'(?m)^RING_NAME = "([^"]+)"', self.python)
        self.assertTrue(rust_name and python_name)
        self.assertEqual(rust_name.group(1), python_name.group(1))


if __name__ == "__main__":
    unittest.main()
