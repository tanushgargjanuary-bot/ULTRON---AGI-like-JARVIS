"""`self_modify` and `system_prompt`: the two tools that change the assistant itself.

`self_modify` rewrites the program's source. It is not on any policy list, so it was
guarded only by the fallback for tools nobody classified, and the approval banner told
the owner "unclassified tool - treated conservatively" — true of a tool nobody had
looked at, and no help to a person deciding whether to let the program rewrite itself.
It is named now, and stays guarded for every action it has.

The second class is the general rule behind `tests/test_prompt_gate.py`: a tool that is
exempt from the approval banner because it "carries its own gate" must not let the
MODEL satisfy that gate by filling in an argument.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from actions import prompt_editor  # noqa: E402
from actions import self_change as self_change_tool  # noqa: E402
from core import policy  # noqa: E402

# Parameter names by which a model could vouch for itself.
SELF_VOUCHING = {"channel", "confirmed", "confirm", "approved", "approval", "token",
                 "consent", "authorized", "authorised", "override", "force", "yes"}


class SelfModifyIsGuardedByName(unittest.TestCase):
    def test_it_is_named_and_the_banner_says_what_it_is(self):
        decision = policy.classify("self_modify", {"action": "apply"})
        self.assertEqual(decision.tier, policy.Tier.GUARDED)
        self.assertFalse(decision.allow)
        self.assertNotIn("unclassified", decision.reason)
        self.assertIn("own source code", decision.reason)

    def test_every_action_the_tool_has_asks_first(self):
        actions = set(self_change_tool.ACTIONS) | {"", "no-such-action"}
        for action in sorted(actions):
            with self.subTest(action=action):
                decision = policy.classify("self_modify", {"action": action})
                self.assertFalse(decision.allow, f"self_modify action={action!r} ran unasked")

    def test_a_missing_or_malformed_argument_set_still_asks(self):
        for args in (None, {}, {"action": None}, {"action": 5}, {"path": "core/policy.py"}):
            with self.subTest(args=args):
                self.assertFalse(policy.decide("self_modify", args).allow)

    def test_the_reason_is_what_the_banner_shows(self):
        text = str(policy.decide("self_modify", {"action": "propose"}))
        self.assertIn("ask", text)
        self.assertIn("own source code", text)


class AToolThatCarriesItsOwnGateCannotBeVouchedForByTheModel(unittest.TestCase):
    TOOLS = {"system_prompt": prompt_editor.TOOL}

    def test_every_exempt_tool_with_a_schema_here_has_no_self_vouching_parameter(self):
        for name in policy.BYPASS_TOOLS:
            tool = self.TOOLS.get(name)
            if tool is None:
                continue                      # a plugin; its schema lives in plugins/
            with self.subTest(tool=name):
                properties = {p.lower() for p in tool["parameters"]["properties"]}
                self.assertEqual(properties & SELF_VOUCHING, set(),
                                 f"{name} lets the model say where a confirmation came from")

    def test_the_plugin_that_is_exempt_takes_only_an_operation_and_a_payload(self):
        from plugins import custom_jarvis
        properties = set(custom_jarvis.PLUGIN["parameters"]["properties"])
        self.assertEqual(properties, {"operation", "payload_json"})

    def test_self_modify_takes_no_argument_the_model_could_vouch_with(self):
        # It is not exempt (every call asks), but its second confirmation used to be a `channel` the
        # model wrote. That argument is gone; a model that sends one is ignored (tests/test_self_change.py).
        properties = {p.lower() for p in self_change_tool.TOOL["parameters"]["properties"]}
        self.assertEqual(properties & SELF_VOUCHING, set(),
                         "self_modify lets the model say where a confirmation came from")

    def test_the_list_of_exempt_tools_has_not_grown_unnoticed(self):
        # Adding a name here removes the approval banner from that tool. If the list
        # must grow, this test is the place a reviewer is made to look.
        self.assertEqual(set(policy.BYPASS_TOOLS), {"custom_jarvis", "system_prompt"})


if __name__ == "__main__":
    unittest.main()
