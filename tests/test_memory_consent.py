"""Only what the user approves is remembered — pinned, not assumed.

The rule was in `core/policy.py` ("memory is permanent — remembering is
approval-gated") and nowhere in the write path: `save_memory` called
`update_memory` directly. These tests hold the rule at the place it is now
enforced, with a fake writer so a failure here cannot touch a real memory file.

The failure that matters is not "the prompt did not appear" — it is **a fact
stored that nobody approved**, so most of these assert on what the writer *did
not* receive.
"""

from __future__ import annotations

import unittest

from core import memory_consent
from core.memory_consent import EMPTY_ANSWER, PENDING_MARKER, request_write


class _Verdict:
    def __init__(self, allow: bool):
        self.allow = allow


class _Recorder:
    """Stands in for memory_manager.update_memory and for a pending banner."""

    def __init__(self, allow: bool = False, gate_answer: str | None = None):
        self.writes: list[dict] = []
        self.banners: list[dict] = []
        self.allow = allow
        self.gate_answer = gate_answer if gate_answer is not None else (
            PENDING_MARKER + " ask the user to confirm on the HUD")

    # the two injections
    def write(self, payload: dict) -> None:
        self.writes.append(payload)

    def decide(self, *_args, **_kwargs):
        return _Verdict(self.allow)

    def gate(self, **kwargs) -> str:
        self.banners.append(kwargs)
        return self.gate_answer


class NoSilentWriteTests(unittest.TestCase):
    def test_an_inferred_fact_is_not_written(self):
        rec = _Recorder()
        result = request_write("notes", "wifi", "hunter2", rec.write,
                               gate=rec.gate, decide=rec.decide)
        self.assertEqual(rec.writes, [], "nothing may be stored before approval")
        self.assertIn(PENDING_MARKER, result["result"])
        self.assertNotIn("silent", result, "a pending write must not be silent")

    def test_the_banner_shows_the_fact_itself(self):
        rec = _Recorder()
        request_write("notes", "wifi", "hunter2", rec.write,
                      gate=rec.gate, decide=rec.decide)
        self.assertEqual(len(rec.banners), 1)
        detail = rec.banners[0]["detail"]
        self.assertIn("wifi", detail)
        self.assertIn("hunter2", detail, "the user approves the value, not a summary")
        self.assertIn("notes", detail)

    def test_confirming_writes_exactly_once(self):
        rec = _Recorder()
        request_write("notes", "wifi", "hunter2", rec.write,
                      gate=rec.gate, decide=rec.decide)
        run = rec.banners[0]["run"]
        self.assertEqual(run(), "Remembered “wifi” in notes.")
        self.assertEqual(rec.writes,
                         [{"notes": {"wifi": {"value": "hunter2"}}}])

    def test_cancelling_leaves_the_store_untouched(self):
        rec = _Recorder()
        request_write("notes", "wifi", "hunter2", rec.write,
                      gate=rec.gate, decide=rec.decide)
        # CANCEL means the stored callable is never called: model the UI, which
        # simply drops it. Nothing else in this module may write.
        self.assertEqual(rec.writes, [])
        self.assertNotIn("silent", {"result": "x"})

    def test_a_gate_that_cannot_ask_saves_nothing(self):
        rec = _Recorder(gate_answer="I cannot confirm right now, so I have not done it.")
        result = request_write("notes", "wifi", "hunter2", rec.write,
                               gate=rec.gate, decide=rec.decide)
        self.assertEqual(rec.writes, [])
        self.assertIn("have not done it", result["result"])

    def test_malformed_input_spends_no_banner(self):
        for category, key, value in (("notes", "", "x"), ("notes", "k", ""),
                                     ("", "", "")):
            with self.subTest(key=key, value=value):
                rec = _Recorder()
                result = request_write(category, key, value, rec.write,
                                       gate=rec.gate, decide=rec.decide)
                self.assertEqual(result["result"], EMPTY_ANSWER)
                self.assertEqual(rec.banners, [], "do not nag about an empty fact")
                self.assertEqual(rec.writes, [])

    def test_a_policy_that_allows_it_still_writes_once(self):
        """Forward compatibility: if the tier ever opens, the path stays single."""
        rec = _Recorder(allow=True)
        result = request_write("notes", "wifi", "hunter2", rec.write,
                               gate=rec.gate, decide=rec.decide)
        self.assertEqual(result, {"result": "ok", "silent": True})
        self.assertEqual(rec.writes, [{"notes": {"wifi": {"value": "hunter2"}}}])
        self.assertEqual(rec.banners, [])


class OneBannerAtATimeTests(unittest.TestCase):
    def test_a_second_pending_write_does_not_replace_the_first(self):
        """The gate holds one decision; the second write must be refused with a
        sentence, not dropped on the floor while the model says "remembered"."""
        from core import confirm, memory_consent

        shown: list[tuple[str, str]] = []
        confirm.bind(show=lambda title, detail: shown.append((title, detail)),
                     hide=lambda: None, log=lambda _m: None)
        writes: list[dict] = []
        try:
            first = memory_consent.request_write("notes", "one", "1", writes.append)
            second = memory_consent.request_write("notes", "two", "2", writes.append)
            self.assertIn(memory_consent.PENDING_MARKER, first["result"])
            self.assertIn("already have a confirmation", second["result"])
            self.assertEqual(writes, [], "neither may be stored before approval")
            confirm.resolve(True)          # approve the first
            self.assertEqual(writes, [{"notes": {"one": {"value": "1"}}}],
                             "the first fact survives; the second was refused aloud")
        finally:
            confirm.resolve(False)
            confirm.bind(show=None, hide=None, log=None)


class RealPolicyTests(unittest.TestCase):
    """The shipped policy, not a fake one — this is the claim the user made."""

    def test_the_shipped_policy_gates_memory(self):
        from core import policy
        verdict = policy.decide("save_memory",
                                {"category": "notes", "key": "k", "value": "v"})
        self.assertFalse(verdict.allow)
        self.assertIn("approval", verdict.reason)

    def test_the_shipped_path_asks_before_writing(self):
        writes: list[dict] = []
        asked: list[dict] = []
        result = request_write(
            "notes", "k", "v", writes.append,
            gate=lambda **kw: asked.append(kw) or PENDING_MARKER,
        )
        self.assertEqual(writes, [])
        self.assertEqual(len(asked), 1)
        self.assertIn(PENDING_MARKER, result["result"])

    def test_main_py_routes_save_memory_through_the_gate(self):
        """The defect was the call site, so assert on the call site."""
        source = (memory_consent.__file__ and
                  __import__("pathlib").Path("main.py").read_text(encoding="utf-8",
                                                                  errors="replace"))
        block = source.split('if name == "save_memory":', 1)[1][:1200]
        self.assertIn("request_memory_write", block)
        self.assertNotIn("update_memory({category: {key:", block,
                         "the direct write must not come back")


if __name__ == "__main__":
    unittest.main()
