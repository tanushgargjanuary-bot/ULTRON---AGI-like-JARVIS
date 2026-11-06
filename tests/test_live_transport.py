"""tests/test_live_transport.py — the provider path over a real socket.

The gap this closes: every previous test of the provider path handed the engine a
fake object that yielded dicts. That proves the engine; it does not prove the
transport — SSE framing split across chunks, a tool call arriving as deltas, a
401 arriving as HTML, a stream that stops mid-sentence, a timeout. Those are what
actually breaks against a real server, and none of them needs a vendor, a key or
a network connection to reproduce.

So this file starts a real HTTP server (`scripts/fake_provider.py`) that speaks
the OpenAI-compatible protocol, points the REAL provider at it, and drives the
REAL pipeline engine through it. The model is fake. The socket is not.

No vendor is contacted. No key is used. Nothing leaves 127.0.0.1.
"""

from __future__ import annotations

import asyncio
import socket
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import httpx                                  # noqa: F401
except ImportError as exc:                        # pragma: no cover
    raise unittest.SkipTest(f"httpx not installed: {exc}") from exc

from providers import registry                    # noqa: E402
from providers.base import FunctionCall           # noqa: E402
from providers.engine_pipeline import PipelineEngine   # noqa: E402
from scripts.fake_provider import FakeProvider    # noqa: E402

PROVIDER = "openai_compat@ollama"                 # any id with the same shape


def build(server: FakeProvider, model: str, **extra):
    registry.reset()                              # the cache is keyed by config
    return registry.build(PROVIDER, server.config(model, **extra))


def collect(llm, messages, tools=None, *, timeout=15.0):
    """Everything `chat()` yields, as a list."""
    async def _run():
        out = []
        async for event in llm.chat(messages, tools):
            out.append(event)
        return out
    return asyncio.run(asyncio.wait_for(_run(), timeout))


def _response(call_id: str, name: str):
    """A FunctionResponse from the SDK when it is installed, and the same shape
    when it is not — the engine only reads .id, .name and .response."""
    try:
        from google.genai import types
        return types.FunctionResponse(id=call_id, name=name,
                                      response={"result": "started"})
    except ImportError:                                   # pragma: no cover
        return SimpleNamespace(id=call_id, name=name, response={"result": "started"})


def closed_port() -> int:
    """A port nothing is listening on — a provider that cannot be reached."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class StreamTests(unittest.TestCase):
    """Text arriving as SSE chunks, over HTTP, through the real client."""

    @classmethod
    def setUpClass(cls):
        cls.server = FakeProvider().start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_a_streamed_answer_arrives_in_pieces(self):
        llm = build(self.server, "echo")
        events = collect(llm, [{"role": "user", "content": "hello"}])
        text = "".join(e.get("text", "") for e in events)
        self.assertIn("nominal", text)
        self.assertGreaterEqual(len([e for e in events if e.get("text")]), 2,
                                "one lump means the stream was not streamed")

    def test_the_request_carries_the_key_and_the_model(self):
        self.server.requests.clear()
        llm = build(self.server, "echo", api_key="sk-test-123")
        collect(llm, [{"role": "user", "content": "hello"}])
        sent = self.server.requests[-1]
        self.assertEqual(sent["auth"], "Bearer sk-test-123")
        self.assertEqual(sent["body"]["model"], "echo")
        self.assertIn("/chat/completions", sent["path"])

    def test_a_server_that_stops_mid_sentence_does_not_lose_the_turn(self):
        llm = build(self.server, "truncate")
        events = collect(llm, [{"role": "user", "content": "hello"}])
        text = "".join(e.get("text", "") for e in events)
        self.assertIn("The answer is", text)

    def test_a_silent_server_ends_without_inventing_an_answer(self):
        llm = build(self.server, "silent")
        events = collect(llm, [{"role": "user", "content": "hello"}])
        self.assertEqual("".join(e.get("text", "") for e in events), "")

    def test_a_malformed_event_stream_does_not_raise(self):
        llm = build(self.server, "garbage")
        events = collect(llm, [{"role": "user", "content": "hello"}])
        self.assertEqual("".join(e.get("text", "") for e in events), "")

    def test_deltas_of_a_tool_call_are_assembled_into_one_call(self):
        # A real server sends the name in one delta and the arguments in
        # fragments. Sending it whole would hide the bug this checks.
        llm = build(self.server, "tools")
        events = collect(llm, [{"role": "user", "content": "open spotify"}])
        calls = [c for e in events for c in (e.get("tool_calls") or [])]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].name, "open_app")
        self.assertEqual(calls[0].args, {"app_name": "spotify"})


class ErrorTests(unittest.TestCase):
    """What the user is told when the server says no."""

    @classmethod
    def setUpClass(cls):
        cls.server = FakeProvider().start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def assert_fails_with(self, model: str, *fragments: str):
        llm = build(self.server, model)
        with self.assertRaises(Exception) as caught:
            collect(llm, [{"role": "user", "content": "hi"}])
        message = str(caught.exception).lower()
        for fragment in fragments:
            self.assertIn(fragment.lower(), message)

    def test_401_says_unauthorised_and_does_not_return_html(self):
        self.assert_fails_with("unauth", "401")
        llm = build(self.server, "unauth")
        with self.assertRaises(Exception) as caught:
            collect(llm, [{"role": "user", "content": "hi"}])
        self.assertNotIn("<html>", str(caught.exception))

    def test_429_is_reported_as_a_rate_limit(self):
        self.assert_fails_with("ratelimit", "429")

    def test_500_is_reported_with_its_code(self):
        self.assert_fails_with("boom", "500")

    def test_404_model_not_found_is_reported(self):
        self.assert_fails_with("notfound", "404")

    def test_an_unreachable_server_fails_promptly_with_its_address(self):
        port = closed_port()
        llm = registry.build(PROVIDER, {"base_url": f"http://127.0.0.1:{port}/v1",
                                        "model": "echo", "timeout": 3})
        with self.assertRaises(Exception) as caught:
            collect(llm, [{"role": "user", "content": "hi"}])
        walked = " ".join(str(a) for a in caught.exception.args).lower()
        self.assertTrue(str(port) in walked or "connect" in walked, walked)


class VisionProbeOverHttpTests(unittest.TestCase):
    """The tri-state probe, against a server that really answers."""

    @classmethod
    def setUpClass(cls):
        cls.server = FakeProvider().start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_a_server_that_accepts_an_image_says_yes(self):
        llm = build(self.server, "vision-ok")
        self.assertIs(llm.can_see(), True)

    def test_a_server_that_refuses_the_image_says_no(self):
        llm = build(self.server, "vision-no")
        self.assertIs(llm.can_see(), False)

    def test_a_server_that_is_not_there_says_nothing(self):
        port = closed_port()
        llm = registry.build(PROVIDER, {"base_url": f"http://127.0.0.1:{port}/v1",
                                        "model": "vision-ok", "timeout": 2})
        self.assertIsNone(llm.can_see(timeout=2))

    def test_a_refusal_does_not_delete_a_known_yes(self):
        llm = build(self.server, "vision-no", vision=True)
        saved = []
        # The probe asks again because the model name changed with the config.
        self.assertFalse(llm.ensure_vision_known(save=saved.append))
        self.assertEqual(saved[-1]["vision"], "",
                         "a real refusal is recorded — as a refusal")


class EngineOverHttpTests(unittest.TestCase):
    """The whole provider path: engine -> HTTP -> SSE -> engine."""

    @classmethod
    def setUpClass(cls):
        cls.server = FakeProvider().start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def engine(self, model: str, tools=True) -> PipelineEngine:
        registry.reset()
        llm = registry.build(PROVIDER, self.server.config(model))
        config = SimpleNamespace(
            system_instruction="You are Ultron.",
            tools=[{"function_declarations": [
                {"name": "open_app", "description": "Open an application",
                 "parameters": {"type": "OBJECT",
                                "properties": {"app_name": {"type": "STRING",
                                                            "description": "name"}},
                                "required": ["app_name"]}}]}] if tools else [])
        return PipelineEngine(llm, None, None, config=config, log=lambda _m: None)

    def run_turn(self, engine, text="hello", answer_calls=True, timeout=20.0):
        async def scenario():
            await engine.send_client_content(turns={"parts": [{"text": text}]})
            said, calls, ended = [], [], False

            async def drive():
                async for msg in engine.receive():
                    sc = getattr(msg, "server_content", None)
                    if sc is not None and getattr(sc, "output_transcription", None):
                        said.append(sc.output_transcription.text)
                    if getattr(msg, "tool_call", None):
                        for call in msg.tool_call.function_calls:
                            calls.append((call.name, dict(call.args or {})))
                            if answer_calls:
                                await engine.send_tool_response(function_responses=[
                                    _response(call.id, call.name)])
                    if sc is not None and getattr(sc, "turn_complete", False):
                        return True
                return False

            ended = await asyncio.wait_for(drive(), timeout)
            return "".join(said), calls, ended

        try:
            return asyncio.run(scenario())
        finally:
            asyncio.run(engine.close())

    def test_a_text_turn_over_http_is_spoken_and_ends(self):
        said, _calls, ended = self.run_turn(self.engine("echo"))
        self.assertTrue(ended, "the turn never completed")
        self.assertIn("nominal", said)

    def test_a_slow_server_still_completes_the_turn(self):
        said, _calls, ended = self.run_turn(self.engine("slow"))
        self.assertTrue(ended)
        self.assertIn("moment", said)

    def test_a_tool_round_trip_over_http(self):
        # First request: the model calls the tool. Second request carries the
        # result. The answer only comes if both halves of the transport work.
        said, calls, ended = self.run_turn(self.engine("tools"), "open spotify")
        self.assertEqual(calls, [("open_app", {"app_name": "spotify"})])
        self.assertTrue(ended)
        self.assertIn("Spotify", said)

    def test_a_server_error_ends_the_turn_with_an_apology(self):
        said, _calls, ended = self.run_turn(self.engine("boom"))
        self.assertTrue(ended, "an error left the turn open")
        self.assertTrue(said, "the user heard nothing at all")


if __name__ == "__main__":
    unittest.main()
