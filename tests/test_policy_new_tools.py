"""Where the twelve new plugins sit in the risk table.

Two failure modes are equally bad here. Asking permission to format a JSON string
is the "excessive prompt for a trivial action" the owner rejected. Letting a tool
spawn a renderer, post to a service or probe a port without asking is the other
one. These tests pin both directions, and pin the conservative default.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from core import policy
from core.plugin_loader import discover_plugins

PLUGINS = Path(__file__).resolve().parent.parent / "plugins"


class Tiers(unittest.TestCase):
    def tier(self, name, **args):
        return policy.classify(name, args)

    def test_local_converters_are_routine(self):
        for name in ("dev_json", "dev_regex", "dev_hash", "dev_cron", "crypto_ident"):
            decision = self.tier(name, action="validate")
            self.assertEqual(decision.tier, policy.Tier.ROUTINE, name)
            self.assertTrue(decision.allow, name)

    def test_net_check_reads_are_not_prompts(self):
        self.assertEqual(self.tier("net_check", action="dns").tier, policy.Tier.OBSERVE)
        self.assertEqual(self.tier("net_check", action="headers").tier, policy.Tier.ROUTINE)

    def test_net_check_port_needs_a_decision(self):
        decision = self.tier("net_check", action="port")
        self.assertEqual(decision.tier, policy.Tier.GUARDED)
        self.assertFalse(decision.allow)

    def test_asking_a_tool_if_it_is_alive_is_a_read(self):
        for name in ("rea_bridge", "hyperframes_bridge", "hypit_bridge"):
            self.assertEqual(self.tier(name, action="help").tier, policy.Tier.OBSERVE, name)
        for name in ("hindsight_bridge", "voicestudio_bridge"):
            self.assertEqual(self.tier(name, action="status").tier, policy.Tier.OBSERVE, name)

    def test_making_a_tool_work_is_guarded(self):
        for name in ("hyperframes_bridge", "hypit_bridge"):
            decision = self.tier(name, action="command")
            self.assertEqual(decision.tier, policy.Tier.GUARDED, name)
            self.assertFalse(decision.allow, name)
        for name in ("hindsight_bridge", "voicestudio_bridge"):
            self.assertEqual(self.tier(name, action="request").tier, policy.Tier.GUARDED, name)

    def test_a_bridge_with_no_action_is_guarded_not_trusted(self):
        for name in ("rea_bridge", "hyperframes_bridge", "hypit_bridge",
                     "hindsight_bridge", "voicestudio_bridge"):
            decision = self.tier(name)
            self.assertEqual(decision.tier, policy.Tier.GUARDED, name)
            self.assertFalse(decision.allow, name)

    def test_every_shipped_plugin_is_classified(self):
        """A plugin that lands in "unclassified" is a plugin that always asks."""
        registry = discover_plugins(PLUGINS, core_tool_names=set(), logger=lambda _m: None)
        for row in registry.list_for_ui():
            decision = self.tier(row["name"], action="")
            reason = decision.reason.lower()
            if row["name"] == "custom_jarvis":
                continue          # carries its own per-step gate, by design
            self.assertNotIn("unclassified", reason, row["name"])

    def test_policy_never_raises_on_junk(self):
        for name in ("", None, 42, "no_such_tool"):
            for args in ({}, {"action": None}, {"action": 5}, {"port": "x"}):
                policy.decide(name, args)


class Wired(unittest.TestCase):
    def test_plugin_declarations_reach_the_model(self):
        registry = discover_plugins(PLUGINS, core_tool_names=set(), logger=lambda _m: None)
        names = {decl.get("name") for decl in registry.get_tool_declarations()}
        for expected in ("dev_json", "net_check", "rea_bridge", "voicestudio_bridge"):
            self.assertIn(expected, names)

    def test_plugin_declarations_carry_parameters(self):
        registry = discover_plugins(PLUGINS, core_tool_names=set(), logger=lambda _m: None)
        for decl in registry.get_tool_declarations():
            if decl.get("name") == "dev_json":
                self.assertIn("text", decl["parameters"]["properties"])
                return
        self.fail("dev_json is not in the model's tool list")


if __name__ == "__main__":
    unittest.main()
