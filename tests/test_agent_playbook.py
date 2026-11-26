"""docs/reference/CODING_AGENT_PLAYBOOK.md: a playbook for coding agents that obeys its own rules.

The playbook this one replaces (a pasted "Vibe Coding Agent Master Playbook", 2026-11-26) broke its own rules in ways a
program can find: it set the file-length limit to 300 in two places and to 400 in three, called itself a "3-strike" rule
and rolled back after two, told agents never to run destructive git commands and then told them to run
`git checkout -- .`, banned placeholders and was full of them, gave statistics and credits that nobody could check, put
LaTeX in a file that agents read as plain text, and nested one code fence inside another so that the page broke.

These tests hold the replacement to the same standard:
* every number is defined once, in the thresholds table, and the rest of the file agrees with it;
* the always-loaded core is short, is free of one stack's vocabulary, and gives a reason for every rule;
* a destructive command appears only as something not to run;
* the file has no placeholder, no LaTeX, no unbalanced or nested fence, no statistic that nobody measured;
* every skill has the same four parts, and its description says when to use it (Anthropic's skill guide: the
  description is the trigger);
* every source is marked verified or not verified, and a verified source names its commit or date. The commits are
  compared with the ones recorded in docs/UPSTREAM_RESEARCH.md, section 11, which was written from the same reads.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "reference" / "CODING_AGENT_PLAYBOOK.md"
RESEARCH = ROOT / "docs" / "UPSTREAM_RESEARCH.md"
INDEX = ROOT / "docs" / "INDEX.md"

WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
         11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen", 16: "sixteen"}
PARTS = ("0", "1", "2", "3", "4", "5", "6", "7", "8", "A", "B", "C")
NEEDED = ("core_block_max_lines", "core_block_max_chars", "skill_body_max_lines", "new_file_target_lines",
          "new_file_split_lines", "slice_max_files", "fix_attempts", "checkpoint_tool_calls",
          "checkpoint_context_percent", "command_timeout_quick_s", "command_timeout_build_s")
STACK_WORDS = ("Zod", "Pydantic", "Prisma", "Drizzle", "Supabase", "RLS", "Next.js", "Tailwind", "shadcn", "npm ", "pnpm", "ESLint")
PROHIBITION = re.compile(r"(?i)\b(never|do not|don't|not|no|unprompted|instead|banned|forbidden|refuse|refuses)\b")
DESTRUCTIVE = (r"git reset --hard", r"git clean\b", r"git checkout -- \.", r"git restore \.", r"push --force\b",
               r"push -f\b", r"rm -rf", r"git add \.", r"git add -A", r"curl [^\n]*\| *sh", r"npx -y")
PLACEHOLDERS = re.compile(r"\b(TODO|TBD|FIXME|XXX)\b|implement later|lorem ipsum", re.IGNORECASE)
REMOVED_CLAIMS = (r"\b\d+x\b", r"#1 voted", r"Swarm Architecture", r"triple_pass", r"branch-reviewer")


def read() -> str:
    return DOC.read_text(encoding="utf-8")


def sections(text: str) -> dict[str, str]:
    """{part: body}. A heading inside a code fence is not a heading: a template can hold lines that start with `## `."""
    found: dict[str, str] = {}
    key, buffer = None, []
    for line, fenced in fenced_lines(text):
        head = None if fenced else re.match(r"^## (?:(\d+)|Appendix ([A-C]))\.", line)
        if head:
            if key:
                found[key] = "\n".join(buffer) + "\n"
            key, buffer = head.group(1) or head.group(2), []
        elif key:
            buffer.append(line)
    if key:
        found[key] = "\n".join(buffer) + "\n"
    return found


def thresholds(text: str) -> dict[str, float]:
    body = sections(text).get("0", "")
    return {m.group(1): float(m.group(2)) for m in re.finditer(r"(?m)^\| `([a-z_]+)` \| (\d+(?:\.\d+)?) \|", body)}


def core_block(text: str) -> str:
    found = re.search(r"<!-- core:start -->\n(.*?)<!-- core:end -->", text, re.DOTALL)
    return found.group(1) if found else ""


def without_history(text: str) -> str:
    """The text with the thresholds table, the sources and the change list removed: they quote numbers on purpose."""
    kept = {key: body for key, body in sections(text).items() if key not in ("A", "C")}
    kept["0"] = re.sub(r"(?m)^\|.*\n", "", kept.get("0", ""))
    return "\n".join(kept.values())


def fenced_lines(text: str) -> list[tuple[str, bool]]:
    """[(line, inside a fence)] by CommonMark's rule: a fence closes with the same character, at least as long."""
    result, opened = [], 0
    for line in text.splitlines():
        fence = re.match(r"^(`{3,})(.*)$", line)
        if opened and fence and len(fence.group(1)) >= opened and not fence.group(2).strip():
            result.append((line, True))
            opened = 0
        elif not opened and fence:
            result.append((line, True))
            opened = len(fence.group(1))
        else:
            result.append((line, bool(opened)))
    return result


def sources(text: str) -> list[list[str]]:
    body = sections(text).get("A", "")
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in body.splitlines() if line.startswith("| ")]
    return [row for row in rows if len(row) == 4 and row[0] != "Source" and not set(row[0]) <= set("- ")]


def recorded_commits() -> dict[str, str]:
    """{repository: first 10-hex commit} from the table in section 11.1 of docs/UPSTREAM_RESEARCH.md."""
    found: dict[str, str] = {}
    text = RESEARCH.read_text(encoding="utf-8")
    block = text.split("### 11.1", 1)[1].split("### 11.2", 1)[0]
    for line in block.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        sha = re.search(r"\b[0-9a-f]{10}\b", cells[4]) if len(cells) > 4 else None
        if line.startswith("| `") and sha:
            found[cells[0].strip("`")] = sha.group(0)
    return found


class TheFileIsThere(unittest.TestCase):
    def test_it_has_all_its_parts(self):
        self.assertTrue(DOC.is_file(), "docs/reference/CODING_AGENT_PLAYBOOK.md is missing")
        self.assertEqual([p for p in PARTS if p not in sections(read())], [])

    def test_it_is_listed_in_the_documentation_index(self):
        self.assertIn("CODING_AGENT_PLAYBOOK.md", INDEX.read_text(encoding="utf-8"))

    def test_it_says_the_repository_wins_over_the_playbook(self):
        self.assertRegex(core_block(read()), r"(?i)repository wins")


class EveryNumberIsDefinedOnce(unittest.TestCase):
    def test_the_thresholds_table_has_every_name(self):
        self.assertEqual([n for n in NEEDED if n not in thresholds(read())], [])

    def test_a_limit_stated_in_the_text_is_one_the_table_defines(self):
        values = {int(v) for v in thresholds(read()).values()}
        for number, unit in re.findall(r"\b(\d[\d,]*)\s+(lines|characters|files|tool calls|seconds|percent)\b", without_history(read())):
            with self.subTest(limit=f"{number} {unit}"):
                self.assertIn(int(number.replace(",", "")), values, f"{number} {unit} is not in the thresholds table")

    def test_the_two_file_limits_are_not_confused(self):
        table = thresholds(read())
        self.assertLess(table["new_file_target_lines"], table["new_file_split_lines"])


class TheCoreIsShortAndGivesReasons(unittest.TestCase):
    def test_it_fits_its_budget(self):
        core, table = core_block(read()), thresholds(read())
        self.assertTrue(core, "no core block between the markers")
        self.assertLessEqual(len(core.strip().splitlines()), table["core_block_max_lines"])
        self.assertLessEqual(len(core), table["core_block_max_chars"])

    def test_every_numbered_rule_gives_a_reason(self):
        rules = re.findall(r"(?m)^\d+\. .*$", core_block(read()))
        self.assertGreaterEqual(len(rules), 10)
        for rule in rules:
            with self.subTest(rule=rule[:40]):
                self.assertIn("Reason:", rule)

    def test_it_belongs_to_no_one_stack(self):
        core = core_block(read())
        self.assertEqual([word for word in STACK_WORDS if word in core], [])

    def test_the_section_that_introduces_it_counts_its_rules_correctly(self):
        """v1 and the first draft of v2 each described their own size wrongly in the text that introduces it."""
        said = re.search(r"\*\*Core\*\* \(section 1\)\. (\w+) rules", sections(read())["0"])
        self.assertTrue(said, "section 0 no longer says how many rules the core has")
        rules = len(re.findall(r"(?m)^\d+\. ", core_block(read())))
        self.assertEqual(said.group(1).lower(), WORDS.get(rules), f"the core has {rules} rules")

    def test_the_numbers_in_it_are_the_tables(self):
        values = {int(v) for v in thresholds(read()).values()}
        for number in re.findall(r"\b(\d+)\s+(?:lines|files|seconds|percent|tool calls)\b", core_block(read())):
            self.assertIn(int(number), values)


class TheAttemptBudgetIsTheSameEverywhere(unittest.TestCase):
    """v1 called it a 3-strike rule and rolled back after two. The budget is a number in the table and a word in the text."""

    def test_the_core_and_the_fix_section_say_what_the_table_says(self):
        word = WORDS[int(thresholds(read())["fix_attempts"])]
        rule = next((r for r in re.findall(r"(?m)^\d+\. .*$", core_block(read())) if "Debug from a loop" in r), "")
        self.assertRegex(rule.lower(), rf"after {word} failed fixes")
        self.assertRegex(sections(read())["7"].lower(), rf"you have {word} fix attempts")


class ThePlaybookFollowsItsOwnRules(unittest.TestCase):
    def test_a_destructive_command_appears_only_as_something_not_to_run(self):
        in_never_table = False
        for line, fenced in fenced_lines(without_history(read())):
            if line.startswith("|"):
                in_never_table = in_never_table or "Never run" in line
            else:
                in_never_table = False
            for pattern in DESTRUCTIVE:
                if re.search(pattern, line) and not fenced:
                    with self.subTest(line=line[:70]):
                        self.assertTrue(in_never_table or PROHIBITION.search(line), f"offered as advice: {line}")

    def test_it_has_no_placeholder_of_its_own(self):
        for line, fenced in fenced_lines(without_history(read())):
            if PLACEHOLDERS.search(line) and not fenced:
                with self.subTest(line=line[:70]):
                    self.assertTrue(PROHIBITION.search(line), f"a placeholder: {line}")

    def test_it_has_no_math_markup(self):
        self.assertIsNone(re.search(r"\$[^$\n]+\$", read()), "LaTeX in a file that agents read as plain text")

    def test_every_fence_closes_and_none_is_nested(self):
        text, opened = read(), 0
        for line in text.splitlines():
            fence = re.match(r"^(`{3,})(.*)$", line)
            if not fence:
                continue
            if opened and len(fence.group(1)) >= opened and not fence.group(2).strip():
                opened = 0
            elif opened and len(fence.group(1)) == opened:
                self.fail(f"a fence of the same length opens inside another: {line}")
            elif not opened:
                opened = len(fence.group(1))
        self.assertEqual(opened, 0, "a code fence is never closed")

    def test_nothing_unsourced_from_the_old_playbook_came_back(self):
        text = without_history(read())
        for pattern in REMOVED_CLAIMS:
            with self.subTest(claim=pattern):
                self.assertIsNone(re.search(pattern, text), f"an unverified claim is back: {pattern}")


class EverySkillHasTheSameFourParts(unittest.TestCase):
    def skills(self) -> dict[str, str]:
        found = {}
        for block in re.split(r"(?m)^### ", sections(read()).get("4", ""))[1:]:
            name, _, body = block.partition("\n")
            found[name.strip()] = body
        return found

    def test_there_are_skills_with_proper_names(self):
        names = list(self.skills())
        self.assertGreaterEqual(len(names), 10)
        for name in names:
            self.assertRegex(name, r"^[a-z]+(?:-[a-z]+)*$")

    def test_each_has_description_do_done_when_and_never(self):
        for name, body in self.skills().items():
            for part in ("description:", "Do:", "Done when:", "Never:"):
                with self.subTest(skill=name, part=part):
                    self.assertRegex(body, rf"(?m)^{re.escape(part)}")

    def test_a_description_says_when_to_use_it_and_stays_short(self):
        for name, body in self.skills().items():
            description = re.search(r"(?m)^description:\s*(.*)$", body)
            with self.subTest(skill=name):
                self.assertTrue(description)
                self.assertRegex(description.group(1).lower(), r"\buse (when|whenever|before|after|for)\b")
                self.assertLessEqual(len(description.group(1).split()), 100)

    def test_a_skill_stays_within_its_budget(self):
        limit = thresholds(read())["skill_body_max_lines"]
        for name, body in self.skills().items():
            with self.subTest(skill=name):
                self.assertLessEqual(len([line for line in body.splitlines() if line.strip()]), limit)


class EverySourceIsMarkedAndTheCommitsAgree(unittest.TestCase):
    def test_each_row_says_verified_or_not_verified(self):
        rows = sources(read())
        self.assertGreaterEqual(len(rows), 8)
        for row in rows:
            with self.subTest(source=row[0][:40]):
                self.assertRegex(row[2].lower(), r"^(not verified|verified)")

    def test_a_verified_source_names_a_commit_or_a_date(self):
        for row in sources(read()):
            if row[2].lower().startswith("verified"):
                with self.subTest(source=row[0][:40]):
                    self.assertRegex(row[3], r"\b[0-9a-f]{10}\b|\d{4}-\d{2}-\d{2}")

    def test_a_commit_given_here_is_the_one_recorded_in_the_research_log(self):
        recorded = recorded_commits()
        for row in sources(read()):
            repo = re.search(r"`([\w.-]+/[\w.-]+)`", row[0])
            if repo and repo.group(1) in recorded:
                with self.subTest(repository=repo.group(1)):
                    self.assertIn(recorded[repo.group(1)], row[3])


if __name__ == "__main__":
    unittest.main()
