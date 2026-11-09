"""Tests for provider routing at run time."""

import asyncio
import unittest

from core.routing import Provider, Purpose, Route, RoutingTable
from core.routing_runtime import RoutedLLM, configured_slot_id
from providers.engine_pipeline import PipelineEngine


class FakeLLM:
    def __init__(self, model, *, tools=True, vision=False, max_tools=12):
        self.model = model
        self.base = "https://example.invalid/v1"
        self.caps = {"tools": tools, "tool_format": "openai", "vision": vision,
                     "max_tools": max_tools, "max_tool_chars": 8000}

    async def chat(self, messages, tools=None, **kwargs):
        yield {"text": f"from {self.model}"}


class _FakeSTT:
    async def transcribe(self, _pcm, _sample_rate):
        return "use Ollama"


class RoutingRuntimeTests(unittest.TestCase):
    def test_purposes_map_to_real_engine_slots(self):
        settings = {
            "pipeline": {"llm": "provider@chat"},
            "coding": "provider@coder",
            "sidecar": "provider@review",
        }
        self.assertEqual(configured_slot_id(Purpose.CONVERSATION, settings), "provider@chat")
        self.assertEqual(configured_slot_id(Purpose.EVOLUTION, settings), "provider@coder")
        self.assertEqual(configured_slot_id(Purpose.CRITIC, settings), "provider@review")

    def build(self):
        table = RoutingTable()
        table.add_provider(Provider("Groq", quota_group="groq", paid=True))
        table.add_provider(Provider("Ollama", local=True))
        table.add_provider(Provider("Google AI Studio", quota_group="google", paid=True))
        table.set_route(Purpose.CONVERSATION, "Groq", "llama-70b")
        table.set_route(Purpose.EVOLUTION, "Ollama", "qwen-coder")
        table.set_route(Purpose.CRITIC, "Google AI Studio", "gemma")
        logs, persisted = [], []
        runtime = RoutedLLM(
            table,
            {"groq": FakeLLM("llama-70b"), "ollama": FakeLLM("qwen-coder"),
             "google ai studio": FakeLLM("gemma")},
            {"groq": "openai_compat@groq", "ollama": "openai_compat@ollama",
             "google ai studio": "openai_compat@google"},
            log=logs.append, persist=persisted.append,
        )
        return runtime, logs, persisted

    def test_three_request_purposes_select_the_configured_provider(self):
        runtime, logs, _ = self.build()
        selected = [runtime.select(p)[0].describe() for p in Purpose]
        self.assertEqual(selected, ["Groq/llama-70b", "Ollama/qwen-coder", "Google AI Studio/gemma"])
        self.assertEqual(len(logs), 3)
        self.assertIn("purpose=critic", logs[-1])

    def test_voice_switch_updates_live_route_and_persists_provider_id(self):
        runtime, logs, persisted = self.build()
        response = runtime.handle_switch("use Ollama")
        self.assertIn("Ollama", response)
        self.assertEqual(runtime.table.route_for(Purpose.CONVERSATION), Route("Ollama", "qwen-coder"))
        self.assertEqual(persisted, ["openai_compat@ollama"])
        self.assertIn("switched purpose=conversation", logs[-1])

    def test_non_conversation_switch_is_not_intercepted(self):
        runtime, _logs, persisted = self.build()
        self.assertIsNone(runtime.handle_switch("switch the critic to Ollama"))
        self.assertEqual(runtime.table.route_for(Purpose.CONVERSATION).provider, "Groq")
        self.assertEqual(persisted, [])

    def test_unknown_provider_does_not_change_route(self):
        runtime, _logs, _ = self.build()
        self.assertIsNone(runtime.handle_switch("use UnknownCloud"))
        self.assertEqual(runtime.table.route_for(Purpose.CONVERSATION).provider, "Groq")

    def test_chat_delegates_to_current_conversation_route(self):
        runtime, _logs, _ = self.build()

        async def collect():
            return [event async for event in runtime.chat([{"role": "user", "content": "hi"}])]

        self.assertEqual(asyncio.run(collect()), [{"text": "from llama-70b"}])
        self.assertEqual(runtime.table.ledger.snapshot()["groq"]["used_requests"], 1)

    def test_pipeline_intercepts_voice_route_switch_without_dropping_history(self):
        runtime, _logs, persisted = self.build()
        engine = PipelineEngine(runtime, stt=_FakeSTT())
        engine._history = [
            {"role": "user", "content": "keep this prior question"},
            {"role": "assistant", "content": "and its answer"},
        ]
        engine._mic = [bytes([0, 0])]
        engine._mic_bytes = 2

        async def run_turn():
            await engine.flush_microphone()
            return [await engine._queue.get(), await engine._queue.get()]

        events = asyncio.run(run_turn())
        self.assertEqual(events[0].server_content.input_transcription.text, "use Ollama")
        self.assertEqual(events[1].server_content.output_transcription.text,
                         "Conversation model switched to Ollama/qwen-coder.")
        self.assertEqual(engine._history, [
            {"role": "user", "content": "keep this prior question"},
            {"role": "assistant", "content": "and its answer"},
            {"role": "user", "content": "use Ollama"},
            {"role": "assistant", "content": "Conversation model switched to Ollama/qwen-coder."},
        ])
        self.assertEqual(persisted, ["openai_compat@ollama"])
        self.assertEqual(runtime.table.ledger.snapshot(), {})

    def test_shared_capabilities_are_safe_across_selected_models(self):
        runtime, _logs, _ = self.build()
        self.assertEqual(runtime.caps["max_tools"], 12)
        self.assertFalse(runtime.caps["vision"])


if __name__ == "__main__":
    unittest.main()
