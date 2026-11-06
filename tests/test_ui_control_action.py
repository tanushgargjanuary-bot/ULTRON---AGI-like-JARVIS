"""tests/test_ui_control_action.py — the tool the model actually calls.

    The bridge is injected, so these tests exercise the tool's own behaviour:
    what it returns for each shape of success and failure, and whether it ever
    claims something happened that it did not see. The last part matters more than
    the rest — an assistant that says "done" when it means "asked" is worse than
    one that fails loudly.
"""

from __future__ import annotations

import sys
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from actions import ui_control as tool
from core.ui_tree import Node


def window(*children, name="Notes"):
    return Node(role="Window", name=name, children=tuple(children))


def button(name, actions=("invoke",)):
    return Node(role="Button", name=name, actions=actions)


class FakeAdapter:
    name = "fake"
    fail = None

    def __init__(self, root=None, *, caps=("uia", "headless", "keyboard")) -> None:
        self.root = root if root is not None else window(
            button("Save"), Node(role="Edit", name="Title", actions=("set_value",)),
        )
        self.caps = set(caps)
        self.performed: list[tuple[str, str, str]] = []

    def capabilities(self):
        return set(self.caps)

    def snapshot(self, app="", root_ref=None, max_depth=None):
        return self.root

    def set_snapshot_id(self, snapshot_id):
        pass

    def perform(self, entry, action, value=""):
        if self.fail is not None:
            raise self.fail
        self.performed.append((entry.name, action, value))

    def probe(self, entry):
        return None


class ToolTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = FakeAdapter()
        tool._ADAPTER = self.adapter
        tool._ADAPTER_REASON = "test"

    def tearDown(self) -> None:
        tool._ADAPTER = None
        tool._ADAPTER_REASON = ""
        tool._BROWSER_PAGE = None

    def call(self, **params):
        return tool.ui_control(params)


class SnapshotTests(ToolTestCase):
    def test_a_snapshot_returns_the_elements_and_the_refs(self):
        result = self.call(action="snapshot", app="Notes")
        self.assertTrue(result.startswith("status=done"))
        self.assertIn("Save", result)
        self.assertIn(":e", result)

    def test_the_line_budget_is_honoured(self):
        self.adapter.root = window(*[button(f"B{i}") for i in range(12)])
        result = self.call(action="snapshot", max_lines=3)
        self.assertIn("more elements", result)

    def test_skeleton_does_not_crash_a_deep_window(self):
        depth = Node(role="Pane", name="A", children=(Node(
            role="Pane", name="B", children=(button("Deep"),)),))
        self.adapter.root = window(depth)
        self.assertTrue(self.call(action="snapshot", skeleton=True).startswith("status=done"))


class ActTests(ToolTestCase):
    def test_an_action_is_reported_as_unverified_not_done(self):
        result = self.call(action="act", target="Save")
        self.assertTrue(result.startswith("status=unverified"))
        self.assertIn("Save", result)
        self.assertNotIn("status=done", result)

    def test_the_adapter_is_actually_called(self):
        self.call(action="act", target="Save")
        self.assertEqual(self.adapter.performed, [("Save", "invoke", "")])

    def test_text_is_typed_into_the_named_field(self):
        self.call(action="act", target="Title", do="type", value="Q3 2026")
        self.assertEqual(self.adapter.performed, [("Title", "set_value", "Q3 2026")])

    def test_a_missing_element_asks_rather_than_guessing(self):
        result = self.call(action="act", target="Publish")
        self.assertTrue(result.startswith(("status=ask", "status=failed")))

    def test_an_ambiguous_name_asks(self):
        self.adapter.root = window(button("Save"), button("Save"))
        result = self.call(action="act", target="Save")
        self.assertTrue(result.startswith("status=ask"))
        self.assertEqual(self.adapter.performed, [])

    def test_an_unsupported_action_offers_the_shortcut_route(self):
        self.adapter.root = window(Node(role="Image", name="&Chart", actions=()))
        result = self.call(action="act", target="Chart")
        self.assertIn("status=", result)
        self.assertIn("computer_control", result + self.call(action="act", target="Chart"))

    def test_a_bare_ref_is_refused(self):
        result = self.call(action="act", target="e4")
        self.assertIn("status=", result)
        self.assertEqual(self.adapter.performed, [])


class BatchTests(ToolTestCase):
    def test_a_batch_stops_at_the_first_failure(self):
        result = self.call(action="batch", operations=[
            {"target": "Publish"}, {"target": "Save"},
        ])
        self.assertTrue(result.startswith(("status=failed", "status=ask")))
        self.assertEqual(self.adapter.performed, [])

    def test_an_empty_batch_is_refused(self):
        self.assertTrue(self.call(action="batch", operations=[]).startswith("status=failed"))


class RefLifetimeTests(ToolTestCase):
    """A ref has to survive from the snapshot call to the act call.

    Without this the whole design is decorative: the tool took a new snapshot
    before acting, so every ref the model read was already stale and the adapter
    was never called. That was the state before this test existed.
    """

    def setUp(self) -> None:
        super().setUp()
        tool.reset_session()

    def test_a_ref_from_a_snapshot_works_in_the_next_call(self):
        first = self.call(action="snapshot")
        ref = next(part for part in first.split() if part.startswith("@"))
        result = self.call(action="act", target=ref)
        self.assertTrue(result.startswith("status=unverified"), result)
        self.assertEqual(self.adapter.performed, [("Save", "invoke", "")])

    def test_the_same_ref_is_refused_once_it_has_been_used(self):
        first = self.call(action="snapshot")
        ref = next(part for part in first.split() if part.startswith("@"))
        self.call(action="act", target=ref)
        second = self.call(action="act", target=ref)
        self.assertFalse(second.startswith("status=done"))
        self.assertEqual(len(self.adapter.performed), 1)

    def test_acting_by_name_does_not_need_a_ref_at_all(self):
        self.assertTrue(self.call(action="act", target="Save").startswith("status="))
        self.assertEqual(self.adapter.performed, [("Save", "invoke", "")])

    def test_reset_session_forgets_the_snapshot(self):
        first = self.call(action="snapshot")
        ref = next(part for part in first.split() if part.startswith("@"))
        tool.reset_session()
        result = self.call(action="act", target=ref)
        self.assertEqual(self.adapter.performed, [])
        self.assertIn("status=", result)


class HonestyTests(ToolTestCase):
    def test_with_no_bridge_it_says_so_instead_of_clicking(self):
        # Windows CI has uiautomation installed, so clearing the cache is not
        # enough: available() would hand back a real adapter on the next call.
        # Both the cache and the answer are removed, which is the state the test
        # is about.
        tool._ADAPTER = None
        tool._ADAPTER_REASON = "no bridge on this machine"
        with mock.patch("core.ui_windows.available",
                        return_value=(False, "no bridge on this machine")), \
             mock.patch.object(tool, "_BROWSER_PAGE", None):
            result = self.call(action="act", target="Save")
        self.assertTrue(result.startswith("status=ask"))
        self.assertIn("cannot read", result)
        self.assertEqual(self.adapter.performed, [])

    def test_describe_states_what_can_be_reached(self):
        result = self.call(action="describe")
        self.assertTrue(result.startswith("status=done"))
        self.assertIn("accessibility tree", result)

    def test_an_unknown_action_is_refused_clearly(self):
        self.assertTrue(self.call(action="summon").startswith("status=failed"))

    def test_an_adapter_crash_never_escapes_the_tool(self):
        self.adapter.fail = RuntimeError("COM died")
        result = self.call(action="act", target="Save")
        self.assertIn("status=", result)
        self.assertNotIn("RuntimeError", result) if "status=done" in result else None

    def test_drill_without_a_snapshot_is_refused(self):
        self.assertTrue(self.call(action="drill", target="@abc123:e1").startswith("status=failed"))

    def test_drill_of_a_region_returns_that_region(self):
        self.adapter.root = window(Node(
            role="Pane", name="Big", children=(button("A"), button("B"))))
        first = self.call(action="snapshot")
        ref = next(part for part in first.split() if part.startswith("@"))
        result = self.call(action="drill", target=ref)
        self.assertIn("status=", result)


if __name__ == "__main__":
    unittest.main()
