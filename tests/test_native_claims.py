"""What the documents say about the native core must match what the native core does.

`docs/specifications/AUTONOMOUS_EVOLUTION_SPEC.md` describes a Rust supervisor with a
watchdog, a boot-loop guard, git rollback, blue/green swaps, a job-object sandbox and a
"hardware" referee seal. `native/ultron-core/src/main.rs` starts the audio ring and the IPC
server and nothing else; the rest is library code nobody calls. The document now says so
under "Status of this document", and these tests keep that statement true in both
directions. The native build check compiles and tests the crate and starts it, but it cannot say which modules
`main.rs` starts, so that is still checked on the source.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CRATE = ROOT / "native" / "ultron-core"
SPEC = ROOT / "docs" / "specifications" / "AUTONOMOUS_EVOLUTION_SPEC.md"
MARKER = "NOT started by\n  `main.rs`"        # as wrapped in the spec

# Modules the spec describes as running, and the names that would show main.rs using one.
UNWIRED = {
    "watchdog": ("watchdog", "BootLoopGuard", "boot_guard"),
    "git recovery": ("git::", "GitRecovery", "rollback_to_verified_tag"),
    "blue/green": ("orchestrator", "BlueGreenOrchestrator"),
    "job object sandbox": ("process::", "SandboxJob"),
    "vision capture": ("vision::", "ScreenCapture", "capture_frame"),
    "referee sealer": ("integrity", "RefereeSealer"),
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text)


class TheStatusParagraphMatchesMain(unittest.TestCase):
    def setUp(self):
        self.main = read(CRATE / "src" / "main.rs")
        self.spec = read(SPEC)

    def wired(self):
        found = []
        for module, names in UNWIRED.items():
            if any(name in self.main for name in names):
                found.append(module)
        return found

    def test_the_spec_says_what_main_starts_and_that_is_still_all(self):
        self.assertIn("Status of this document", self.spec)
        self.assertIn("SharedAudioRing", self.main)
        self.assertIn("start_ipc_server", self.main)

    def test_the_unwired_claim_is_true_or_the_paragraph_is_gone(self):
        says_unwired = squash(MARKER) in squash(self.spec)
        wired = self.wired()
        if wired:
            self.assertFalse(
                says_unwired,
                f"main.rs now uses {wired}, but the spec still says they are not started by "
                "main.rs: update 'Status of this document'")
        else:
            self.assertTrue(
                says_unwired,
                "main.rs starts none of the watchdog, recovery, orchestrator, sandbox, "
                "vision or sealer modules, and the spec no longer says so")

    def test_every_module_the_paragraph_names_exists(self):
        for relative in ("watchdog/boot_guard.rs", "git/recovery.rs", "orchestrator/blue_green.rs",
                         "process/supervisor.rs", "vision/capture.rs",
                         "integrity/referee_sealer.rs", "ipc/server.rs"):
            with self.subTest(module=relative):
                self.assertTrue((CRATE / "src" / relative).is_file())

    def test_the_server_keeps_no_clock_so_it_cannot_end_a_stalled_worker(self):
        server = read(CRATE / "src" / "ipc" / "server.rs")
        for word in ("Instant", "timeout", "HEARTBEAT_TIMEOUT", "sleep"):
            self.assertNotIn(word, server,
                             f"server.rs now uses {word}; if it tracks heartbeats, the spec's "
                             "'nothing terminates a stalled worker' sentence needs revisiting")


class TheSealerIsNotDescribedAsMoreThanItIs(unittest.TestCase):
    def test_its_comments_say_experimental_and_constant_key(self):
        source = read(CRATE / "src" / "integrity" / "referee_sealer.rs")
        self.assertIn("EXPERIMENTAL", source)
        self.assertIn("NOT hardware-bound", source)
        self.assertNotIn("Computes a 256-bit HMAC tag", source)
        self.assertNotIn("Derives a consistent hardware-bound seed", source)

    def test_the_key_really_is_a_constant(self):
        # The claim in the comments: the key does not depend on the machine. If the
        # function starts reading anything from the machine, the comments are stale.
        source = read(CRATE / "src" / "integrity" / "referee_sealer.rs")
        body = source[source.index("pub fn from_device_context"):source.index("pub fn compute_tag")]
        for machine_source in ("env::var", "GetComputerName", "hostname", "CryptProtectData",
                               "MachineGuid", "std::env"):
            self.assertNotIn(machine_source, body)


class ThePipeNameIsOneName(unittest.TestCase):
    """Python, Rust and every document that names the pipe use the same name."""

    def test_python_and_rust_agree(self):
        from core import ipc_client
        rust = read(CRATE / "src" / "ipc" / "server.rs")
        found = re.search(r'PIPE_NAME: &str = r"([^"]+)"', rust)
        self.assertIsNotNone(found)
        self.assertEqual(found.group(1), ipc_client.PIPE_PATH)

    def test_no_document_names_a_pipe_that_does_not_exist(self):
        allowed = r"ultron-core"
        offenders = []
        documents = [*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md")]
        history = {"log.txt", "HANDOFF.md", "verification-results.txt", "GITHUB_AWESOME_CATALOG.md"}
        for path in documents:
            if path.name in history:
                continue
            for number, line in enumerate(read(path).splitlines(), start=1):
                for name in re.findall(r"pipe\\+(ultron[\w-]*)", line):
                    if name != allowed:
                        offenders.append(f"{path.relative_to(ROOT)}:{number}: {name}")
        self.assertEqual(offenders, [], "the pipe is \\\\.\\pipe\\ultron-core")


if __name__ == "__main__":
    unittest.main()
