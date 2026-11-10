"""test_suite_assistant.py — one suite file for 8 areas.

Each section below was its own test module and is kept whole, with its
header, its helpers and its tests. They were combined because the project
had sixty-five test modules of one or two hundred lines each, and a file
count that size hides the structure instead of showing it. Nothing was
removed; a name that appeared in two sections was given a suffix.

Sections:
  * test_failures.py
  * test_deep_scan.py
  * test_identity_voice.py
  * test_startup_paths.py
  * test_insights.py
  * test_digest.py
  * test_performance_budget.py
  * test_first_run.py
"""

from __future__ import annotations
import sys
import unittest
from pathlib import Path
from core import failures
import tempfile
import textwrap
from unittest.mock import patch
from core import identity, voice_style
import ast
import json
from types import SimpleNamespace
from actions import system_monitor
from core.insights import InsightEngine
from custom_jarvis.service import CustomService
import os
import socket
import subprocess
import time
from datetime import datetime
from unittest import mock
from core import digest
import statistics
from memory import config_manager as cm



# ══════════════════════════════════════════════════════════════════════════
# from test_failures.py
# ══════════════════════════════════════════════════════════════════════════
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import failures


class TheNoteTaker(unittest.TestCase):
    def setUp(self):
        failures.clear()

    def tearDown(self):
        failures.clear()

    def test_it_records_what_was_caught_and_where(self):
        try:
            raise PermissionError("the window will not take focus")
        except Exception as error:
            failures.note("appidentity.focus", error)
        trail = failures.recent()
        self.assertEqual(len(trail), 1)
        self.assertEqual(trail[0]["where"], "appidentity.focus")
        self.assertEqual(trail[0]["kind"], "PermissionError")
        self.assertIn("focus", trail[0]["error"])

    def test_a_note_carries_the_line_it_came_from(self):
        # A trail without a line number is a rumour.
        try:
            raise ValueError("bad")
        except Exception as error:
            failures.note("somewhere", error)
        self.assertTrue(failures.recent()[-1]["at"])

    def test_it_accepts_a_sentence_instead_of_an_exception(self):
        failures.note("boot", "the sidecar was missing")
        entry = failures.recent()[-1]
        self.assertEqual(entry["kind"], "Message")
        self.assertEqual(entry["error"], "the sidecar was missing")

    def test_it_never_raises_even_when_the_error_is_hostile(self):
        class Hostile(Exception):
            def __str__(self):
                raise RuntimeError("no")

        failures.note("hostile", Hostile())        # must not raise
        self.assertEqual(failures.recent(), [])

    def test_the_trail_is_bounded(self):
        for index in range(failures.KEEP + 50):
            failures.note("loop", f"number {index}")
        self.assertEqual(len(failures.recent(limit=failures.KEEP + 100)),
                         failures.KEEP)
        self.assertEqual(failures.recent()[-1]["error"], f"number {failures.KEEP + 49}")

    def test_the_summary_counts_by_part(self):
        failures.note("audio.open", "no device")
        failures.note("audio.open", "no device")
        failures.note("sidecar.start", "missing")
        self.assertEqual(failures.summary(), {"audio.open": 2, "sidecar.start": 1})

    def test_clear_empties_it(self):
        failures.note("x", "y")
        failures.clear()
        self.assertEqual(failures.recent(), [])


class EveryCallSiteCanSeeIt(unittest.TestCase):
    """The mistake this build made: the call was written, the import was not.

    A mechanical edit added `failures.note(...)` to forty-three handlers and forgot
    `from core import failures` in one file. Every test still passed, because the
    line only runs when something has already failed — so the note-taker was found
    by a test that deliberately broke an adapter, and it crashed with NameError
    instead of recording. This is the cheapest possible guard against that class.
    """

    def test_a_module_that_notes_a_failure_imports_the_note_taker(self):
        import ast

        offenders = []
        for path in sorted(ROOT.rglob("*.py")):
            if ".git" in path.parts or path.name == "failures.py":
                continue
            source = path.read_text(encoding="utf-8", errors="replace")
            if "failures.note(" not in source:
                continue
            tree = ast.parse(source)
            imported = False
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module in {
                        "core", "core.failures", "failures"}:
                    if any(alias.name == "failures" for alias in node.names):
                        imported = True
                if isinstance(node, ast.Import) and any(
                        alias.name in {"core.failures", "failures"} for alias in node.names):
                    imported = True
            if not imported:
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [], "these call the note-taker without importing it")


class NothingInTheOwnedCoreSwallows(unittest.TestCase):
    """The promise this build makes, checked against the source itself."""

    def test_core_and_providers_never_catch_an_exception_and_drop_it(self):
        import ast

        # One definition of "catches everything", shared with the scan, so the two
        # cannot disagree about a tuple or a dotted name. The first version of this
        # test wrote its own and called four honest `except (OSError, ValueError)`
        # handlers offenders.
        from scripts.deep_scan import catches_everything

        offenders = []
        for folder in ("core", "providers"):
            for path in (ROOT / folder).rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.ExceptHandler):
                        continue
                    if len(node.body) != 1:
                        continue
                    if not isinstance(node.body[0], (ast.Pass, ast.Continue)):
                        continue
                    if catches_everything(node.type):
                        offenders.append(f"{path.name}:{node.lineno}")
        self.assertEqual(offenders, [],
                         "a failure in the owned core must leave a note, not vanish")


# ══════════════════════════════════════════════════════════════════════════
# from test_deep_scan.py
# ══════════════════════════════════════════════════════════════════════════
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Measured on 2026-11-06. The first number of each pair is the tree's figure at the
# time this test was written; the ceiling is that figure. Nothing here is a target:
# a target nobody reaches is worse than no target.
CEILINGS = {
    "high": 0,
    "swallowed-exception": 157,      # was 282: 43 handlers in core/ and providers/
    "print-in-library": 254,         # now leave a note instead of vanishing
    "complex-function": 108,
    "long-function": 97,
    "typed-exception-discarded": 82,
    "no-timeout": 45,
    "hardcoded-address": 37,
    "deep-nesting": 26,
    "address-in-constant": 19,
    "no-module-docstring": 18,
    "duplicate-body": 11,
    "dangerous-call": 1,
}


def load_scanner():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts import deep_scan
    return deep_scan


class TheScanItself(unittest.TestCase):
    """The rules must fire on the real thing and stay quiet on a deliberate one."""

    def setUp(self):
        self.scanner = load_scanner()
        self.report = self.scanner.Report()

    def scan(self, source: str) -> list:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.py"
            path.write_text(textwrap.dedent(source), encoding="utf-8")
            self.scanner.scan_python(path, self.report, {})
        return [f for f in self.report.findings]

    def kinds(self) -> set[str]:
        return {f.kind for f in self.report.findings}

    def test_a_real_key_shape_is_caught(self):
        self.scan('KEY = "sk-' + "a1b2c3d4e5" * 3 + '"')
        self.assertIn("secret-in-source", self.kinds())

    def test_a_marked_fixture_is_not_reported(self):
        # The repository marks fixtures the way the secret scanners do. Without
        # this, the scan cries wolf at its own tests and stops being read.
        self.scan('FIXTURE = "github_pat_11BZQ7XK2MvT9LpR4WnC8JdY6HsA3GfE5UoI1Kq7YmZ"'
                  '  # gitleaks:allow')
        self.assertNotIn("secret-in-source", self.kinds())

    def test_a_dict_get_is_not_a_network_call(self):
        self.scan("def f(d):\n    return d.get('key')")
        self.assertNotIn("no-timeout", self.kinds())

    def test_a_client_get_with_no_timeout_is_reported(self):
        self.scan("def f(session):\n    return session.get('/health')")
        self.assertIn("no-timeout", self.kinds())

    def test_qts_event_loop_is_not_pythons_exec(self):
        self.scan("def f(app):\n    return app.exec()")
        self.assertNotIn("dangerous-call", self.kinds())

    def test_a_named_tuple_of_types_is_not_catching_everything(self):
        # `except (OSError, ValueError):` names what it expects; `except Exception:`
        # does not. The first version of this scan read any tuple as the second and
        # called four honest handlers holes.
        self.scan("""
            def f():
                try:
                    work()
                except (OSError, ValueError):
                    pass
        """)
        self.assertNotIn("swallowed-exception", self.kinds())
        self.assertIn("typed-exception-discarded", self.kinds())

    def test_bare_exec_is_reported(self):
        self.scan("def f(source):\n    exec(source)")
        self.assertIn("dangerous-call", self.kinds())

    def test_a_caught_and_discarded_exception_is_reported(self):
        self.scan("""
            def f():
                try:
                    work()
                except Exception:
                    pass
        """)
        self.assertIn("swallowed-exception", self.kinds())

    def test_a_bare_except_is_high(self):
        self.scan("""
            def f():
                try:
                    work()
                except:
                    pass
        """)
        self.assertEqual([f.severity for f in self.report.findings
                          if f.kind == "bare-except"], ["high"])


class TheCeilings(unittest.TestCase):
    """The tree as it is, measured the way the report measures it."""

    @classmethod
    def setUpClass(cls):
        cls.scanner = load_scanner()
        cls.report = cls.scanner.run(ROOT)
        cls.counts = cls.report.counts()

    def test_no_finding_is_high(self):
        high = self.report.worst(self.scanner.HIGH)
        self.assertEqual([f"{Path(f.path).name}:{f.line} {f.detail}" for f in high],
                         [], "a high finding is a bug that ships")

    def test_no_measure_has_grown_past_its_ceiling(self):
        grown = {}
        for kind, ceiling in CEILINGS.items():
            measured = len(self.report.worst(self.scanner.HIGH)) if kind == "high" \
                else self.counts.get(kind, 0)
            if measured > ceiling:
                grown[kind] = (ceiling, measured)
        self.assertEqual(grown, {}, "the debt grew; fix it or lower it, do not raise "
                                    "the ceiling")

    def test_the_report_lists_where_it_counts_from(self):
        # A number with no file behind it is a claim, not evidence.
        swallowed = [f for f in self.report.findings
                     if f.kind == "swallowed-exception"]
        self.assertTrue(swallowed)
        self.assertTrue(all(f.path.endswith(".py") and f.line > 0
                            for f in swallowed))

    def test_the_owned_core_discards_nothing(self):
        # The rule this project actually promised: the modules it owns — the ones
        # the gates and the evidence path run through — never swallow a failure.
        owned = [f for f in self.report.findings
                 if f.kind == "swallowed-exception"
                 and Path(f.path).relative_to(ROOT).parts[0] in {"core", "providers"}]
        self.assertEqual([f"{Path(f.path).name}:{f.line}" for f in owned], [])


# ══════════════════════════════════════════════════════════════════════════
# from test_identity_voice.py
# ══════════════════════════════════════════════════════════════════════════
import unittest
from pathlib import Path
from unittest.mock import patch

from core import identity, voice_style

ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / "core" / "prompt.txt"


class IdentityTests(unittest.TestCase):
    def test_the_name_is_ultron(self):
        self.assertEqual(identity.NAME, "Ultron")
        self.assertEqual(identity.display_name(), "Ultron")

    def test_it_answers_to_the_old_names_without_correcting(self):
        for name in ("JARVIS", "Jarvis", "Mark", "Ultron"):
            self.assertTrue(identity.is_self_name(name), name)
        self.assertFalse(identity.is_self_name("Spotify"))

    def test_being_addressed_is_detected(self):
        for phrase in ("Hey Ultron, open notes", "ultron?", "Okay Jarvis, stop"):
            self.assertTrue(identity.is_being_addressed(phrase), phrase)
        self.assertFalse(identity.is_being_addressed("open the notes app"))

    def test_upstream_attribution_is_still_recorded(self):
        facts = identity.as_facts()
        self.assertIn("MARK LVI", facts["upstream"])
        self.assertIn("CC BY-NC", facts["license"])

    def test_config_defaults_come_from_the_identity_module(self):
        from memory import config_manager

        with patch.object(config_manager, "load_api_keys", return_value={}):
            self.assertEqual(config_manager.get_assistant_name(), identity.NAME)


class PromptIdentityTests(unittest.TestCase):
    def setUp(self):
        self.text = PROMPT.read_text(encoding="utf-8-sig")

    def test_the_name_token_is_still_injected(self):
        self.assertIn("{assistant_name}", self.text)

    def test_the_prompt_names_the_project(self):
        self.assertIn("Ultron", self.text)

    def test_the_manner_section_exists(self):
        self.assertIn("[MANNER]", self.text)

    def test_the_speech_rules_that_matter_are_present(self):
        lowered = self.text.lower()
        self.assertIn("no bullet points", lowered)
        self.assertIn("no preamble", lowered)
        self.assertIn("sir", lowered)

    def test_the_persona_does_not_regress_into_chatbot_language(self):
        """The prompt must forbid the tells, not merely omit permission for them."""
        lowered = self.text.lower()
        self.assertIn("certainly", lowered)      # named as forbidden
        self.assertIn("great question", lowered)

    def test_no_stale_jarvis_branding_in_the_addendum_heading(self):
        self.assertNotIn("CUSTOM JARVIS SAFETY ADDENDUM", self.text)
        self.assertIn("CUSTOM ULTRON SAFETY ADDENDUM", self.text)


class VoiceStyleTests(unittest.TestCase):
    def test_markdown_emphasis_is_removed(self):
        self.assertEqual(voice_style.spoken("**Disk:** 41 GB free"), "Disk: 41 GB free")
        self.assertEqual(voice_style.spoken("__Really__ fine"), "Really fine")

    def test_code_ticks_and_headings_are_removed(self):
        self.assertEqual(voice_style.spoken("## Status"), "Status")
        self.assertEqual(voice_style.spoken("Run `setup.py` now"), "Run setup.py now")

    def test_a_bullet_list_becomes_sentences(self):
        spoken = voice_style.spoken("Steps:\n- Check the drive\n- Copy the file")
        self.assertNotIn("-", spoken)
        self.assertIn("Check the drive.", spoken)
        self.assertIn("Copy the file.", spoken)

    def test_numbered_lists_are_flattened_too(self):
        spoken = voice_style.spoken("1. Check the drive\n2. Copy the file")
        self.assertNotIn("1.", spoken)
        self.assertIn("Check the drive.", spoken)

    def test_stacked_openers_are_all_dropped(self):
        self.assertEqual(voice_style.spoken("Sure! Certainly, the drive has 41 GB free."),
                         "the drive has 41 GB free.")

    def test_a_complete_short_answer_is_never_deleted(self):
        self.assertEqual(voice_style.spoken("Sure."), "Sure.")
        self.assertEqual(voice_style.spoken("Yes."), "Yes.")

    def test_content_is_not_rewritten(self):
        text = "The file is at C:\\Users\\me\\notes.txt and holds 41 lines."
        self.assertEqual(voice_style.spoken(text), text)

    def test_links_keep_their_text(self):
        self.assertEqual(voice_style.spoken("See [the docs](https://example.com)"),
                         "See the docs")

    def test_written_register_detection(self):
        self.assertTrue(voice_style.is_written_register("## a\n- b"))
        self.assertFalse(voice_style.is_written_register("The drive has 41 GB free."))

    def test_empty_input_is_safe(self):
        for value in ("", None, "   "):
            self.assertEqual(voice_style.spoken(value), "")


class PipelineSpeechTests(unittest.TestCase):
    def test_the_tts_path_flattens_lists_and_drops_emoji(self):
        from providers.engine_pipeline import _speakable

        text = "**Sure!** Here you go:\n- one\n- two \u2600"
        result = _speakable(text)
        self.assertNotIn("*", result)
        self.assertNotIn("-", result)
        self.assertNotIn("\u2600", result)
        self.assertIn("one.", result)

    def test_plain_speech_passes_through(self):
        from providers.engine_pipeline import _speakable

        self.assertEqual(_speakable("The drive has 41 GB free."),
                         "The drive has 41 GB free.")


# ══════════════════════════════════════════════════════════════════════════
# from test_startup_paths.py
# ══════════════════════════════════════════════════════════════════════════
import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SOURCE = (ROOT / "main.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def extract(*names: str, extra_globals: dict | None = None) -> dict:
    """Build a namespace containing only the named top-level functions."""
    wanted = [node for node in TREE.body
              if isinstance(node, ast.FunctionDef) and node.name in names]
    missing = set(names) - {node.name for node in wanted}
    assert not missing, f"not found in main.py: {sorted(missing)}"
    module = ast.Module(body=wanted, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"json": json}
    namespace.update(extra_globals or {})
    exec(compile(module, "main.py (extracted)", "exec"), namespace)
    return namespace


class ApiKeyTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.path = Path(self._temp.name) / "api_keys.json"
        self.ns = extract("_get_api_key", "_has_gemini_key",
                          extra_globals={"API_CONFIG_PATH": self.path})

    def tearDown(self):
        self._temp.cleanup()

    def test_a_present_key_is_returned_without_whitespace(self):
        self.path.write_text(json.dumps({"gemini_api_key": "  AIza-key  "}), "utf-8")
        self.assertEqual(self.ns["_get_api_key"](), "AIza-key")
        self.assertTrue(self.ns["_has_gemini_key"]())

    def test_no_key_is_an_empty_string_and_not_a_key_error(self):
        # The old body was `return json.load(f)["gemini_api_key"]`, so an install
        # configured for a provider and no Gemini key raised KeyError from inside
        # the reconnect loop — where every exception becomes a retry.
        self.path.write_text(json.dumps({"os_system": "windows"}), "utf-8")
        self.assertEqual(self.ns["_get_api_key"](), "")
        self.assertFalse(self.ns["_has_gemini_key"]())

    def test_a_missing_file_is_an_empty_string(self):
        self.assertEqual(self.ns["_get_api_key"](), "")
        self.assertFalse(self.ns["_has_gemini_key"]())

    def test_a_damaged_file_is_an_empty_string(self):
        self.path.write_text("{not json", "utf-8")
        self.assertEqual(self.ns["_get_api_key"](), "")

    def test_a_json_list_is_an_empty_string(self):
        self.path.write_text("[1, 2, 3]", "utf-8")
        self.assertEqual(self.ns["_get_api_key"](), "")


class PromptFallbackTests(unittest.TestCase):
    def test_the_fallback_prompt_is_named_after_this_assistant(self):
        # It said "You are JARVIS, Tony Stark's AI assistant" — the upstream
        # project's name, in the one place that speaks the persona when the
        # prompt file is missing.
        from core import identity
        with tempfile.TemporaryDirectory() as temp:
            ns = extract("_load_system_prompt",
                         extra_globals={"PROMPT_PATH": Path(temp) / "missing.txt",
                                        "identity": identity})
            text = ns["_load_system_prompt"]()
        self.assertIn(identity.NAME, text)
        self.assertNotIn("JARVIS", text)

    def test_the_real_prompt_file_still_wins(self):
        from core import identity
        ns = extract("_load_system_prompt",
                     extra_globals={"PROMPT_PATH": ROOT / "core" / "prompt.txt",
                                    "identity": identity})
        self.assertEqual(ns["_load_system_prompt"](), (ROOT / "core" / "prompt.txt")
                         .read_text(encoding="utf-8"))


class PipelineFallbackIsHonestTests(unittest.TestCase):
    """A fallback that does not exist is worse than no fallback.

    With provider mode configured, a broken engine, and no Gemini key, the loop
    used to ask Gemini Live with an empty key, take an auth error, and answer it
    with the setup screen — repeatedly — while the real fault was a provider that
    would not build.
    """

    def test_the_loop_refuses_to_open_a_session_it_cannot_authenticate(self):
        self.assertIn('self._engine_mode() == "pipeline"', SOURCE)
        self.assertIn("not _has_gemini_key()", SOURCE)
        # and it waits rather than spinning
        start = SOURCE.index("not _has_gemini_key()")
        window = SOURCE[start:start + 600]
        self.assertIn("await asyncio.sleep", window)

    def test_the_reason_comes_back_from_the_engine_resolution(self):
        self.assertIn("self._pipeline_error = reason", SOURCE)
        self.assertIn('self._pipeline_error = ""', SOURCE)

    def _engine_caps_body(self):
        # Locate the whole method, not a fixed-size window. The method grew
        # past 4000 chars, which put the key check and the once-only report
        # outside the old window and made these tests fail on good code.
        start = SOURCE.index("def _resolve_engine_caps")
        candidates = [idx for idx in (SOURCE.find("\n    async def ", start),
                                      SOURCE.find("\n    def ", start + 10))
                      if idx != -1]
        end = min(candidates) if candidates else len(SOURCE)
        return SOURCE[start:end]

    def test_the_message_depends_on_whether_a_key_exists(self):
        body = self._engine_caps_body()
        self.assertIn("if _has_gemini_key():", body)
        self.assertIn("ENGINE & PROVIDERS", body)

    def test_a_failure_is_reported_once_not_once_per_attempt(self):
        body = self._engine_caps_body()
        self.assertIn("_pipeline_reported", body)


# ══════════════════════════════════════════════════════════════════════════
# from test_insights.py
# ══════════════════════════════════════════════════════════════════════════
import ast
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from actions import system_monitor
from core.insights import InsightEngine
from custom_jarvis.service import CustomService


class InsightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "private" / "approved.json"
        self.now = [100.0]
        self.engine = InsightEngine(self.path, clock=lambda: self.now[0])

    def proposal(self):
        self.engine.observe("Please keep answers short.")
        row = self.engine.review()["pending"][0]
        return row, {"key": row["key"], "value": row["value"]}

    def test_observing_does_not_create_a_profile_or_directory(self):
        self.proposal()
        self.assertFalse(self.path.parent.exists())
        self.assertEqual(self.engine.review()["approved"], {})

    def test_only_approval_persists_exact_enum_preference(self):
        row, expected = self.proposal()
        self.engine.approve(row["id"], expected)
        self.assertEqual(
            json.loads(self.path.read_text()), {"response_length": "concise"}
        )
        self.assertNotIn("evidence", self.path.read_text())

    def test_approved_preference_survives_restart(self):
        row, expected = self.proposal()
        self.engine.approve(row["id"], expected)
        restored = InsightEngine(self.path)
        self.assertEqual(restored.approved["response_length"], "concise")
        self.assertIn("concise", restored.prompt_context())
        self.assertEqual(restored.review()["pending"], [])

    def test_expired_proposal_cannot_be_saved(self):
        row, expected = self.proposal()
        self.now[0] += 3601
        with self.assertRaises(ValueError):
            self.engine.approve(row["id"], expected)
        self.assertFalse(self.path.exists())

    def test_changed_proposal_cannot_be_approved_with_old_identity(self):
        row, expected = self.proposal()
        self.engine.observe("I want more detail.")
        with self.assertRaises(ValueError):
            self.engine.approve(row["id"], expected)
        self.assertFalse(self.path.exists())

    def test_tampered_expected_value_is_rejected(self):
        row, expected = self.proposal()
        with self.assertRaises(ValueError):
            self.engine.approve(
                row["id"], {"key": expected["key"], "value": "detailed"}
            )
        self.assertFalse(self.path.exists())

    def test_reject_never_saves(self):
        row, _ = self.proposal()
        self.engine.reject(row["id"])
        self.assertEqual(self.engine.review()["pending"], [])
        self.assertFalse(self.path.exists())

    def test_secret_bearing_messages_are_not_used_for_proposals(self):
        self.engine.observe("My password is SECRET; keep answers short")
        self.assertEqual(self.engine.review()["pending"], [])

    def test_does_not_infer_personality_health_or_emotion(self):
        self.engine.observe("I am anxious and tired and have a medical diagnosis.")
        self.assertEqual(self.engine.review()["pending"], [])
        self.assertFalse(self.path.exists())

    def test_currently_negated_preference_not_proposed(self):
        self.engine.observe("Do not be brief")
        self.assertEqual(self.engine.review()["pending"], [])

    def test_proposal_evidence_is_bounded(self):
        self.engine.observe("x" * 500 + " keep answers short " + "z" * 1000)
        row = self.engine.review()["pending"][0]
        self.assertLessEqual(len(row["evidence"]), 120)

    def test_readiness_is_only_a_temporary_draft_checklist(self):
        self.engine.observe("I have a presentation tomorrow.")
        view = self.engine.review()
        self.assertEqual(view["recommendations"][0]["title"], "Presentation readiness")
        self.assertEqual(len(view["recommendations"][0]["draft"]), 3)
        self.assertFalse(self.path.exists())
        self.now[0] += 3601
        self.assertEqual(self.engine.review()["recommendations"], [])

    def test_forget_clears_all_insight_state(self):
        row, expected = self.proposal()
        self.engine.approve(row["id"], expected)
        self.engine.observe("I have a meeting tomorrow")
        self.engine.forget()
        self.assertFalse(self.path.exists())
        self.assertEqual(self.engine.review()["approved"], {})
        self.assertEqual(self.engine.review()["recommendations"], [])

    def test_profile_load_ignores_unknown_keys_and_values(self):
        self.path.parent.mkdir()
        self.path.write_text(
            json.dumps(
                {
                    "personality": "obedient",
                    "tone": "professional",
                    "permissions": "all",
                    "response_length": "anything",
                }
            )
        )
        restored = InsightEngine(self.path)
        self.assertEqual(restored.approved, {"tone": "professional"})

    def test_atomic_write_failure_does_not_claim_preference_saved(self):
        row, expected = self.proposal()
        with patch("core.insights.os.replace", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                self.engine.approve(row["id"], expected)
        self.assertEqual(self.engine.approved, {})
        self.assertFalse(self.path.exists())
        self.assertFalse(list(self.path.parent.glob(".insights-*")))

    def test_service_requires_real_approval_before_profile_write(self):
        row, _ = self.proposal()
        service = CustomService(
            Path(self.temp.name) / "service", approval=lambda *args: False
        )
        with patch("core.insights.get_insights", return_value=self.engine):
            with self.assertRaises(ValueError):
                service.perform("review_insight", {"id": row["id"]})
        self.assertFalse(self.path.exists())

    def test_service_saves_only_after_reviewed_approval(self):
        row, _ = self.proposal()
        requests = []
        service = CustomService(
            Path(self.temp.name) / "service",
            approval=lambda name, payload: requests.append((name, payload)) or True,
        )
        with patch("core.insights.get_insights", return_value=self.engine):
            result = service.perform("review_insight", {})
        self.assertEqual(requests[0][0], "save_reviewed_insight")
        self.assertEqual(requests[0][1]["value"], "concise")
        self.assertEqual(result["approved"], {"response_length": "concise"})

    def test_service_can_dismiss_next_candidate_without_saving(self):
        self.proposal()
        service = CustomService(
            Path(self.temp.name) / "service", approval=lambda *args: False
        )
        with patch("core.insights.get_insights", return_value=self.engine):
            result = service.perform("reject_insight", {})
        self.assertTrue(result["rejected"])
        self.assertEqual(self.engine.review()["pending"], [])
        self.assertFalse(self.path.exists())

    def test_automatic_session_summary_storage_is_disabled(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "main.py").read_text())
        method = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "_save_session_summary"
        )
        self.assertFalse(any(isinstance(n, ast.Call) for n in ast.walk(method)))


class QuietRamTests(unittest.TestCase):
    def snapshot(self, ram=99, temp=-1):
        return (
            patch.object(system_monitor.psutil, "cpu_percent", return_value=0),
            patch.object(
                system_monitor.psutil,
                "virtual_memory",
                return_value=SimpleNamespace(
                    percent=ram, used=8 * 1024**3, total=16 * 1024**3
                ),
            ),
            patch.object(system_monitor, "_get_cpu_temp", return_value=temp),
            patch.object(system_monitor, "_get_gpu_usage", return_value=-1),
        )

    def test_high_ram_never_generates_default_alert(self):
        a, b, c, d = self.snapshot()
        with a, b, c, d:
            monitor = system_monitor.SystemMonitor()
            for _ in range(5):
                self.assertIsNone(monitor.check())
            self.assertNotIn("ram", monitor._last_alert)

    def test_other_temperature_alerts_are_not_removed(self):
        a, b, c, d = self.snapshot(temp=99)
        with a, b, c, d:
            result = system_monitor.SystemMonitor().check()
        self.assertIn("temperature", result)
        self.assertNotIn("RAM", result)

    def test_explicit_system_status_still_includes_ram(self):
        a, b, c, d = self.snapshot()
        with a, b, c, d:
            result = system_monitor.get_system_status()
        self.assertEqual(result["ram_percent"], 99)
        self.assertEqual(result["ram_total_gb"], 16)

    def test_proactive_prompt_forbids_ram_nags(self):
        from actions.proactive import ProactiveEngine

        prompt = ProactiveEngine().build_prompt({})
        self.assertIn("Never give unsolicited RAM", prompt)


# ══════════════════════════════════════════════════════════════════════════
# from test_digest.py
# ══════════════════════════════════════════════════════════════════════════
import ast
import os
import socket
import subprocess
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from core import digest

ROOT = Path(__file__).resolve().parents[1]

MEMORY = {
    "notes": {
        "wifi": {"value": "1234", "updated": "2026-11-06"},
        "old": {"value": "kept from before", "updated": "2026-10-01"},
        "plain string entry": "legacy shape",          # bare string, no date
    },
    "preferences": {"lang": {"value": "English", "updated": "2026-11-06"}},
    "monitors": {"rain in Dehli": {"hash": "abc"}},     # machine state, not a fact
    "identity": {}, "projects": {}, "relationships": {}, "wishes": {},
}

NOW = datetime(2026, 11, 6, 20, 30)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.report = digest.build(now=NOW, memory=MEMORY, reminders_dir=Path("/nonexistent"))

    def test_todays_facts_are_listed(self):
        keys = {(f["category"], f["key"]) for f in self.report["remembered_today"]}
        self.assertEqual(keys, {("notes", "wifi"), ("preferences", "lang")})

    def test_older_facts_are_counted_not_listed(self):
        self.assertEqual(self.report["remembered_older"], 2)   # old + legacy string
        text = digest.render_text(self.report)
        self.assertIn("Older facts on file: 2", text)
        self.assertNotIn("kept from before", text)

    def test_watched_topics_are_not_counted_as_facts(self):
        keys = {f["key"] for f in self.report["remembered_today"]}
        self.assertNotIn("rain in Dehli", keys)

    def test_watched_topics_are_reported_separately(self):
        self.assertEqual(self.report["watching"], ["rain in Dehli"])
        self.assertIn("Watching: rain in Dehli", digest.render_text(self.report))

    def test_the_report_says_it_changed_nothing(self):
        self.assertIn("Nothing was started, sent or changed",
                      digest.render_text(self.report))

    def test_an_empty_day_still_reads_sensibly(self):
        empty = digest.build(now=NOW, memory={}, reminders_dir=Path("/nonexistent"))
        text = digest.render_text(empty)
        self.assertIn("nothing new", text.lower())
        self.assertIn("Reminders set: none", text)
        self.assertTrue(digest.render_speech(empty))

    def test_reminder_names_come_from_the_folder(self):
        import tempfile
        folder = Path(tempfile.mkdtemp())
        (folder / "dentist.py").write_text("", encoding="utf-8")
        (folder / "call_mom.py").write_text("", encoding="utf-8")
        (folder / "notes.txt").write_text("", encoding="utf-8")   # not a reminder
        report = digest.build(now=NOW, memory={}, reminders_dir=folder)
        self.assertEqual(report["reminders"], ["call_mom", "dentist"])

    def test_a_missing_reminder_folder_is_not_created(self):
        missing = Path("/tmp/definitely-not-here-digest")
        digest.build(now=NOW, memory={}, reminders_dir=missing)
        self.assertFalse(missing.exists(), "the digest must not create folders")


class InertTests(unittest.TestCase):
    """The rule: the digest activates nothing."""

    def test_building_writes_no_files(self):
        before = {p: (p.stat().st_mtime_ns, p.stat().st_size)
                  for p in (ROOT / "memory").rglob("*") if p.is_file()}
        digest.build(now=NOW, memory=MEMORY, reminders_dir=Path("/nonexistent"))
        digest.render_text(digest.build(now=NOW, memory=MEMORY))
        digest.render_speech(digest.build(now=NOW, memory=MEMORY))
        after = {p: (p.stat().st_mtime_ns, p.stat().st_size)
                 for p in (ROOT / "memory").rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_building_opens_no_socket(self):
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network")), \
             mock.patch.object(socket, "create_connection",
                               side_effect=AssertionError("network")):
            report = digest.build(now=NOW, memory=MEMORY, reminders_dir=Path("/nonexistent"))
            self.assertTrue(digest.render_text(report))

    def test_building_starts_no_process(self):
        with mock.patch.object(subprocess, "run", side_effect=AssertionError("process")), \
             mock.patch.object(subprocess, "Popen", side_effect=AssertionError("process")), \
             mock.patch.object(os, "system", side_effect=AssertionError("process")):
            digest.build(now=NOW, memory=MEMORY, reminders_dir=Path("/nonexistent"))

    def test_the_only_write_is_one_date(self):
        with mock.patch.object(Path, "write_text") as written, \
             mock.patch.object(Path, "mkdir"):
            digest.save_last_run("2026-11-06", path=Path("/tmp/x/state.json"))
        self.assertEqual(written.call_count, 1)
        self.assertIn("2026-11-06", written.call_args.args[0])


class SchedulerTests(unittest.TestCase):
    def test_before_the_hour_it_does_not_run(self):
        self.assertFalse(digest.should_run(datetime(2026, 11, 6, 19, 59), "20:00", ""))

    def test_after_the_hour_it_runs_once(self):
        self.assertTrue(digest.should_run(datetime(2026, 11, 6, 20, 0), "20:00", ""))
        self.assertFalse(digest.should_run(datetime(2026, 11, 6, 23, 0), "20:00", "2026-11-06"))

    def test_a_new_day_runs_again(self):
        self.assertTrue(digest.should_run(datetime(2026, 11, 7, 20, 1), "20:00", "2026-11-06"))

    def test_a_bad_hour_falls_back_to_the_default(self):
        self.assertTrue(digest.should_run(datetime(2026, 11, 6, 20, 30), "junk", ""))

    def test_last_run_round_trips(self):
        import tempfile
        path = Path(tempfile.mkdtemp()) / "state.json"
        self.assertEqual(digest.load_last_run(path), "")
        self.assertTrue(digest.save_last_run("2026-11-06", path=path))
        self.assertEqual(digest.load_last_run(path), "2026-11-06")

    def test_a_corrupt_state_file_is_not_fatal(self):
        import tempfile
        path = Path(tempfile.mkdtemp()) / "state.json"
        path.write_text("not json", encoding="utf-8")
        self.assertEqual(digest.load_last_run(path), "")


class WiringTests(unittest.TestCase):
    """The feature is only real if the app can reach it."""

    def _main_source(self) -> str:
        return (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")

    def test_main_declares_the_tool(self):
        tree = ast.parse(self._main_source())
        names = {node.value for node in ast.walk(tree)
                 if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        self.assertIn("daily_digest", names)

    def test_main_handles_it_without_a_tool_call(self):
        source = self._main_source()
        block = source.split('elif name == "daily_digest":', 1)[-1][:400]
        self.assertIn("digest_mod.build()", block)
        self.assertIn("render_text", block)

    def test_the_daily_loop_exists_and_records_the_day(self):
        source = self._main_source()
        loop = source.split("async def _digest_loop", 1)[-1][:900]
        self.assertIn("should_run", loop)
        self.assertIn("save_last_run", loop)
        self.assertIn("write_log", loop, "the digest is delivered to the log")
        self.assertNotIn("speak", loop.lower(),
                         "the digest must not speak over the user")

    def test_the_hour_is_a_readable_setting(self):
        from memory import config_manager
        self.assertRegex(config_manager.get_digest_hour(), r"^\d{2}:\d{2}$")


# ══════════════════════════════════════════════════════════════════════════
# from test_performance_budget.py
# ══════════════════════════════════════════════════════════════════════════
import statistics
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Ceilings in milliseconds, twenty times or more the measured value.
CEILING = {
    "policy over every tool": 5.0,
    "describe every tool": 5.0,
    "render the system prompt": 5.0,
    "memory read": 5.0,
}


def load_main():
    """Import the program, or skip, on a machine with no audio device or kit.

    The stages measured here never touch a speaker, so a missing PortAudio is
    stubbed. A missing PyQt6 is not stubbable — it supplies base classes — so that
    machine skips, which is the same rule the audio claims follow.
    """
    try:
        import PyQt6  # noqa: F401
    except Exception as exc:                           # pragma: no cover
        raise unittest.SkipTest(f"PyQt6 not installed: {exc}")
    for name in ("sounddevice", "mss"):
        try:
            __import__(name)
        except Exception:
            sys.modules[name] = mock.MagicMock()
    try:
        import main
    except Exception as exc:                           # pragma: no cover
        raise unittest.SkipTest(f"main.py will not import here: {exc}")
    return main


def median_ms(fn, rounds: int = 30) -> float:
    samples = []
    for _ in range(rounds):
        started = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - started) * 1000.0)
    return statistics.median(samples)


class TurnBudget(unittest.TestCase):
    """Four measured stages of a turn, each with a generous ceiling."""

    @classmethod
    def setUpClass(cls):
        cls.main = load_main()

    def test_policy_classification_of_every_tool_is_cheap(self):
        from core import policy
        names = [d.get("name", "") for d in self.main.TOOL_DECLARATIONS
                 if isinstance(d, dict)]

        def run():
            for name in names:
                policy.decide(name, {"path": "notes.txt"})

        elapsed = median_ms(run)
        self.assertLess(elapsed, CEILING["policy over every tool"],
                        f"{len(names)} policy decisions took {elapsed:.2f} ms")

    def test_describing_every_tool_is_cheap(self):
        declarations = list(self.main.TOOL_DECLARATIONS)
        elapsed = median_ms(lambda: self.main._describe_tools(declarations))
        self.assertLess(elapsed, CEILING["describe every tool"],
                        f"describing {len(declarations)} tools took {elapsed:.2f} ms")

    def test_rendering_the_prompt_is_cheap(self):
        template = (ROOT / "core" / "prompt.txt").read_text(encoding="utf-8")
        values = {"assistant_name": "Ultron", "tools": "- one: does a thing" * 50,
                  "limits": "nothing", "date": "2026-11-06", "time": "10:30"}
        elapsed = median_ms(lambda: self.main._render_prompt(template, values))
        self.assertLess(elapsed, CEILING["render the system prompt"],
                        f"prompt rendering took {elapsed:.2f} ms")

    def test_reading_memory_is_cheap(self):
        from memory import memory_manager
        elapsed = median_ms(lambda: memory_manager.load_memory())
        self.assertLess(elapsed, CEILING["memory read"],
                        f"memory read took {elapsed:.2f} ms")


class PromptBudget(unittest.TestCase):
    """The system prompt is paid for by the provider on every request.

    Measured on the build machine: 15,534 characters of hand-written template,
    1,669 of tool descriptions and 1,107 of limits — 16,620 characters assembled,
    about 4,155 tokens. Nine tenths of it is persona and rules, and there is no
    duplicated line in it, so there is nothing to cut safely without a live
    evaluation of whether the assistant still behaves.

    What this test does instead of trimming blind: it stops the prompt from
    *growing* unnoticed, and it checks the two things that make it correct — every
    tool appears once, and no placeholder is left unfilled.
    """

    CEILING_CHARS = 20_000          # measured 16,620; about 20 % of headroom

    @classmethod
    def setUpClass(cls):
        cls.main = load_main()

    def assemble(self) -> tuple[str, str, str]:
        base = self.main._load_system_prompt()
        declarations = list(self.main.TOOL_DECLARATIONS)
        tools = self.main._describe_tools(declarations)
        limits = self.main._describe_limits(True, True)
        rendered = self.main._render_prompt(base, {
            "assistant_name": "Ultron", "user_name": "Owner", "tools": tools,
            "limits": limits, "platform": "Windows", "memory": '{"identity": {}}',
            "date": "2026-11-06", "time": "10:30"})
        return rendered, tools, base

    def test_the_assembled_prompt_stays_inside_its_budget(self):
        rendered, tools, base = self.assemble()
        self.assertLess(len(rendered), self.CEILING_CHARS,
                        f"the prompt is {len(rendered)} chars, over its "
                        f"{self.CEILING_CHARS} budget")
        # The template is the part a person edits, so it gets its own line here:
        # a jump in this figure is someone writing a new paragraph, not a bug.
        self.assertLess(len(base), 18_000, "the hand-written template has grown")

    def test_every_tool_appears_exactly_once(self):
        _rendered, tools, _base = self.assemble()
        names = [d.get("name") for d in self.main.TOOL_DECLARATIONS
                 if isinstance(d, dict) and d.get("name")]
        lines = [line for line in tools.splitlines() if line.startswith("- ")]
        self.assertEqual(len(lines), len(names), "a tool is missing from the prompt")
        for name in names:
            self.assertEqual(sum(1 for line in lines if line.startswith(f"- {name}:")
                                 or line == f"- {name}"), 1,
                             f"{name} appears more than once")

    def test_no_placeholder_is_left_unfilled(self):
        rendered, _tools, _base = self.assemble()
        for token in ("{tools}", "{limits}", "{memory}", "{assistant_name}",
                      "{user_name}", "{date}", "{time}", "{platform}"):
            self.assertNotIn(token, rendered, f"{token} was never filled in")


class NoWorkPerCall(unittest.TestCase):
    """The mistake a language change cannot fix: doing the same work twice."""

    def test_policy_tables_are_module_constants_not_built_per_call(self):
        from core import policy
        for name in ("OBSERVE_TOOLS", "ROUTINE_TOOLS", "GUARDED_TOOLS"):
            self.assertIsInstance(getattr(policy, name), (set, frozenset, dict),
                                  f"{name} is rebuilt on every decision")

    def test_the_transcript_regex_is_compiled_once(self):
        main = load_main()
        pattern = getattr(main, "_CTRL_RE", None)
        self.assertIsNotNone(pattern, "_CTRL_RE disappeared from main.py")
        self.assertTrue(hasattr(pattern, "sub"),
                        "the transcript scrub compiles its pattern per call")


# ══════════════════════════════════════════════════════════════════════════
# from test_first_run.py
# ══════════════════════════════════════════════════════════════════════════
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from memory import config_manager as cm


class ConfigSandbox(unittest.TestCase):
    """Point the config module at a throwaway api_keys.json for each test."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.dir = Path(self._temp.name)
        self._saved = (cm.CONFIG_DIR, cm.CONFIG_FILE)
        cm.CONFIG_DIR = self.dir
        cm.CONFIG_FILE = self.dir / "api_keys.json"

    def tearDown(self):
        cm.CONFIG_DIR, cm.CONFIG_FILE = self._saved
        self._temp.cleanup()

    def write(self, payload: dict) -> None:
        cm.CONFIG_FILE.write_text(json.dumps(payload), encoding="utf-8")

    def read(self) -> dict:
        return json.loads(cm.CONFIG_FILE.read_text(encoding="utf-8"))


class BriefingOptInTests(ConfigSandbox):
    """Startup speech is opt-in unless the owner has saved a boolean choice."""

    def test_a_fresh_install_defaults_to_off(self):
        self.assertFalse(cm.get_brief_enabled())

    def test_an_existing_config_without_a_choice_defaults_to_off(self):
        self.write({"assistant_name": "Ultron", "voice_name": "Aoede"})
        self.assertFalse(cm.get_brief_enabled())

    def test_an_explicit_true_choice_is_preserved(self):
        self.write({"morning_brief_enabled": True})
        self.assertTrue(cm.get_brief_enabled())

    def test_an_explicit_false_choice_is_preserved(self):
        self.write({"morning_brief_enabled": False})
        self.assertFalse(cm.get_brief_enabled())

    def test_a_malformed_non_boolean_choice_fails_closed(self):
        self.write({"morning_brief_enabled": "true"})
        self.assertFalse(cm.get_brief_enabled())

    def test_the_owner_can_turn_the_brief_on_and_off(self):
        self.write({"assistant_name": "Ultron"})
        cm.save_brief_enabled(True)
        self.assertTrue(cm.get_brief_enabled())
        self.assertEqual(self.read()["assistant_name"], "Ultron")
        cm.save_brief_enabled(False)
        self.assertFalse(cm.get_brief_enabled())
        self.assertEqual(self.read()["assistant_name"], "Ultron")


class NothingIsLostTests(ConfigSandbox):
    def test_reopening_setup_keeps_the_name_voice_colour_and_scale(self):
        self.write({
            "os_system": "windows",
            "gemini_api_key": "old-key",
            "assistant_name": "Ultron",
            "user_name": "Ada",
            "voice_name": "Aoede",
            "ui_color": "#ff8800",
            "ui_scale": 1.45,
        })
        cm.apply_first_run(os_name="windows", gemini_api_key="new-key")
        config = self.read()
        self.assertEqual(config["gemini_api_key"], "new-key")
        for field, value in (("assistant_name", "Ultron"), ("user_name", "Ada"),
                             ("voice_name", "Aoede"), ("ui_color", "#ff8800"),
                             ("ui_scale", 1.45)):
            self.assertEqual(config[field], value, f"{field} was erased by setup")

    def test_a_blank_key_never_deletes_a_stored_one(self):
        self.write({"os_system": "windows", "gemini_api_key": "keep-me"})
        cm.apply_first_run(os_name="windows", gemini_api_key="   ")
        self.assertEqual(self.read()["gemini_api_key"], "keep-me")

    def test_configured_providers_survive_another_run(self):
        self.write({
            "os_system": "windows",
            "gemini_api_key": "k",
            "providers": {"mode": "gemini",
                          "creds": {"openai_compat@groq": {"api_key": "gsk-1",
                                                           "model": "llama-3.3-70b"}}},
        })
        cm.apply_first_run(os_name="windows", providers=[
            {"id": "openai_compat@openai", "values": {"api_key": "sk-2", "model": "gpt-4o"}}
        ])
        creds = self.read()["providers"]["creds"]
        self.assertIn("openai_compat@groq", creds)
        self.assertIn("openai_compat@openai", creds)
        self.assertEqual(creds["openai_compat@groq"]["api_key"], "gsk-1")


class ProviderOnlyTests(ConfigSandbox):
    def test_a_local_provider_alone_makes_an_install_configured(self):
        cm.apply_first_run(os_name="windows", providers=[
            {"id": "openai_compat@ollama",
             "values": {"base_url": "http://127.0.0.1:11434/v1", "model": "qwen3:8b"}}
        ])
        config = self.read()
        self.assertNotIn("gemini_api_key", config)
        self.assertTrue(cm.has_a_brain())

    def test_a_cloud_provider_alone_switches_to_pipeline_mode(self):
        cm.apply_first_run(os_name="windows", providers=[
            {"id": "openai_compat@groq", "values": {"api_key": "gsk", "model": "llama"}}
        ])
        block = self.read()["providers"]
        self.assertEqual(block["mode"], "pipeline")
        self.assertEqual(block["pipeline"]["llm"], "openai_compat@groq")

    def test_a_gemini_key_keeps_the_live_path(self):
        cm.apply_first_run(os_name="windows", gemini_api_key="AIza-x")
        block = self.read().get("providers") or {}
        self.assertNotEqual(block.get("mode"), "pipeline")

    def test_several_providers_are_stored_side_by_side(self):
        cm.apply_first_run(os_name="windows", gemini_api_key="AIza-x", providers=[
            {"id": "openai_compat@groq", "values": {"api_key": "gsk", "model": "llama"}},
            {"id": "openai_compat@ollama",
             "values": {"base_url": "http://127.0.0.1:11434/v1", "model": "qwen3:8b"}},
            {"id": "openai_compat@openrouter", "values": {"api_key": "sk-or", "model": "x"}},
        ])
        creds = self.read()["providers"]["creds"]
        self.assertEqual(len(creds), 3)

    def test_a_provider_with_no_values_is_not_saved(self):
        cm.apply_first_run(os_name="windows", providers=[{"id": "openai_compat@groq",
                                                          "values": {"api_key": "", "model": ""}}])
        creds = (self.read().get("providers") or {}).get("creds") or {}
        self.assertEqual(creds, {})


class IsConfiguredTests(ConfigSandbox):
    def test_a_missing_file_is_not_configured(self):
        self.assertFalse(cm.has_a_brain())

    def test_a_key_without_an_operating_system_is_not_configured(self):
        self.write({"gemini_api_key": "AIza-x"})
        self.assertFalse(cm.has_a_brain())

    def test_a_key_with_an_operating_system_is_configured(self):
        self.write({"gemini_api_key": "AIza-x", "os_system": "windows"})
        self.assertTrue(cm.has_a_brain())

    def test_a_configured_provider_is_configured(self):
        self.write({"os_system": "windows",
                    "providers": {"creds": {"openai_compat@ollama":
                                            {"model": "qwen3:8b"}}}})
        self.assertTrue(cm.has_a_brain())

    def test_an_empty_provider_entry_is_not_configured(self):
        self.write({"os_system": "windows",
                    "providers": {"creds": {"openai_compat@ollama": {"model": ""}}}})
        self.assertFalse(cm.has_a_brain())

    def test_garbage_in_the_providers_block_does_not_raise(self):
        self.write({"os_system": "windows", "providers": ["not", "a", "dict"]})
        self.assertFalse(cm.has_a_brain())


class TheOldNameStillMeansWhatItMeantTests(ConfigSandbox):
    def test_is_configured_still_only_answers_for_gemini(self):
        # Left exactly as it was: callers elsewhere may rely on "a Gemini key is
        # present", and quietly widening it would change their meaning.
        self.write({"os_system": "windows", "gemini_api_key": "short"})
        self.assertFalse(cm.is_configured())
        self.write({"os_system": "windows", "gemini_api_key": "a-long-enough-key-123"})
        self.assertTrue(cm.is_configured())


class PatchSettingsTests(ConfigSandbox):
    def test_it_returns_the_config_it_wrote(self):
        result = cm.patch_settings(os_system="linux")
        self.assertEqual(result["os_system"], "linux")

    def test_it_merges_rather_than_replaces(self):
        self.write({"assistant_name": "Ultron", "voice_name": "Aoede"})
        cm.patch_settings(ui_scale=1.3)
        config = self.read()
        self.assertEqual(config["assistant_name"], "Ultron")
        self.assertEqual(config["ui_scale"], 1.3)


if __name__ == "__main__":
    unittest.main()
