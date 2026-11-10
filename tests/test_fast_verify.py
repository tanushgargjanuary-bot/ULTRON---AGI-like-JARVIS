"""Edge tests for the fast branch verification runner."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import fast_verify


class GitPathDecodingTests(unittest.TestCase):
    def test_decodes_spaces_and_unicode_without_splitting_paths(self):
        raw = "folder with spaces/café.py\0tests/test_one.py\0".encode("utf-8")
        self.assertEqual(
            fast_verify.decode_git_paths(raw),
            ["folder with spaces/café.py", "tests/test_one.py"],
        )

    def test_empty_inventory_is_valid_but_not_a_python_inventory(self):
        self.assertEqual(fast_verify.decode_git_paths(b""), [])

    def test_rejects_missing_nul_terminator(self):
        with self.assertRaisesRegex(ValueError, "NUL-terminated"):
            fast_verify.decode_git_paths(b"tests/test.py")

    def test_rejects_empty_path_entry(self):
        with self.assertRaisesRegex(ValueError, "empty path"):
            fast_verify.decode_git_paths(b"tests/test.py\0\0")

    def test_rejects_invalid_utf8(self):
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            fast_verify.decode_git_paths(b"bad-\xff.py\0")


class PythonPathBoundaryTests(unittest.TestCase):
    def test_resolves_valid_python_paths_and_ignores_other_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "folder with spaces" / "valid.py"
            source.parent.mkdir()
            source.write_text("value = 1\n", encoding="utf-8")
            result = fast_verify.resolve_python_files(
                root,
                ["README.md", "folder with spaces/valid.py"],
            )
            self.assertEqual(result, [source.resolve()])

    def test_rejects_path_traversal_and_absolute_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("../outside.py", "/tmp/outside.py", "C:/outside.py", "x\\..\\outside.py"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    fast_verify.resolve_python_files(root, [name])

    def test_rejects_duplicate_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "one.py"
            source.write_text("value = 1\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                fast_verify.resolve_python_files(root, ["one.py", "one.py"])

    def test_rejects_missing_python_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "missing"):
                fast_verify.resolve_python_files(Path(temporary), ["missing.py"])

    def test_rejects_symlinked_python_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            outside = Path(temporary) / "outside.py"
            outside.write_text("value = 1\n", encoding="utf-8")
            link = root / "linked.py"
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("This platform cannot create symlinks for this user")
            with self.assertRaisesRegex(ValueError, "symlink"):
                fast_verify.resolve_python_files(root, ["linked.py"])


class SyntaxValidationTests(unittest.TestCase):
    def test_accepts_valid_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "valid.py"
            source.write_text("def answer():\n    return 42\n", encoding="utf-8")
            self.assertEqual(fast_verify.syntax_errors(root, [source]), [])

    def test_reports_syntax_and_encoding_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            invalid = root / "invalid.py"
            invalid.write_text("def broken(:\n    pass\n", encoding="utf-8")
            bad_encoding = root / "encoding.py"
            bad_encoding.write_bytes(b"\xff\xfe\xfa")
            errors = fast_verify.syntax_errors(root, [invalid, bad_encoding])
            self.assertEqual(len(errors), 2)
            self.assertIn("invalid.py:", errors[0])
            self.assertIn("encoding.py:", errors[1])


class CommandExecutionTests(unittest.TestCase):
    def test_zero_exit_is_passed_without_a_shell(self):
        with (
            patch.object(fast_verify.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run,
            patch("builtins.print"),
        ):
            self.assertTrue(
                fast_verify.run_check(
                    "safe command",
                    ["python", "-c", "pass"],
                    root=ROOT,
                    env={"PYTHONDONTWRITEBYTECODE": "1"},
                    timeout=10,
                )
            )
        self.assertFalse(run.call_args.kwargs.get("shell", False))
        self.assertEqual(run.call_args.kwargs["timeout"], 10)

    def test_nonzero_exit_fails(self):
        with (
            patch.object(fast_verify.subprocess, "run", return_value=SimpleNamespace(returncode=7)),
            patch("builtins.print"),
        ):
            self.assertFalse(fast_verify.run_check("bad command", ["python", "-c", "raise"]))

    def test_timeout_fails_closed(self):
        with (
            patch.object(
                fast_verify.subprocess,
                "run",
                side_effect=fast_verify.subprocess.TimeoutExpired(cmd=["slow"], timeout=1),
            ),
            patch("builtins.print"),
        ):
            self.assertFalse(
                fast_verify.run_check("slow command", ["slow"], timeout=1)
            )

    def test_missing_executable_fails_closed(self):
        with (
            patch.object(
                fast_verify.subprocess,
                "run",
                side_effect=FileNotFoundError("missing runner"),
            ),
            patch("builtins.print"),
        ):
            self.assertFalse(fast_verify.run_check("missing command", ["missing"]))


if __name__ == "__main__":
    unittest.main()
