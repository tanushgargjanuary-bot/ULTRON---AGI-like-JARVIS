"""Offline tests for provider routing and voice switching (core/routing.py).

Everything here is pure logic: no socket is opened, no key is read, no provider
name is baked in. The rules under test are the agreed ones — quota is tracked per
QUOTA GROUP (not per key), a fallback may not silently cost money, share data, or
move onto this machine, and a switch only works against providers the user
actually configured.
"""

import unittest

from core import routing
from core.routing import (
    Fallback,
    Provider,
    Purpose,
    QuotaLedger,
    Refusal,
    Route,
    RoutingTable,
)


def table(**kwargs):
    value = RoutingTable(**kwargs)
    return value


class ProviderTests(unittest.TestCase):
    def test_quota_group_defaults_to_the_provider(self):
        self.assertEqual(Provider("Groq").quota_group, "groq")

    def test_two_keys_on_one_account_share_a_group(self):
        groq = Provider("Groq")
        groq_key_2 = Provider("Groq", quota_group=groq.quota_group)
        self.assertEqual(groq.quota_group, groq_key_2.quota_group)


class QuotaTests(unittest.TestCase):
    def setUp(self):
        self.now = [1000.0]
        self.today = ["2026-11-05"]
        self.ledger = QuotaLedger(clock=lambda: self.now[0],
                                  today=lambda: self.today[0])

    def test_usage_accumulates(self):
        self.ledger.configure("groq", requests_per_day=3)
        self.ledger.record("groq", tokens=100)
        self.ledger.record("groq", tokens=50)
        snapshot = self.ledger.snapshot()["groq"]
        self.assertEqual(snapshot["used_requests"], 2)
        self.assertEqual(snapshot["used_tokens"], 150)

    def test_a_daily_limit_binds(self):
        self.ledger.configure("groq", requests_per_day=2)
        self.assertTrue(self.ledger.available("groq"))
        self.ledger.record("groq")
        self.ledger.record("groq")
        self.assertFalse(self.ledger.available("groq"))

    def test_the_counter_rolls_over_at_the_day_boundary(self):
        self.ledger.configure("groq", requests_per_day=1)
        self.ledger.record("groq")
        self.assertFalse(self.ledger.available("groq"))
        self.today[0] = "2026-11-06"
        self.assertTrue(self.ledger.available("groq"))

    def test_retry_after_blocks_the_whole_group_then_expires(self):
        self.ledger.block_for("groq", 30)
        self.assertFalse(self.ledger.available("groq"))
        self.now[0] += 31
        self.assertTrue(self.ledger.available("groq"))

    def test_an_unconfigured_group_is_available(self):
        self.assertTrue(self.ledger.available("never-seen"))


class RoutingTableTests(unittest.TestCase):
    def build(self):
        value = table()
        value.add_provider(Provider("Google AI Studio", quota_group="google"))
        value.add_provider(Provider("Groq", quota_group="groq"))
        value.add_provider(Provider("Ollama", local=True))
        value.add_provider(Provider("SomePaid", paid=True))
        value.add_provider(Provider("SomeFree", shares_data=True))
        return value

    def test_a_route_can_be_set_per_purpose(self):
        value = self.build()
        value.set_route(Purpose.CONVERSATION, "Groq", "qwen/qwen3.8-27b")
        value.set_route(Purpose.CRITIC, "Google AI Studio", "gemma-4-31b")
        self.assertEqual(value.route_for(Purpose.CONVERSATION).model, "qwen/qwen3.8-27b")
        self.assertEqual(value.route_for("critic").provider, "Google AI Studio")

    def test_an_unknown_provider_is_refused(self):
        with self.assertRaises(Refusal):
            self.build().set_route(Purpose.CONVERSATION, "NotConfigured")

    def test_provider_lookup_is_case_insensitive(self):
        self.assertIsNotNone(self.build().provider("groq"))

    def test_choose_returns_the_primary(self):
        value = self.build()
        value.set_route(Purpose.CONVERSATION, "Groq", "m")
        self.assertEqual(value.choose(Purpose.CONVERSATION), Route("Groq", "m"))

    def test_an_exhausted_primary_moves_to_the_next_allowed_fallback(self):
        value = self.build()
        value.set_route(Purpose.CONVERSATION, "Groq", "m")
        value.fallbacks = [Fallback(Route("Google AI Studio", "g")),
                           Fallback(Route("Ollama"))]
        value.ledger.configure("groq", requests_per_day=1)
        value.record_use(Route("Groq", "m"))
        self.assertEqual(value.choose(Purpose.CONVERSATION), Route("Google AI Studio", "g"))

    def test_a_paid_fallback_is_not_taken_silently(self):
        value = self.build()
        value.set_route(Purpose.CONVERSATION, "Groq", "m")
        value.fallbacks = [Fallback(Route("SomePaid"))]
        value.ledger.configure("groq", requests_per_day=1)
        value.record_use(Route("Groq", "m"))
        with self.assertRaises(Refusal):
            value.choose(Purpose.CONVERSATION)

    def test_a_data_sharing_fallback_is_not_taken_silently(self):
        value = self.build()
        value.set_route(Purpose.CONVERSATION, "Groq", "m")
        value.fallbacks = [Fallback(Route("SomeFree"))]
        value.ledger.configure("groq", requests_per_day=1)
        value.record_use(Route("Groq", "m"))
        with self.assertRaises(Refusal):
            value.choose(Purpose.CONVERSATION)

    def test_an_explicitly_permitted_paid_fallback_is_used(self):
        value = self.build()
        value.allow_paid_fallback = True
        value.set_route(Purpose.CONVERSATION, "Groq", "m")
        value.fallbacks = [Fallback(Route("SomePaid"))]
        value.ledger.configure("groq", requests_per_day=1)
        value.record_use(Route("Groq", "m"))
        self.assertEqual(value.choose(Purpose.CONVERSATION).provider, "SomePaid")

    def test_the_primary_is_used_even_when_it_is_paid(self):
        # Choosing a paid provider on purpose is not a silent fallback.
        value = self.build()
        value.set_route(Purpose.CONVERSATION, "SomePaid", "m")
        self.assertEqual(value.choose(Purpose.CONVERSATION).provider, "SomePaid")

    def test_the_ladder_ends_on_the_permitted_local_model(self):
        # Automatic local failover needs the same consent as every other kind.
        value = self.build()
        value.allow_local_fallback = True
        value.set_route(Purpose.CONVERSATION, "Groq", "m")
        value.fallbacks = [Fallback(Route("Ollama"))]
        value.ledger.configure("groq", requests_per_day=1)
        value.record_use(Route("Groq", "m"))
        self.assertEqual(value.choose(Purpose.CONVERSATION).provider, "Ollama")

    def test_a_local_fallback_is_not_taken_silently(self):
        value = self.build()
        value.set_route(Purpose.CONVERSATION, "Groq", "m")
        value.fallbacks = [Fallback(Route("Ollama"))]
        value.ledger.configure("groq", requests_per_day=1)
        value.record_use(Route("Groq", "m"))
        with self.assertRaises(Refusal):
            value.choose(Purpose.CONVERSATION)

    def test_no_route_at_all_is_refused_with_a_reason(self):
        with self.assertRaises(Refusal) as caught:
            self.build().choose(Purpose.CONVERSATION)
        self.assertIn("no provider", str(caught.exception).lower())

    def test_a_429_blocks_the_group_not_the_key(self):
        value = self.build()
        value.set_route(Purpose.CONVERSATION, "Groq", "m")
        value.fallbacks = [Fallback(Route("Google AI Studio", "g"))]
        value.record_limit(Route("Groq", "m"), 60)
        self.assertEqual(value.choose(Purpose.CONVERSATION).provider, "Google AI Studio")

    def test_describe_mentions_each_purpose(self):
        value = self.build()
        value.set_route(Purpose.CONVERSATION, "Groq", "m")
        text = routing.describe(value)
        self.assertIn("conversation", text)
        self.assertIn("critic", text)


class SwitchParsingTests(unittest.TestCase):
    def providers(self):
        return [Provider("Google AI Studio"), Provider("Groq"), Provider("Ollama", local=True)]

    def test_a_plain_provider_switch(self):
        request = routing.parse_switch("use Groq", self.providers())
        self.assertIsNotNone(request)
        self.assertEqual(request.provider, "Groq")
        self.assertIsNone(request.purpose)

    def test_switching_one_purpose_only(self):
        request = routing.parse_switch("switch the critic to Groq", self.providers())
        self.assertIsNotNone(request)
        self.assertEqual(request.purpose, Purpose.CRITIC)

    def test_switching_with_a_model_name(self):
        request = routing.parse_switch(
            "use Groq with qwen3.8-27b", self.providers(), ["qwen3.8-27b"])
        self.assertIsNotNone(request)
        self.assertEqual(request.provider, "Groq")
        self.assertEqual(request.model, "qwen3.8-27b")

    def test_going_local(self):
        request = routing.parse_switch("go local for now", self.providers())
        self.assertIsNotNone(request)
        self.assertTrue(request.local_only)

    def test_multi_word_provider_names(self):
        request = routing.parse_switch("switch to google ai studio", self.providers())
        self.assertIsNotNone(request)
        self.assertEqual(request.provider, "Google AI Studio")

    def test_an_unconfigured_provider_is_not_a_switch(self):
        self.assertIsNone(routing.parse_switch("use OpenAI", self.providers()))

    def test_ordinary_sentences_are_not_switches(self):
        for sentence in ("what model are you using?", "tell me about Groq latencies",
                         "the critic should be careful"):
            self.assertIsNone(routing.parse_switch(sentence, self.providers()), sentence)

    def test_empty_input(self):
        self.assertIsNone(routing.parse_switch("", self.providers()))


class SwitchApplyingTests(unittest.TestCase):
    def build(self):
        value = table()
        value.add_provider(Provider("Google AI Studio"))
        value.add_provider(Provider("Groq"))
        value.add_provider(Provider("Ollama", local=True))
        value.set_route(Purpose.CONVERSATION, "Google AI Studio", "gemma-4-31b")
        return value

    def test_a_switch_changes_the_route(self):
        value = self.build()
        applied = routing.apply_switch(
            value, routing.SwitchRequest(provider="Groq", model="qwen"), purposes=[Purpose.CONVERSATION])
        self.assertEqual(applied[0][1].provider, "Groq")
        self.assertEqual(value.route_for(Purpose.CONVERSATION).model, "qwen")

    def test_a_purpose_specific_switch_leaves_the_others_alone(self):
        value = self.build()
        routing.apply_switch(
            value, routing.SwitchRequest(provider="Groq", purpose=Purpose.CRITIC))
        self.assertEqual(value.route_for(Purpose.CONVERSATION).provider, "Google AI Studio")
        self.assertEqual(value.route_for(Purpose.CRITIC).provider, "Groq")

    def test_local_only_needs_a_local_provider(self):
        value = table()
        value.add_provider(Provider("Groq"))
        with self.assertRaises(Refusal):
            routing.apply_switch(value, routing.SwitchRequest(local_only=True))

    def test_local_only_switches(self):
        value = self.build()
        routing.apply_switch(value, routing.SwitchRequest(local_only=True),
                             purposes=[Purpose.CONVERSATION])
        self.assertEqual(value.route_for(Purpose.CONVERSATION).provider, "Ollama")

    def test_a_model_only_switch_keeps_the_provider(self):
        value = self.build()
        routing.apply_switch(value, routing.SwitchRequest(model="gemma-4-26b"),
                             purposes=[Purpose.CONVERSATION])
        route = value.route_for(Purpose.CONVERSATION)
        self.assertEqual(route.provider, "Google AI Studio")
        self.assertEqual(route.model, "gemma-4-26b")

    def test_switching_to_an_unknown_provider_is_refused(self):
        with self.assertRaises(Refusal):
            routing.apply_switch(self.build(), routing.SwitchRequest(provider="Nope"))

    def test_default_target_is_the_conversation(self):
        value = self.build()
        applied = routing.apply_switch(value, routing.SwitchRequest(provider="Groq"))
        self.assertEqual(applied[0][0], Purpose.CONVERSATION)


if __name__ == "__main__":
    unittest.main()
