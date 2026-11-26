"""What the owner took out stays out.

2026-11-26, the owner: "I did meant the webapp. Remove the dashboard for phone and web remote."

A removal that is only a deleted folder comes back by accident: a merge from upstream, an old branch, a
document that still says to run it, a workflow that still builds it. Each removal gets one class here, red while
the folder or anything that points at it is still in the tree. Bringing a feature back is a decision: revert the
merge that removed it (DECISIONS.md names the merge), and that revert takes the class below out with it.
"""

from __future__ import annotations

import ast
import fnmatch
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def text_of(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def requirement_names() -> set[str]:
    names = set()
    for line in text_of(ROOT / "requirements.txt").splitlines():
        line = line.split("#")[0].strip()
        if line:
            names.add(re.split(r"[\s<>=!~;\[]", line, maxsplit=1)[0].lower())
    return names


def imported_top_level_names() -> dict[str, list[str]]:
    """Every top-level module name that the program's own Python files import, with where. The tests are left out:
    they are allowed to name what is gone."""
    skip = {"tests", ".git", ".venv", "venv", "node_modules", "__pycache__", ".ruff_cache", "copies"}
    found: dict[str, list[str]] = {}
    for path in sorted(ROOT.rglob("*.py")):
        relative = path.relative_to(ROOT)
        if skip & set(relative.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            else:
                continue
            for name in names:
                found.setdefault(name, []).append(f"{relative.as_posix()}:{node.lineno}")
    return found


class TheWebClientIsGone(unittest.TestCase):
    """`webapp/`: a Next.js sign-in page with a chat box that was switched off, never connected to Ultron."""

    def test_the_folder_is_gone(self):
        self.assertFalse((ROOT / "webapp").exists(),
                         "webapp/ was removed at the owner's request; revert the removal to get it back")

    def test_no_workflow_is_left_that_builds_it(self):
        self.assertFalse((WORKFLOWS / "webapp.yml").exists())
        for path in sorted(WORKFLOWS.glob("*.yml")):
            with self.subTest(workflow=path.name):
                self.assertNotIn("webapp", text_of(path))

    def test_dependabot_is_not_told_to_watch_it(self):
        text = text_of(ROOT / ".github" / "dependabot.yml")
        self.assertNotIn('package-ecosystem: "npm"', text)
        self.assertNotIn("webapp", text)

    def test_the_attributes_file_does_not_name_it(self):
        self.assertNotIn("webapp", text_of(ROOT / ".gitattributes"))


class ThePhoneAndWebRemoteIsGone(unittest.TestCase):
    """`dashboard/`: a web server inside the program with pairing keys, a certificate maker, a Windows firewall opener,
    a QR-code window and a relay for the phone's microphone."""

    # What only the dashboard (and the one window that paired a phone) imported. `yaml` is not here on purpose: it
    # arrived with uvicorn and the code checks use it, so it is declared by name instead (see below).
    ONLY_THE_DASHBOARD_NEEDED = ("dashboard", "fastapi", "uvicorn", "starlette", "multipart", "python_multipart",
                                 "qrcode", "dotenv", "uvloop", "httptools", "watchfiles")

    def test_the_folder_and_its_guide_are_gone(self):
        self.assertFalse((ROOT / "dashboard").exists(),
                         "dashboard/ was removed at the owner's request; revert the removal to get it back")
        self.assertFalse((ROOT / "docs" / "REMOTE_DASHBOARD.md").exists())

    def test_nothing_in_the_program_imports_it_or_what_only_it_needed(self):
        found = imported_top_level_names()
        for name in self.ONLY_THE_DASHBOARD_NEEDED:
            with self.subTest(module=name):
                self.assertEqual(found.get(name, []), [], f"{name} is imported again")

    def test_the_requirements_no_longer_ask_for_its_packages(self):
        names = requirement_names()
        self.assertTrue(names, "no requirement was read: the parser no longer matches the file")
        for name in ("fastapi", "uvicorn", "python-multipart", "qrcode"):
            with self.subTest(package=name):
                self.assertNotIn(name, names)

    def test_pyyaml_is_declared_because_the_code_checks_import_it(self):
        # `uvicorn[standard]` used to bring PyYAML in without anyone asking. core/code_checks.py reads .yml files with it
        # and skips them silently when it is missing, so a fresh install without the line would stop checking them.
        self.assertIn("import yaml", text_of(ROOT / "core" / "code_checks.py"),
                      "the code checks no longer use PyYAML: this test and the requirement can go")
        self.assertIn("pyyaml", requirement_names())

    def test_upstream_is_told_to_leave_its_dashboard_alone(self):
        # A new Mark will go on changing its dashboard. The ledger decides every file of it `rejected`, so the weekly
        # report names the change and never offers it, and E4 keeps the dashboard's names out of Ultron's own code.
        ledger = json.loads(text_of(ROOT / "docs" / "upstream" / "LEDGER.json"))
        for name in ("dashboard/__init__.py", "dashboard/server.py", "dashboard/static/app.html"):
            with self.subTest(file=name):
                first = next((entry for entry in ledger["entries"]
                              if any(fnmatch.fnmatchcase(name, pattern) for pattern in entry["paths"])), None)
                self.assertIsNotNone(first, f"{name} has no decision in the ledger, so it would be reported as held")
                self.assertEqual(first["disposition"], "rejected")
        exclusions = json.loads(text_of(ROOT / "docs" / "upstream" / "EXCLUSIONS.json"))
        self.assertIn("E4", {item["id"] for item in exclusions["exclusions"]})

    def test_packaging_does_not_ship_it(self):
        listed = [line.strip() for line in text_of(ROOT / "packaging" / "payload.txt").splitlines()]
        self.assertTrue(listed, "payload.txt was not read")
        self.assertNotIn("dashboard/", listed)

    def test_an_old_certificate_can_never_be_committed(self):
        # The removed server made a private key in config/certs/ on any install that turned HTTPS on. Nothing makes it
        # now and nothing deletes it, so the ignore line stays.
        ignored = [line.strip() for line in text_of(ROOT / ".gitignore").splitlines()]
        self.assertIn("config/certs/", ignored)


if __name__ == "__main__":
    unittest.main()
