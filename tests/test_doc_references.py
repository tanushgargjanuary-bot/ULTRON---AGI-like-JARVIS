"""A document that tells you where something is must be right about where it is.

`DECISIONS.md` named eight test files that do not exist (the suite was consolidated into
`tests/test_suite_*.py`), `ARCHITECTURE.md` named a test and a `core/evidence*` module that do
not exist, and three guides named tests that were merged. A reader following "enforced by
`tests/test_x.py`" and finding nothing concludes the rule is not enforced. This checks the
documents that describe the present state of the tree; history, plans and specifications are
left out on purpose, because they are allowed to name files that were or will be.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

LIVING_DOCS = (
    "ARCHITECTURE.md", "DECISIONS.md", "AGENTS.md", "GATEKEEPERS.md", "WORKING-PHILOSOPHY.md",
    "docs/AGENT_MAINTENANCE.md", "docs/DEEP-SCAN.md", "docs/HEALTH_CENTER.md", "docs/INDEX.md",
    "docs/INSTALL.md", "docs/NEXT_CHECKPOINTS.md", "docs/PERFORMANCE.md", "docs/PROMPT.md",
    "docs/SELF-CHANGE.md", "docs/TEST_AUTOMATION.md", "docs/TOOL_SUGGESTIONS.md",
    "docs/reference/CUSTOM_ULTRON.md", "docs/specifications/SYSTEM_OVERVIEW.md",
)

# Files that exist on a running installation or are examples of a name, not files of the repo.
CREATED_AT_RUNTIME = {
    "config/api_keys.json", "memory/long_term.json", "state/active_plan.json",
    "plugins/_helper.py",       # AGENTS.md: the shape of a helper module's name
    "verification/deep-scan.json",   # written by `scripts/deep_scan.py --json`; the folder is ignored
}

REFERENCE = re.compile(
    r"`((?:[\w.-]+/)+[\w.-]+\.(?:py|md|json|jsonl|txt|yml|yaml|rs|go|toml|ps1|bat|html|js|ts|"
    r"tsx|fbs|ico|png|gif|iss))(?::[\w.]+|:\d+(?:-\d+)?)?`")


def references(text: str):
    for number, line in enumerate(text.splitlines(), start=1):
        for found in REFERENCE.finditer(line):
            path = found.group(1)
            if any(mark in path for mark in "*<>{}") or path.startswith(("http", "~")):
                continue
            yield number, path


class DocumentsNameRealFiles(unittest.TestCase):
    def test_the_list_of_documents_is_current(self):
        missing = [name for name in LIVING_DOCS if not (ROOT / name).is_file()]
        self.assertEqual(missing, [], "a document in this list was renamed or removed")

    def test_every_path_a_document_names_exists(self):
        broken = []
        for name in LIVING_DOCS:
            document = ROOT / name
            for number, path in references(document.read_text(encoding="utf-8", errors="replace")):
                if path in CREATED_AT_RUNTIME:
                    continue
                if (ROOT / path).exists() or (document.parent / path).exists():
                    continue
                broken.append(f"{name}:{number}: {path}")
        self.assertEqual(broken, [], "these documents point at files that are not there")

    def test_the_runtime_exceptions_are_still_mentioned_somewhere(self):
        # An allowance nobody uses is a hole waiting for a real mistake.
        combined = "\n".join((ROOT / name).read_text(encoding="utf-8", errors="replace")
                             for name in LIVING_DOCS)
        for path in sorted(CREATED_AT_RUNTIME):
            with self.subTest(path=path):
                self.assertIn(f"`{path}", combined)

    def test_the_pattern_catches_what_it_is_for(self):
        found = list(references("see `tests/test_gone.py:Cls` and `core/a.py:12-14` and `x/y*.py`"))
        self.assertEqual([path for _n, path in found], ["tests/test_gone.py", "core/a.py"])


class TheChangelogKnowsTheVersion(unittest.TestCase):
    """CHANGELOG.md stopped at 1.2.36 while `packaging/version.txt` said 1.2.38."""

    def test_the_current_version_is_mentioned(self):
        version = (ROOT / "packaging" / "version.txt").read_text(encoding="utf-8").strip()
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(version, changelog,
                      f"packaging/version.txt is {version} and CHANGELOG.md never says so")


if __name__ == "__main__":
    unittest.main()
