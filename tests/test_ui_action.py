"""tests/test_ui_action.py — acting on a ref, and refusing when you must not.

    The adapter below is a fake, and that is the honest way to test this layer:
    what needs proving is the *discipline* — wait for ready, act once, mark the
    snapshot stale, turn every failure into a disposition the caller can use — and
    none of that changes when the tree comes from a real window.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.ui_action import (
    FATAL,
    NEEDS_USER,
    RESNAPSHOT,
    RETRY_SAFE,
    Session,
    UiError,
)
from core.ui_tree import Node


def window(*children, name="Notes"):
    return Node(role="Window", name=name, children=tuple(children))


def button(name, actions=("invoke",)):
    return Node(role="Button", name=name, actions=actions)


def field(name, value=""):
    return Node(role="Edit", name=name, value=value, actions=("set_value", "focus"))


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class FakeAdapter:
    """A tree that can be made unready, and a record of what was asked of it."""

    name = "fake"

    def __init__(self, root=None, *, ready=None, fail=None, caps=("uia",)) -> None:
        self.root = root if root is not None else window(button("Save"), field("Title"))
        self.ready = ready              # ref -> (visible, enabled) or None
        self.fail = fail                # callable(entry, action) -> exception or None
        self.caps = set(caps)
        self.performed: list[tuple[str, str, str]] = []
        self.snapshots = 0
        self.snapshot_ids: list[str] = []
        self._probes = 0

    def capabilities(self):
        return set(self.caps)

    def snapshot(self, app="", root_ref=None, max_depth=None):
        self.snapshots += 1
        return self.root

    def set_snapshot_id(self, snapshot_id):
        self.snapshot_ids.append(snapshot_id)

    def perform(self, entry, action, value=""):
        if self.fail is not None:
            problem = self.fail(entry, action)
            if problem is not None:
                raise problem
        self.performed.append((entry.name, action, value))

    def probe(self, entry):
        if self.ready is None:
            return None
        if callable(self.ready):
            self._probes += 1
            return self.ready(self._probes, entry)
        return self.ready.get(entry.ref, (True, True))


def make_session(adapter=None, clock=None):
    clock = clock or FakeClock()
    adapter = adapter or FakeAdapter()
    return Session(adapter, clock=clock, sleeper=clock.sleep), adapter, clock


class ObserveTests(unittest.TestCase):
    def test_a_fresh_session_has_no_usable_snapshot(self):
        session, _, _ = make_session()
        with self.assertRaises(UiError) as caught:
            session.resolve("Save")
        self.assertEqual(caught.exception.code, "STALE_REF")

    def test_observe_produces_a_snapshot_and_clears_dirty(self):
        session, adapter, _ = make_session()
        snap = session.observe("Notes")
        self.assertEqual(len(snap), 3)
        self.assertFalse(session.dirty)
        self.assertEqual(adapter.snapshots, 1)

    def test_the_adapter_is_told_the_snapshot_id(self):
        session, adapter, _ = make_session()
        snap = session.observe("Notes")
        self.assertEqual(adapter.snapshot_ids[-1], snap.snapshot_id)

    def test_skeleton_clamps_depth(self):
        deep = window(Node(role="Pane", name="P", children=(
            Node(role="Pane", name="Q", children=(button("Deep"),)),)))
        adapter = FakeAdapter(deep)
        session, _, _ = make_session(adapter)
        seen = {}
        original = adapter.snapshot

        def spy(app="", root_ref=None, max_depth=None):
            seen["depth"] = max_depth
            return original(app, root_ref, max_depth)

        adapter.snapshot = spy
        session.observe("Notes", skeleton=True)
        self.assertEqual(seen["depth"], 3)

    def test_drill_takes_a_new_snapshot_id_and_old_refs_die(self):
        session, _, _ = make_session()
        snap = session.observe("Notes")
        old_ref = snap.find("Save").ref
        drilled = session.drill(snap.find("Title").ref)
        self.assertNotEqual(drilled.snapshot_id, snap.snapshot_id)
        with self.assertRaises(UiError) as caught:
            session.resolve(old_ref)
        self.assertEqual(caught.exception.code, "STALE_REF")


class ActTests(unittest.TestCase):
    def test_acting_by_name_works_and_records_it(self):
        session, adapter, _ = make_session()
        session.observe("Notes")
        result = session.act("Save", "click")
        self.assertTrue(result.ok)
        self.assertEqual(result.action, "invoke")        # click coerced to invoke
        self.assertEqual(adapter.performed, [("Save", "invoke", "")])
        self.assertEqual(len(session.history), 1)

    def test_acting_by_ref_works(self):
        session, adapter, _ = make_session()
        snap = session.observe("Notes")
        ref = snap.find("Title").ref
        self.assertTrue(session.act(ref, "type", "Q3 2026").ok)
        self.assertEqual(adapter.performed, [("Title", "set_value", "Q3 2026")])

    def test_the_snapshot_is_stale_after_a_successful_action(self):
        session, _, _ = make_session()
        snap = session.observe("Notes")
        ref = snap.find("Save").ref
        session.act(ref)
        self.assertTrue(session.dirty)
        again = session.act(ref)          # act() reports, it does not raise
        self.assertFalse(again.ok)
        self.assertEqual(again.error.code, "STALE_REF")

    def test_a_failed_action_also_marks_the_snapshot_stale(self):
        adapter = FakeAdapter(fail=lambda entry, action: UiError("ADAPTER_FAILED", "boom"))
        session, _, _ = make_session(adapter)
        session.observe("Notes")
        result = session.act("Save")
        self.assertFalse(result.ok)
        self.assertTrue(session.dirty)

    def test_a_click_on_a_text_field_becomes_focus(self):
        """Clicking a field does not put text in it; it puts the cursor there."""
        session, adapter, _ = make_session()
        session.observe("Notes")
        self.assertTrue(session.act("Title", "click").ok)
        self.assertEqual(adapter.performed[0][1], "focus")

    def test_an_unsupported_action_is_refused_before_the_adapter_is_called(self):
        adapter = FakeAdapter(window(Node(role="Image", name="Chart", actions=())))
        session, _, _ = make_session(adapter)
        session.observe("Notes")
        result = session.act("Chart", "click")
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "UNSUPPORTED_ACTION")
        self.assertEqual(result.error.disposition, NEEDS_USER)
        self.assertEqual(adapter.performed, [])

    def test_a_bare_ref_is_rejected(self):
        session, _, _ = make_session()
        session.observe("Notes")
        result = session.act("e1")
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "INVALID_ARGS")
        self.assertEqual(result.error.disposition, FATAL)

    def test_an_unconfirmed_action_is_declined_not_performed(self):
        session, adapter, _ = make_session()
        session.observe("Notes")
        result = session.act("Save", confirm=lambda entry, action: False)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "DECLINED")
        self.assertEqual(adapter.performed, [])

    def test_a_confirmation_can_allow(self):
        session, _adapter, _unused = make_session()
        session.observe("Notes")
        seen = {}

        def confirm(entry, action):
            seen["name"] = entry.name
            return True

        self.assertTrue(session.act("Save", confirm=confirm).ok)
        self.assertEqual(seen["name"], "Save")


class WaitTests(unittest.TestCase):
    def test_an_element_that_becomes_ready_is_waited_for(self):
        adapter = FakeAdapter(ready=lambda probes, entry: (True, probes >= 3))
        session, adapter, _clock = make_session(adapter)
        session.observe("Notes")
        result = session.act("Save", wait_ms=5000)
        self.assertTrue(result.ok)
        self.assertGreater(result.waited_ms, 0)

    def test_never_enabled_times_out_with_a_retryable_error(self):
        adapter = FakeAdapter(ready=lambda probes, entry: (True, False))
        session, _unused, _clock = make_session(adapter)
        session.observe("Notes")
        result = session.act("Save", wait_ms=200)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "NOT_ENABLED")
        self.assertEqual(result.error.disposition, RETRY_SAFE)
        self.assertTrue(result.error.retryable)

    def test_never_visible_says_visible(self):
        adapter = FakeAdapter(ready=lambda probes, entry: (False, True))
        session, _, _ = make_session(adapter)
        session.observe("Notes")
        result = session.act("Save", wait_ms=100)
        self.assertEqual(result.error.code, "NOT_VISIBLE")

    def test_an_adapter_without_probe_is_not_waited_for(self):
        adapter = FakeAdapter()
        adapter.probe = None
        session, _unused, clock = make_session(adapter)
        session.observe("Notes")
        started = clock.now
        self.assertTrue(session.act("Save", wait_ms=5000).ok)
        self.assertEqual(clock.now, started)


class FailureShapeTests(unittest.TestCase):
    def test_a_missing_element_is_a_resnapshot_hint(self):
        session, _, _ = make_session()
        session.observe("Notes")
        result = session.act("Publish")
        self.assertFalse(result.ok)
        self.assertEqual(result.error.disposition, RESNAPSHOT)

    def test_an_ambiguous_name_never_picks_one(self):
        adapter = FakeAdapter(window(button("Save"), button("Save")))
        session, adapter, _ = make_session(adapter)
        session.observe("Notes")
        result = session.act("Save")
        self.assertEqual(result.error.code, "AMBIGUOUS_TARGET")
        self.assertEqual(adapter.performed, [])

    def test_an_adapter_crash_becomes_a_result_not_an_exception(self):
        def explode(entry, action):
            return RuntimeError("COM object went away")

        adapter = FakeAdapter(fail=explode)
        session, _, _ = make_session(adapter)
        session.observe("Notes")
        result = session.act("Save")
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "ADAPTER_FAILED")
        self.assertTrue(result.error.retryable)

    def test_an_error_that_already_has_a_code_is_passed_through(self):
        adapter = FakeAdapter(fail=lambda entry, action: UiError("NOT_ENABLED", "greyed out"))
        session, _, _ = make_session(adapter)
        session.observe("Notes")
        self.assertEqual(session.act("Save").error.code, "NOT_ENABLED")

    def test_no_adapter_is_reported_honestly(self):
        session = Session(None)
        with self.assertRaises(UiError) as caught:
            session.observe("Notes")
        self.assertEqual(caught.exception.code, "NO_ADAPTER")
        self.assertEqual(caught.exception.disposition, FATAL)

    def test_capabilities_survive_a_broken_adapter(self):
        class Broken(FakeAdapter):
            def capabilities(self):
                raise RuntimeError("nope")

        session = Session(Broken())
        self.assertEqual(session.capabilities(), set())


class ResultShapeTests(unittest.TestCase):
    def test_a_success_dict_has_no_error_field(self):
        session, _, _ = make_session()
        session.observe("Notes")
        payload = session.act("Save").as_dict()
        self.assertTrue(payload["ok"])
        self.assertNotIn("error", payload)
        self.assertIn("snapshot_id", payload)

    def test_a_failure_dict_carries_the_disposition(self):
        session, _, _ = make_session()
        session.observe("Notes")
        payload = session.act("Publish").as_dict()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["disposition"], RESNAPSHOT)
        self.assertTrue(payload["retryable"])

    def test_a_result_can_be_spoken(self):
        session, _, _ = make_session()
        session.observe("Notes")
        spoken = session.act("Save").spoken()
        self.assertIn("Save", spoken)
        self.assertNotIn("@", spoken)


class BatchTests(unittest.TestCase):
    def test_a_batch_runs_in_order(self):
        session, _adapter, _unused = make_session()
        session.observe("Notes")
        results = session.batch([
            {"target": "Title", "action": "type", "value": "Q3"},
        ])
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].ok)

    def test_a_batch_stops_at_a_failure_that_is_not_retryable(self):
        session, _adapter, _unused = make_session()
        session.observe("Notes")
        results = session.batch([
            {"target": "Publish", "action": "click"},
            {"target": "Save", "action": "click"},
        ])
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].ok)

    def test_malformed_operations_are_refused_not_crashed_on(self):
        session, _, _ = make_session()
        session.observe("Notes")
        results = session.batch(["not a dict"])
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error.code, "INVALID_ARGS")

    def test_a_batch_runs_every_step_not_just_the_first(self):
        """The bug this replaced: an action marks the snapshot stale, so step two
        of every batch failed and a three-step form fill performed nothing."""
        adapter = FakeAdapter(window(field("Title"), field("Author"), button("Save")))
        session, adapter, _unused = make_session(adapter)
        session.observe("Notes")
        results = session.batch([
            {"target": "Title", "do": "type", "value": "Q3"},
            {"target": "Author", "do": "type", "value": "me"},
            {"target": "Save", "do": "click"},
        ])
        self.assertEqual([r.ok for r in results], [True, True, True])
        self.assertEqual(adapter.performed[-1], ("Save", "invoke", ""))

    def test_a_batch_looks_again_before_each_step(self):
        adapter = FakeAdapter(window(button("A"), button("B")))
        session, adapter, _unused = make_session(adapter)
        session.observe("Notes")
        before = adapter.snapshots
        session.batch([{"target": "A"}, {"target": "B"}])
        self.assertGreaterEqual(adapter.snapshots - before, 1)

    def test_a_ref_for_a_later_step_is_refused_with_advice(self):
        """Refs do not survive the look-again, and the message has to say so."""
        adapter = FakeAdapter(window(button("A"), button("B")))
        session, adapter, _unused = make_session(adapter)
        snap = session.observe("Notes")
        first_ref = snap.find("A").ref
        results = session.batch([
            {"target": "A"},
            {"target": first_ref},
        ])
        self.assertTrue(results[0].ok)
        self.assertFalse(results[1].ok)
        self.assertIn("use the element's name", results[1].message)
        self.assertEqual(adapter.performed, [("A", "invoke", "")])

    def test_an_empty_batch_does_nothing(self):
        session, adapter, _unused = make_session()
        session.observe("Notes")
        self.assertEqual(session.batch([]), [])
        self.assertEqual(adapter.performed, [])


if __name__ == "__main__":
    unittest.main()
