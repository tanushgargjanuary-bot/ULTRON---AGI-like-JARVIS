"""The rung after the last cloud model: Ollama on this machine.

A real HTTP server is started in a thread for these tests, because the shape of an
Ollama answer is the thing most likely to change and the thing a mock cannot tell us.
"""

import asyncio
import json
import threading
import tempfile
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from custom_jarvis import local_fallback


class _Fake(BaseHTTPRequestHandler):
    models: list = []
    calls: list = []

    def do_GET(self):                                    # noqa: N802 — stdlib name
        """Serve the fake Ollama model-list response for the test server."""
        if self.path == "/api/tags":
            body = json.dumps({"models": [{"name": name} for name in self.models]}).encode()
            self._answer(200, body)
        else:
            self._answer(404, b"")

    def do_POST(self):                                   # noqa: N802 — stdlib name
        """Record and answer fake Ollama generation requests."""
        size = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(size) or b"{}")
        _Fake.calls.append((self.path, payload))
        if self.path == "/api/show":
            name = str(payload.get("model") or "")
            quant = "Q4_K_M" if "-q4_K_M" in name else "F16"
            self._answer(200, json.dumps({
                "details": {"quantization_level": quant}
            }).encode())
        else:
            self._answer(200, b'{"done": true}')

    def _answer(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


class _Server(unittest.TestCase):
    models: list = []

    def setUp(self):
        _Fake.models = list(self.models)
        _Fake.calls = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()


class TheQuestion(_Server):
    models = ["lfm2:2b-q4_K_M", "qwen3:2b-q4_K_M", "llama3:70b"]

    def test_installed_models_are_read(self):
        self.assertEqual(sorted(local_fallback.installed(self.url)),
                         ["lfm2:2b-q4_K_M", "llama3:70b", "qwen3:2b-q4_K_M"])

    def test_a_server_that_answers_is_running(self):
        self.assertTrue(local_fallback.running(self.url))

    def test_a_port_nobody_listens_on_is_not_running(self):
        self.assertFalse(local_fallback.running("http://127.0.0.1:1"))

    def test_malformed_tag_rows_are_skipped(self):
        with mock.patch.object(local_fallback, "_get", return_value={
                "models": [None, "bad row", {"name": "qwen3:4b"}]}):
            self.assertEqual(local_fallback.installed(self.url), ["qwen3:4b"])


class WhichModel(unittest.TestCase):
    def test_qwen_wins_over_lfm(self):
        self.assertEqual(
            local_fallback.pick(["lfm2:2b-q4_K_M", "qwen3:2b-q4_K_M"]),
            "qwen3:2b-q4_K_M",
        )

    def test_a_seventy_billion_model_is_not_chosen_on_a_laptop(self):
        self.assertEqual(
            local_fallback.pick(["llama3:70b", "lfm2:2b-q4_K_M"]), "lfm2:2b-q4_K_M"
        )
        self.assertIsNone(local_fallback.pick(["llama3:70b"]))

    def test_two_billion_model_is_preferred_over_seventy(self):
        self.assertEqual(
            local_fallback.pick(["llama3:70b", "qwen3:2b-q4_K_M"]),
            "qwen3:2b-q4_K_M",
        )

    def test_four_billion_model_is_outside_the_approved_window(self):
        self.assertIsNone(local_fallback.pick(["qwen3:4b"]))

    def test_the_only_model_is_the_answer(self):
        self.assertIsNone(local_fallback.pick(["mistral:7b"]))

    def test_nothing_installed_has_no_answer(self):
        self.assertIsNone(local_fallback.pick([]))

    def test_embedding_models_are_never_chosen_for_chat(self):
        self.assertEqual(
            local_fallback.pick(["nomic-embed-text", "qwen3:2b-q4_K_M"]),
            "qwen3:2b-q4_K_M",
        )
        self.assertIsNone(local_fallback.pick(["nomic-embed-text", "bge-m3"]))

    def test_a_size_is_read_from_the_name(self):
        self.assertEqual(local_fallback.size_of("qwen3:4b"), 4.0)
        self.assertEqual(local_fallback.size_of("lfm2:latest"), 0.0)


class LocalFallbackConsentTests(unittest.TestCase):
    def test_default_plan_refuses_without_consent(self):
        with mock.patch.object(local_fallback, "installed") as installed:
            result = local_fallback.plan()
        self.assertFalse(result["ok"])
        self.assertIn("local_fallback_consent", result["note"])
        installed.assert_not_called()

    def test_prepare_switch_refuses_without_consent(self):
        builder = mock.Mock()
        result = asyncio.run(local_fallback.prepare_switch(plan_builder=builder))
        self.assertIsNone(result)
        builder.assert_not_called()


class ThePlan(_Server):
    models = ["lfm2:2b-q4_K_M", "qwen3:2b-q4_K_M"]

    def test_with_a_model_and_hearing_the_plan_is_complete(self):
        with mock.patch.object(local_fallback, "find_spec", return_value=object()):
            plan = local_fallback.plan(self.url, consent=True)
        self.assertTrue(plan["ok"])
        self.assertEqual(plan["model"], "qwen3:2b-q4_K_M")
        self.assertEqual(plan["pipeline"], {"llm": "openai_compat@ollama",
                                            "stt": "whisper@local",
                                            "tts": "system_tts"})
        self.assertEqual(plan["creds"]["openai_compat@ollama"]["model"], "qwen3:2b-q4_K_M")
        self.assertTrue(plan["creds"]["openai_compat@ollama"]["base_url"].startswith(self.url))

    def test_unquantized_model_is_refused(self):
        with mock.patch.object(local_fallback, "_post", return_value={
            "details": {"quantization_level": "F16"}
        }):
            self.assertEqual(
                local_fallback.approved_models(self.url, ["qwen3:2b-q4_K_M"]), []
            )

    def test_over_capacity_models_are_excluded_before_ranking(self):
        self.assertIsNone(local_fallback.pick(["llama3:70b", "qwen3:32b"]))
        with mock.patch.object(local_fallback, "find_spec", return_value=object()):
            plan = local_fallback.plan(self.url, models=["llama3:70b"], consent=True)
        self.assertFalse(plan["ok"])
        self.assertIn("1.5B–3B", plan["note"])

    def test_no_model_installed_is_one_sentence(self):
        with mock.patch.object(local_fallback, "find_spec", return_value=object()):
            plan = local_fallback.plan(self.url, models=[], consent=True)
        self.assertFalse(plan["ok"])
        self.assertIn("quantized 1.5B–3B", plan["note"])

    def test_no_hearing_and_no_installed_recogniser_is_refused_not_faked(self):
        with mock.patch.object(local_fallback, "find_spec", return_value=None):
            plan = local_fallback.plan(self.url, current={}, consent=True)
        self.assertFalse(plan["ok"])
        self.assertIn("faster-whisper", plan["note"])

    def test_hearing_already_configured_is_reused_rather_than_lost(self):
        with mock.patch.object(local_fallback, "find_spec", return_value=None):
            plan = local_fallback.plan(self.url, current={
                "stt": "whisper@groq",
                "provider_config": {"whisper@groq": {"api_key": "kept", "base_url": "https://example.test"}},
            }, consent=True)
        self.assertTrue(plan["ok"])
        self.assertEqual(plan["pipeline"]["stt"], "whisper@groq")
        self.assertEqual(plan["creds"]["whisper@groq"]["api_key"], "kept")
        self.assertIn("faster-whisper", plan["note"])
        self.assertIn("Speech recognition still uses whisper@groq", plan["note"])

    def test_switch_warmup_exceptions_leave_the_cloud_path_available(self):
        logs = []
        result = asyncio.run(local_fallback.prepare_switch(
            consent=True,
            url=self.url,
            plan_builder=lambda **_kwargs: {
                "ok": True, "url": self.url, "model": "qwen3:4b",
            },
            warm_model=mock.Mock(side_effect=OSError("truncated response")),
            log=logs.append,
        ))
        self.assertIsNone(result)
        self.assertTrue(any("staying on the cloud retry" in line for line in logs))

    def test_switch_refuses_a_plan_when_stt_is_not_ready(self):
        logs = []
        result = asyncio.run(local_fallback.prepare_switch(
            consent=True,
            url=self.url,
            plan_builder=lambda **_kwargs: {
                "ok": True, "url": self.url, "model": "qwen3:4b",
            },
            warm_model=mock.Mock(return_value=True),
            stt_ready=lambda _plan: False,
            log=logs.append,
        ))
        self.assertIsNone(result)
        self.assertTrue(any("speech recognition is not ready" in line for line in logs))

    def test_local_stt_readiness_fails_closed_when_model_loading_fails(self):
        from providers.stt_whisper import WhisperSTT

        provider = WhisperSTT({"backend": "local"})
        loader = mock.AsyncMock(side_effect=RuntimeError("model unavailable"))
        with mock.patch.object(provider, "_ensure_model", loader):
            self.assertFalse(asyncio.run(provider.ensure_ready()))
        loader.assert_awaited_once()

    def test_local_stt_readiness_reuses_a_loaded_model(self):
        from providers.stt_whisper import WhisperSTT

        provider = WhisperSTT({"backend": "local"})
        loader = mock.AsyncMock(return_value=object())
        with mock.patch.object(provider, "_ensure_model", loader):
            self.assertTrue(asyncio.run(provider.ensure_ready()))
        loader.assert_awaited_once()

    def test_the_plan_writes_nothing(self):
        """Verify a planned fallback leaves saved provider settings untouched."""
        from memory import config_manager

        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "api_keys.json"
            config.write_text(json.dumps({"providers": {
                "mode": "gemini",
                "pipeline": {"stt": "whisper@groq"},
                "creds": {"whisper@groq": {
                    "api_key": "keep-this", "base_url": "https://example.test"}},
            }}), encoding="utf-8")
            before = config.read_bytes()
            with mock.patch.object(config_manager, "CONFIG_FILE", config):
                current = config_manager.get_pipeline()
                current["provider_config"] = {
                    "whisper@groq": config_manager.get_provider_config("whisper@groq")
                }
                with mock.patch.object(local_fallback, "find_spec", return_value=None):
                    plan = asyncio.run(local_fallback.prepare_switch(
                        current,
                        consent=True,
                        url=self.url,
                        plan_builder=lambda **kwargs: local_fallback.plan(
                            url=self.url,
                            current=kwargs.get("current"),
                            models=["qwen3:2b-q4_K_M"],
                            consent=kwargs.get("consent", False),
                        ),
                        stt_ready=lambda _plan: True,
                    ))
            self.assertTrue(plan["ok"])
            self.assertEqual(config.read_bytes(), before)


class StayingWarm(_Server):
    models = ["qwen3:4b"]

    def test_the_model_is_loaded_before_it_is_needed(self):
        self.assertTrue(local_fallback.warm(self.url, "qwen3:4b"))
        path, payload = _Fake.calls[-1]
        self.assertEqual(path, "/api/generate")
        self.assertEqual(payload["keep_alive"], local_fallback.KEEP_ALIVE)
        self.assertEqual(payload["model"], "qwen3:4b")

    def test_no_model_means_no_call(self):
        self.assertFalse(local_fallback.warm(self.url, ""))
        self.assertEqual(_Fake.calls, [])


class StartingIt(unittest.TestCase):
    def test_no_program_and_no_server_is_a_clean_false(self):
        with mock.patch.object(local_fallback.shutil, "which", return_value=None), \
             mock.patch.object(local_fallback, "running", return_value=False):
            self.assertFalse(local_fallback.start_server("http://127.0.0.1:1"))

    def test_a_server_that_already_answers_is_left_alone(self):
        with mock.patch.object(local_fallback, "running", return_value=True), \
             mock.patch.object(local_fallback.subprocess, "Popen") as started:
            self.assertTrue(local_fallback.start_server())
            started.assert_not_called()


if __name__ == "__main__":
    unittest.main()
