"""tests/test_ui_tree.py — the snapshot model, without an operating system.

    Everything here is hand-built: `Node` trees in, refs and text out. That is the
    point. The part of computer use that is worth testing offline is the part that
    decides *what a ref means* and *when it stops meaning it* — the same logic the
    Windows adapter leans on, with no Windows in the way.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.ui_tree import (
    Node,
    Snapshot,
    UiTreeError,
    coerce_actions,
    is_ref,
    new_snapshot_id,
)


def button(name, **kwargs):
    return Node(role="Button", name=name, actions=("invoke",), **kwargs)


def field(name, value="", **kwargs):
    return Node(role="Edit", name=name, value=value, actions=("set_value", "focus"), **kwargs)


def window(*children, name="Untitled"):
    return Node(role="Window", name=name, children=tuple(children))


def sample():
    return window(
        Node(role="ToolBar", name="", children=(
            button("Save"),
            button("Open"),
            Node(role="CheckBox", name="Sync", actions=("toggle",)),
        )),
        Node(role="Document", name="Report", children=(
            field("Title", "Q3"),
            Node(role="Edit", name="Password", actions=("set_value",), sensitive=True,
                 value="hunter2"),
        )),
        name="Notes",
    )


class CaptureTests(unittest.TestCase):
    def test_refs_are_qualified_and_ordered(self):
        snap = Snapshot.capture(sample(), app="Notes")
        self.assertEqual(len(snap), 8)      # window, toolbar + 3, document + 2
        first = snap.refs()[0]
        self.assertTrue(is_ref(first))
        self.assertEqual(first, f"@{snap.snapshot_id}:e0")
        self.assertEqual(snap.refs()[1], f"@{snap.snapshot_id}:e1")

    def test_refs_are_unique(self):
        snap = Snapshot.capture(sample())
        self.assertEqual(len(set(snap.refs())), len(snap.refs()))

    def test_parent_and_children_links_are_bidirectional(self):
        snap = Snapshot.capture(sample())
        save = snap.find("Save")
        self.assertIsNotNone(save.parent)
        self.assertIn(save.ref, snap.entries[save.parent].children)

    def test_a_bare_ref_is_invalid_not_merely_missing(self):
        snap = Snapshot.capture(sample())
        with self.assertRaises(UiTreeError) as caught:
            snap.get("e3")
        self.assertEqual(caught.exception.code, "INVALID_ARGS")

    def test_a_ref_from_another_snapshot_is_stale(self):
        first = Snapshot.capture(sample())
        second = Snapshot.capture(sample())
        foreign = first.refs()[3]
        with self.assertRaises(UiTreeError) as caught:
            second.get(foreign)
        self.assertEqual(caught.exception.code, "STALE_REF")

    def test_an_index_beyond_the_end_is_stale(self):
        snap = Snapshot.capture(sample())
        with self.assertRaises(UiTreeError) as caught:
            snap.get(f"@{snap.snapshot_id}:e999")
        self.assertEqual(caught.exception.code, "STALE_REF")

    def test_a_fixed_snapshot_id_can_be_requested(self):
        snap = Snapshot.capture(sample(), snapshot_id="abc123xyz9")
        self.assertEqual(snap.refs()[0], "@abc123xyz9:e0")

    def test_snapshot_ids_differ(self):
        self.assertNotEqual(new_snapshot_id(), new_snapshot_id())


class FindTests(unittest.TestCase):
    def setUp(self):
        self.snap = Snapshot.capture(sample(), app="Notes")

    def test_find_by_substring(self):
        self.assertEqual(self.snap.find("save").name, "Save")

    def test_find_is_case_insensitive(self):
        self.assertEqual(self.snap.find("SYNC").role, "check_box")

    def test_find_with_role_narrows(self):
        self.assertEqual(self.snap.find("title", role="edit").name, "Title")

    def test_exact_match_does_not_take_a_longer_name(self):
        snap = Snapshot.capture(window(button("Save as"), button("Save")))
        self.assertEqual(snap.find("Save", exact=True).name, "Save")

    def test_two_matching_buttons_are_ambiguous(self):
        snap = Snapshot.capture(window(button("Save"), Node(
            role="ToolBar", name="", children=(button("Save"),))))
        with self.assertRaises(UiTreeError) as caught:
            snap.find("Save")
        self.assertEqual(caught.exception.code, "AMBIGUOUS_TARGET")
        self.assertIn("Save", str(caught.exception))

    def test_missing_is_not_found(self):
        with self.assertRaises(UiTreeError) as caught:
            self.snap.find("Publish to production")
        self.assertEqual(caught.exception.code, "NOT_FOUND")

    def test_hidden_elements_need_to_be_asked_for(self):
        snap = Snapshot.capture(window(button("Ghost", visible=False)))
        with self.assertRaises(UiTreeError):
            snap.find("Ghost")
        self.assertEqual(snap.find("Ghost", include_hidden=True).name, "Ghost")

    def test_disabled_elements_are_still_findable(self):
        snap = Snapshot.capture(window(button("Apply", enabled=False)))
        entry = snap.find("Apply")
        self.assertFalse(entry.enabled)

    def test_sensitive_elements_are_never_searchable(self):
        with self.assertRaises(UiTreeError):
            self.snap.find("Password")

    def test_empty_query_returns_the_first_actionable_element(self):
        snap = Snapshot.capture(window(button("Only")))
        self.assertEqual(snap.find("").name, "Only")


class RedactionTests(unittest.TestCase):
    def test_a_password_never_reaches_the_snapshot(self):
        snap = Snapshot.capture(sample())
        self.assertNotIn("hunter2", snap.render())
        self.assertNotIn("hunter2", json.dumps(snap.to_dict()))

    def test_redactions_are_counted(self):
        snap = Snapshot.capture(sample())
        self.assertEqual(snap.redacted_count, 1)
        self.assertIn("1 redacted", snap.render().splitlines()[0])

    def test_a_sensitive_role_is_enough_on_its_own(self):
        node = Node(role="password", name="PIN", value="1234")
        snap = Snapshot.capture(window(node))
        self.assertTrue(snap.find("", include_hidden=True))
        self.assertNotIn("1234", snap.render())


class TruncationTests(unittest.TestCase):
    def test_depth_limit_marks_containers_with_counts(self):
        tree = window(Node(role="ToolBar", name="Tools", children=(
            button("A"), button("B"), button("C"))))
        snap = Snapshot.capture(tree, max_depth=1)
        toolbar = next(e for e in snap if e.role == "tool_bar")
        self.assertTrue(toolbar.truncated)
        self.assertEqual(toolbar.children_total, 3)
        self.assertEqual(snap.truncated_count, 1)

    def test_drill_targets_are_exactly_the_truncated_containers(self):
        tree = window(Node(role="Pane", name="Left", children=(button("X"),)),
                      Node(role="Pane", name="Right", children=(button("Y"),)))
        snap = Snapshot.capture(tree, max_depth=1)
        names = {entry.name for entry in snap.drill_targets()}
        self.assertEqual(names, {"Left", "Right"})

    def test_node_budget_stops_the_walk_without_raising(self):
        wide = window(*[button(f"B{i}") for i in range(500)])
        snap = Snapshot.capture(wide, max_nodes=50)
        self.assertLessEqual(len(snap), 51)
        self.assertGreater(snap.truncated_count, 0)

    def test_render_explains_the_truncation(self):
        snap = Snapshot.capture(window(Node(role="Pane", name="Big",
                                            children=(button("A"),))), max_depth=1)
        self.assertIn("drill with", snap.render())


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.snap = Snapshot.capture(sample(), app="Notes")
        self.text = self.snap.render()

    def test_every_rendered_line_carries_a_usable_ref(self):
        for line in self.text.splitlines()[1:]:
            with self.subTest(line=line):
                token = [part for part in line.split() if part.startswith("@")]
                self.assertTrue(token)
                self.snap.get(token[0])

    def test_actions_are_listed(self):
        self.assertIn("[invoke]", self.text)

    def test_containers_without_names_are_dropped(self):
        self.assertNotIn('pane ""', self.text)

    def test_line_budget_is_respected(self):
        snap = Snapshot.capture(window(*[button(f"B{i}") for i in range(80)]))
        text = snap.render(max_lines=10)
        self.assertLessEqual(len(text.splitlines()), 12)
        self.assertIn("more elements", text)

    def test_header_reports_the_app_and_the_count(self):
        header = self.text.splitlines()[0]
        self.assertIn("Notes", header)
        self.assertIn(str(len(self.snap)), header)

    def test_json_round_trips(self):
        payload = json.loads(self.snap.to_json())
        self.assertEqual(payload["count"], len(self.snap))
        self.assertEqual(len(payload["elements"]), len(self.snap))

    def test_summary_is_one_sentence(self):
        summary = self.snap.summary()
        self.assertIn("Notes", summary)
        self.assertEqual(summary.count("."), 1)


class RegionTests(unittest.TestCase):
    def test_region_returns_the_subtree(self):
        snap = Snapshot.capture(sample())
        document = snap.find("Report")
        names = [entry.name for entry in snap.region(document.ref)]
        self.assertIn("Title", names)
        self.assertNotIn("Save", names)

    def test_region_of_a_leaf_is_itself(self):
        snap = Snapshot.capture(sample())
        save = snap.find("Save")
        self.assertEqual([e.ref for e in snap.region(save.ref)], [save.ref])


class DeepTreeTests(unittest.TestCase):
    def test_a_very_deep_tree_does_not_recurse(self):
        node = button("leaf")
        for _ in range(4000):
            node = Node(
                role="Pane", name="", actions=(), children=(node,)
            )
        snap = Snapshot.capture(node, max_depth=5000, max_nodes=5000)
        self.assertEqual(len(snap), 4001)

    def test_walk_is_iterative_too(self):
        node = Node(role="Pane", name="", children=())
        for index in range(2000):
            node = Node(role="Pane", name=f"p{index}", children=(node,))
        self.assertEqual(sum(1 for _ in node.walk()), 2001)


class ActionCoercionTests(unittest.TestCase):
    def test_exact_action_wins(self):
        self.assertEqual(coerce_actions("invoke", ("invoke", "focus")), "invoke")

    def test_click_becomes_invoke(self):
        self.assertEqual(coerce_actions("click", ("invoke", "focus")), "invoke")

    def test_type_becomes_set_value(self):
        self.assertEqual(coerce_actions("type", ("set_value", "focus")), "set_value")

    def test_spaces_and_case_are_ignored(self):
        self.assertEqual(coerce_actions("Set Value", ("set_value",)), "set_value")

    def test_an_unsupported_action_lists_what_is_supported(self):
        with self.assertRaises(UiTreeError) as caught:
            coerce_actions("drag", ("invoke", "focus"))
        self.assertEqual(caught.exception.code, "UNSUPPORTED_ACTION")
        self.assertIn("invoke", str(caught.exception))

    def test_an_element_with_no_actions_is_refused(self):
        with self.assertRaises(UiTreeError) as caught:
            coerce_actions("click", ())
        self.assertEqual(caught.exception.code, "UNSUPPORTED_ACTION")


if __name__ == "__main__":
    unittest.main()
