"""tests/test_live_config.py — can a session actually be configured, and does the
provider path really run?

Two things here that nothing else in the suite covers.

1. THE CONFIG. main.py builds a LiveConnectConfig out of 25 tool declarations at
   connect time. If any one of them is malformed the SDK raises, no session opens,
   and the app retries for ever — a failure that happens on the user's machine and
   nowhere else. `google-genai` is a declared dependency, and where it is
   installed these tests build the real objects and prove they validate.

2. THE PROVIDER PATH. The multi-provider engine is the least-exercised code in
   the tree and the one the owner actually asked for. It is driven here end to
   end against a fake model that speaks the documented protocol: a text turn, a
   tool round trip, a provider that raises mid-stream, and a provider that says
   nothing at all. No network, no key, no audio device.
"""

from __future__ import annotations

import ast
import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.action_loader import discover_actions, strip_meta      # noqa: E402
from providers import schema                                     # noqa: E402
from providers.base import FunctionCall                          # noqa: E402
from providers.engine_pipeline import PipelineEngine              # noqa: E402

# Only local tool-budget hints are private bookkeeping. Live API behavior is
# an intentional Gemini-only declaration feature and is preserved by strip_meta.
META_KEYS = {"tier", "brief"}


def _response(call_id: str, name: str):
    try:
        from google.genai import types
        return types.FunctionResponse(id=call_id, name=name, response={"result": "ok"})
    except ImportError:                                   # pragma: no cover
        return SimpleNamespace(id=call_id, name=name, response={"result": "ok"})


def all_declarations() -> tuple[list[dict], list[dict]]:
    """(inline, action). Both as main.py assembles them."""
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    inline: list[dict] = []
    for node in ast.parse(source).body:
        if (isinstance(node, ast.Assign)
                and any(getattr(t, "id", "") == "TOOL_DECLARATIONS" for t in node.targets)):
            inline = ast.literal_eval(node.value)
    registry = discover_actions(ROOT / "actions", logger=lambda _m: None)
    return inline, registry.get_tool_declarations()


class DeclarationTests(unittest.TestCase):
    def test_no_private_bookkeeping_reaches_the_vendor(self):
        # A key the vendor does not know is an error, not something ignored.
        inline, actions = all_declarations()
        outgoing = strip_meta(inline + actions)
        for decl in outgoing:
            leaked = META_KEYS & set(decl)
            self.assertFalse(leaked, f"{decl.get('name')} would send {leaked}")

    def test_every_tool_has_a_description_and_an_object_schema(self):
        inline, actions = all_declarations()
        for decl in inline + actions:
            self.assertTrue(str(decl.get("description", "")).strip(), decl.get("name"))
            self.assertEqual(decl["parameters"]["type"], "OBJECT", decl.get("name"))


class RealSdkConfigTests(unittest.TestCase):
    """Needs google-genai. Skipped rather than faked when it is absent."""

    @classmethod
    def setUpClass(cls):
        try:
            from google.genai import types
        except ImportError as exc:
            raise unittest.SkipTest(f"google-genai not installed: {exc}") from exc
        cls.types = types

    def test_all_twenty_five_declarations_validate(self):
        inline, actions = all_declarations()
        outgoing = strip_meta(inline + actions)
        tool = self.types.Tool(function_declarations=outgoing)
        self.assertEqual(len(tool.function_declarations), len(outgoing))
        self.assertGreaterEqual(len(outgoing), 25)

    def test_a_full_live_config_builds(self):
        types = self.types
        inline, actions = all_declarations()
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction="You are Ultron.",
            tools=[types.Tool(function_declarations=strip_meta(inline + actions))],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede"))),
        )
        self.assertIsNotNone(config)

    def test_every_parameter_type_is_one_the_server_accepts(self):
        # The SDK does not validate the schema locally — it coerces — so a typo
        # here is rejected by the server at connect time, on the user's machine.
        # This is the local stand-in for that check.
        allowed = {"STRING", "NUMBER", "INTEGER", "BOOLEAN", "ARRAY", "OBJECT"}
        inline, actions = all_declarations()

        def walk(spec, path):
            kind = spec.get("type")
            if kind is not None:
                self.assertIn(kind, allowed, f"{path}: type {kind!r}")
            for key, sub in (spec.get("properties") or {}).items():
                walk(sub, f"{path}.{key}")
            if isinstance(spec.get("items"), dict):
                walk(spec["items"], f"{path}[]")

        for decl in strip_meta(inline + actions):
            walk(decl["parameters"], decl["name"])

    def test_every_declared_parameter_has_a_description(self):
        # The model reads these to decide what to pass; an undescribed parameter
        # is one it fills with a guess.
        inline, actions = all_declarations()
        missing = []
        for decl in strip_meta(inline + actions):
            for key, spec in (decl["parameters"].get("properties") or {}).items():
                if not str(spec.get("description", "")).strip():
                    missing.append(f"{decl['name']}.{key}")
        self.assertEqual(missing, [], "undescribed parameters")


class PipelineSchemaTests(unittest.TestCase):
    def test_an_openai_style_model_gets_openai_style_tools(self):
        inline, actions = all_declarations()
        decls = schema.budget(strip_meta(inline + actions))
        converted = schema.convert(decls, "openai")
        self.assertEqual(len(converted), len(decls))
        first = converted[0]
        self.assertEqual(first["type"], "function")
        self.assertIn("name", first["function"])
        self.assertIn("parameters", first["function"])

    def test_the_budget_keeps_tools_and_says_how_many_it_kept(self):
        inline, actions = all_declarations()
        decls = strip_meta(inline + actions)
        kept = schema.budget(decls, max_tools=5)
        self.assertLessEqual(len(kept), 5)
        self.assertGreater(len(kept), 0)


class FakeLLM:
    """Speaks providers.base.LLM. Yields dicts; can raise on cue."""

    caps = {"tools": True, "tool_format": "openai", "vision": False,
            "max_tools": 40, "max_tool_chars": 60000}

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict] = []

    async def chat(self, messages, tools=None, *, stream=True):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools})
        step = self.script.pop(0) if self.script else [{"text": "done"}]
        for item in step:
            if isinstance(item, Exception):
                raise item
            yield item


CONFIG = SimpleNamespace(
    system_instruction="You are Ultron.",
    tools=[{"function_declarations": [
        {"name": "open_app", "description": "Open an application",
         "parameters": {"type": "OBJECT",
                        "properties": {"app_name": {"type": "STRING",
                                                    "description": "name"}},
                        "required": ["app_name"]}},
        {"name": "get_time", "description": "The time now",
         "parameters": {"type": "OBJECT", "properties": {}}},
    ]}],
)


def run_turn(engine, *, timeout=5.0):
    """Drive one turn to its end and return every event, or None on a hang."""
    async def _run():
        events = []
        async for msg in engine.receive():
            events.append(msg)
            if msg.server_content and msg.server_content.turn_complete:
                return events
        return events

    async def _go():
        return await asyncio.wait_for(_run(), timeout)
    return _go


class PipelineEngineTests(unittest.TestCase):
    def turn(self, script, timeout=5.0):
        engine = PipelineEngine(FakeLLM(script), None, None, config=CONFIG,
                                log=lambda _m: None)
        try:
            events = asyncio.run(self._collect(engine, timeout))
        finally:
            asyncio.run(engine.close())
        return events

    async def _collect(self, engine, timeout):
        await engine.send_client_content(turns={"parts": [{"text": "hello"}]})
        events = []

        async def _run():
            async for msg in engine.receive():
                events.append(msg)
                if msg.server_content and msg.server_content.turn_complete:
                    return
        await asyncio.wait_for(_run(), timeout)
        return events

    def test_a_text_turn_is_spoken_and_ends(self):
        events = self.turn([[{"text": "Hello, sir."}]])
        said = "".join(e.server_content.output_transcription.text for e in events
                       if e.server_content and e.server_content.output_transcription)
        self.assertIn("Hello", said)
        self.assertTrue(events[-1].server_content.turn_complete)

    def test_the_tools_reach_the_model(self):
        llm = FakeLLM([[{"text": "ok"}]])
        engine = PipelineEngine(llm, None, None, config=CONFIG, log=lambda _m: None)
        self.assertEqual(sorted(engine.tool_names()), ["get_time", "open_app"])
        asyncio.run(self._collect(engine, 5.0))
        offered = llm.calls[0]["tools"]
        self.assertIsNotNone(offered, "the model was given no tools at all")
        self.assertEqual(len(offered), 2)
        asyncio.run(engine.close())

    def test_a_tool_call_comes_back_with_its_arguments(self):
        # A turn with a tool call deliberately does NOT complete: the engine
        # waits for the result. So this reads until the call arrives.
        engine = PipelineEngine(
            FakeLLM([[{"tool_calls": [FunctionCall(id="c1", name="open_app",
                                                   args={"app_name": "spotify"})]}]]),
            None, None, config=CONFIG, log=lambda _m: None)

        async def scenario():
            await engine.send_client_content(turns={"parts": [{"text": "open spotify"}]})
            events = []
            async def _run():
                async for msg in engine.receive():
                    events.append(msg)
                    if msg.tool_call:
                        return
            await asyncio.wait_for(_run(), 5.0)
            return events

        try:
            events = asyncio.run(scenario())
        finally:
            asyncio.run(engine.close())
        calls = [(c.id, c.name, c.args) for e in events if e.tool_call
                 for c in e.tool_call.function_calls]
        self.assertEqual(calls, [("c1", "open_app", {"app_name": "spotify"})])

    def test_a_tool_result_starts_the_second_round_trip(self):
        llm = FakeLLM([
            [{"tool_calls": [FunctionCall(id="c1", name="open_app",
                                          args={"app_name": "spotify"})]}],
            [{"text": "Spotify is opening."}],
        ])
        engine = PipelineEngine(llm, None, None, config=CONFIG, log=lambda _m: None)

        async def scenario():
            await engine.send_client_content(turns={"parts": [{"text": "open spotify"}]})
            events = []
            async for msg in engine.receive():
                events.append(msg)
                if msg.tool_call:
                    break
            try:
                from google.genai import types
                response = types.FunctionResponse(id="c1", name="open_app",
                                                  response={"result": "started"})
            except ImportError:                       # pragma: no cover
                response = SimpleNamespace(id="c1", name="open_app",
                                           response={"result": "started"})
            await engine.send_tool_response(function_responses=[response])
            second = []
            async def _rest():
                async for msg in engine.receive():
                    second.append(msg)
                    if msg.server_content and msg.server_content.turn_complete:
                        return
            await asyncio.wait_for(_rest(), 5.0)
            return second

        second = asyncio.run(scenario())
        asyncio.run(engine.close())
        text = "".join(e.server_content.output_transcription.text for e in second
                       if e.server_content and e.server_content.output_transcription)
        self.assertIn("Spotify", text)
        # the tool result must be in the history the model was shown
        last = [m for m in llm.calls[-1]["messages"] if isinstance(m, dict)]
        self.assertTrue(any(m.get("role") == "tool" for m in last), last)

    def test_a_provider_that_raises_does_not_hang_the_turn(self):
        events = self.turn([[RuntimeError("provider exploded")]], timeout=5.0)
        self.assertTrue(events, "nothing was emitted, so the UI would sit silent")
        self.assertIn("turn_complete", str(events[-1].server_content))

    def test_a_provider_that_says_nothing_still_ends_the_turn(self):
        events = self.turn([[]], timeout=5.0)
        self.assertTrue(events[-1].server_content.turn_complete)

    # ── a turn that cannot be left open ───────────────────────────────────────
    #
    # The engine waits for every call it made before asking the model again, which
    # is right for a parallel batch. Measured before the fix: two calls, one
    # answered — the turn stayed open for ever, the UI sat in THINKING, and only
    # the stall watchdog rescued it. A call that is never answered at all (consent
    # refused, tool raised before it could report) was the same, worse.

    def _two_calls_then_text(self):
        return FakeLLM([
            [{"tool_calls": [FunctionCall(id="c1", name="open_app",
                                          args={"app_name": "a"}),
                             FunctionCall(id="c2", name="open_app",
                                          args={"app_name": "b"})]}],
            [{"text": "done"}],
        ])

    def test_one_result_is_enough_to_finish_the_turn(self):
        llm = self._two_calls_then_text()
        engine = PipelineEngine(llm, None, None, config=CONFIG, log=lambda _m: None)

        async def scenario():
            await engine.send_client_content(turns={"parts": [{"text": "go"}]})
            async def _run():
                async for msg in engine.receive():
                    if msg.tool_call:
                        await engine.send_tool_response(function_responses=[
                            _response("c1", "open_app")])
                    if msg.server_content and msg.server_content.turn_complete:
                        return True
                return False
            return await asyncio.wait_for(_run(), 6.0)

        try:
            self.assertTrue(asyncio.run(scenario()))
        finally:
            asyncio.run(engine.close())

    def test_a_call_nobody_answers_still_finishes_the_turn(self):
        llm = self._two_calls_then_text()
        logs = []
        engine = PipelineEngine(llm, None, None, config=CONFIG, log=logs.append)

        async def scenario():
            await engine.send_client_content(turns={"parts": [{"text": "go"}]})
            async def _run():
                async for msg in engine.receive():
                    if msg.server_content and msg.server_content.turn_complete:
                        return True
                return False
            return await asyncio.wait_for(_run(), 6.0)

        try:
            self.assertTrue(asyncio.run(scenario()))
        finally:
            asyncio.run(engine.close())
        self.assertTrue(any("no result from" in line.lower() for line in logs), logs)

    def test_the_unanswered_call_is_still_in_the_transcript(self):
        # An assistant turn announcing two calls and answering one is a history
        # the vendor's API rejects on the next request — worse than the delay.
        llm = self._two_calls_then_text()
        engine = PipelineEngine(llm, None, None, config=CONFIG, log=lambda _m: None)

        async def scenario():
            await engine.send_client_content(turns={"parts": [{"text": "go"}]})
            async def _run():
                async for msg in engine.receive():
                    if msg.server_content and msg.server_content.turn_complete:
                        return
            await asyncio.wait_for(_run(), 6.0)

        try:
            asyncio.run(scenario())
        finally:
            asyncio.run(engine.close())
        history = [m for m in llm.calls[-1]["messages"] if isinstance(m, dict)]
        answered = {m.get("tool_call_id") for m in history if m.get("role") == "tool"}
        self.assertEqual(answered, {"c1", "c2"}, history)
if __name__ == "__main__":
    unittest.main()
