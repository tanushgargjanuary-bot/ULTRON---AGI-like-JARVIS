"""GLOSSARY.md: the words the owner reads, defined once, in plain words.

The owner asked for plain words three times (docs/MAINTAINERS.md) and kept meeting words nobody had defined. The glossary
follows the format of the `domain-modeling` skill in Matt Pocock's skills repository (MIT licence): a bold term, a short
definition, and an `_Avoid_` line for the words not to use.

These tests tie it to the program, so that it cannot drift from the words the program itself prints: the verdicts of the
proof gate, the decision words of the follow-up watch, the ids of the excluded features. Each is read from its own source,
not typed again here, so that a word added there and not here fails. They also hold the file to its own rules: a term is
defined once, a sentence is short, and no definition names a file or a command. A glossary says what a word means, not
how the code works.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GLOSSARY = ROOT / "GLOSSARY.md"
MAX_WORDS = 25      # ASD-STE100, the Simplified Technical English the owner asked for: a descriptive sentence has at most 25.


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_for_the_glossary", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read() -> str:
    return GLOSSARY.read_text(encoding="utf-8")


def sections(text: str) -> dict[str, str]:
    """{heading: body} for each `## ` heading."""
    found: dict[str, str] = {}
    for part in re.split(r"(?m)^## ", text)[1:]:
        heading, _, body = part.partition("\n")
        found[heading.strip()] = body
    return found


def terms(text: str) -> list[tuple[str, str, list[str]]]:
    """(term, definition, avoided words) for every `**Term**:` line in the Language section."""
    found: list[list] = []
    for line in sections(text).get("Language", "").splitlines():
        head = re.match(r"^\*\*(.+?)\*\*:\s*$", line)
        if head:
            found.append([head.group(1), [], []])
        elif found and line.startswith("_Avoid_:"):
            found[-1][2] = [word.strip() for word in line[len("_Avoid_:"):].split(",") if word.strip()]
        elif found and line.strip() and not line.startswith("#"):
            found[-1][1].append(line.strip())
    return [(term, " ".join(lines), avoided) for term, lines, avoided in found]


class TheGlossaryIsThere(unittest.TestCase):
    def test_it_exists_with_its_three_parts(self):
        self.assertTrue(GLOSSARY.is_file(), "GLOSSARY.md is missing")
        for heading in ("Language", "Relationships", "Flagged ambiguities"):
            with self.subTest(heading=heading):
                self.assertIn(heading, sections(read()))

    def test_it_defines_something(self):
        self.assertGreaterEqual(len(terms(read())), 20)

    def test_every_term_has_a_definition(self):
        for term, definition, _ in terms(read()):
            with self.subTest(term=term):
                self.assertTrue(definition, f"{term} has no definition")

    def test_a_term_is_defined_once(self):
        names = [term.lower() for term, _, _ in terms(read())]
        self.assertEqual([n for n in names if names.count(n) > 1], [])

    def test_a_word_to_avoid_is_not_itself_a_term(self):
        defined = {term.lower() for term, _, _ in terms(read())}
        for term, _, avoided in terms(read()):
            for word in avoided:
                with self.subTest(term=term, avoided=word):
                    self.assertNotIn(word.lower(), defined, f"{word} is avoided under {term} and defined as a term")


class TheWordsTheProgramPrints(unittest.TestCase):
    """Each list is read from the code that prints it, so a word added there and not here fails here."""

    @classmethod
    def setUpClass(cls):
        cls.terms = {term: definition for term, definition, _ in terms(read())} if GLOSSARY.is_file() else {}

    def test_every_verdict_the_proof_gate_can_print_is_defined(self):
        gate = load_script("proof_gate")
        printed = {gate.PROVEN, gate.FAILED, gate.MISSING, gate.SKIPPED}
        source = (ROOT / "scripts" / "proof_gate.py").read_text(encoding="utf-8")
        self.assertIn('return "PARTIAL"', source, "the gate no longer returns PARTIAL: the glossary list is out of date")
        printed.add("PARTIAL")                  # the one verdict the gate writes as a bare string
        for verdict in sorted(printed):
            with self.subTest(verdict=verdict):
                self.assertIn(verdict, self.terms, f"the proof gate can print {verdict} and the glossary does not define it")

    def test_every_decision_word_of_the_follow_up_watch_is_defined(self):
        watch = load_script("upstream_sync")
        definition = self.terms.get("Decision word", "")
        self.assertTrue(definition, "no term `Decision word`")
        for word in watch.DISPOSITIONS:
            with self.subTest(word=word):
                self.assertRegex(definition, rf"(?i)\b{re.escape(word)}\b")
        self.assertIn("Held", self.terms, "a change nobody has decided about is reported as held, and `Held` is not defined")

    def test_every_excluded_feature_is_named(self):
        data = json.loads((ROOT / "docs" / "upstream" / "EXCLUSIONS.json").read_text(encoding="utf-8"))
        definition = self.terms.get("Excluded feature", "")
        self.assertTrue(definition, "no term `Excluded feature`")
        for entry in data["exclusions"]:
            with self.subTest(id=entry["id"]):
                self.assertIn(entry["id"], definition)


class ThePlainWordsRules(unittest.TestCase):
    def test_no_sentence_is_longer_than_the_limit(self):
        text = read()
        for line in text.splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            prose = re.sub(r"[*_]", "", re.sub(r"^\s*[-*]\s+", "", line))
            for sentence in re.split(r"(?<=[.!?])\s+", prose.strip()):
                with self.subTest(sentence=sentence[:60]):
                    self.assertLessEqual(len(sentence.split()), MAX_WORDS, f"{len(sentence.split())} words: {sentence}")

    def test_no_definition_names_a_file_or_a_command(self):
        text = read()
        self.assertNotIn("`", text, "a glossary names no command and no code")
        self.assertNotRegex(text, r"\.(py|md|json|yml|yaml|bat|ps1|txt)\b", "a glossary names no file")


class ItIsFoundWhereAReaderStarts(unittest.TestCase):
    def test_the_starting_documents_point_to_it(self):
        for name in ("WORKING-PHILOSOPHY.md", "AGENTS.md", "docs/INDEX.md"):
            with self.subTest(document=name):
                self.assertIn("GLOSSARY.md", (ROOT / name).read_text(encoding="utf-8"), f"{name} does not point to GLOSSARY.md")


if __name__ == "__main__":
    unittest.main()
