"""The rung after the last cloud model: Ollama on this machine.

A real HTTP server is started in a thread for these tests, because the shape of an
Ollama answer is the thing most likely to change and the thing a mock cannot tell us.
"""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from custom_jarvis import local_fallback


class _Fake(BaseHTTPRequestHandler):
    models: list = []
    calls: list = []

    def do_GET(self):                                    # noqa: N802 — stdlib name
        if self.path == "/api/tags":
            body = json.dumps({"models": [{"name": name} for name in self.models]}).encode()
            self._answer(200, body)
        else:
            self._answer(404, b"")

    def do_POST(self):                                   # noqa: N802 — stdlib name
        size = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(size) or b"{}")
        _Fake.calls.append((self.path, payload))
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
    models = ["lfm2:latest", "qwen3:4b", "llama3:70b"]

    def test_installed_models_are_read(self):
        self.assertEqual(sorted(local_fallback.installed(self.url)),
                         ["lfm2:latest", "llama3:70b", "qwen3:4b"])

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
        self.assertEqual(local_fallback.pick(["lfm2:latest", "qwen3:4b"]), "qwen3:4b")

    def test_a_seventy_billion_model_is_not_chosen_on_a_laptop(self):
        self.assertEqual(
            local_fallback.pick(["llama3:70b", "lfm2:latest"]), "lfm2:latest"
        )

    def test_four_billion_beat_seventy(self):
        self.assertEqual(
            local_fallback.pick(["llama3:70b", "qwen3:4b"]), "qwen3:4b"
        )

    def test_the_only_model_is_the_answer(self):
        self.assertEqual(local_fallback.pick(["mistral:7b"]), "mistral:7b")

    def test_nothing_installed_has_no_answer(self):
        self.assertIsNone(local_fallback.pick([]))

    def test_embedding_models_are_never_chosen_for_chat(self):
        self.assertEqual(local_fallback.pick(["nomic-embed-text", "qwen3:4b"]),
                         "qwen3:4b")
        self.assertIsNone(local_fallback.pick(["nomic-embed-text", "bge-m3"]))

    def test_a_size_is_read_from_the_name(self):
        self.assertEqual(local_fallback.size_of("qwen3:4b"), 4.0)
        self.assertEqual(local_fallback.size_of("lfm2:latest"), 0.0)


class ThePlan(_Server):
    models = ["lfm2:latest", "qwen3:4b"]

    def test_with_a_model_and_hearing_the_plan_is_complete(self):
        with mock.patch.object(local_fallback, "find_spec", return_value=object()):
            plan = local_fallback.plan(self.url)
        self.assertTrue(plan["ok"])
        self.assertEqual(plan["model"], "qwen3:4b")
        self.assertEqual(plan["pipeline"], {"llm": "openai_compat@ollama",
                                            "stt": "whisper@local",
                                            "tts": "system_tts"})
        self.assertEqual(plan["creds"]["openai_compat@ollama"]["model"], "qwen3:4b")
        self.assertTrue(plan["creds"]["openai_compat@ollama"]["base_url"].startswith(self.url))

    def test_no_model_installed_is_one_sentence(self):
        with mock.patch.object(local_fallback, "find_spec", return_value=object()):
            plan = local_fallback.plan(self.url, models=[])
        self.assertFalse(plan["ok"])
        self.assertIn("ollama pull", plan["note"])

    def test_no_hearing_and_no_installed_recogniser_is_refused_not_faked(self):
        with mock.patch.object(local_fallback, "find_spec", return_value=None):
            plan = local_fallback.plan(self.url, current={})
        self.assertFalse(plan["ok"])
        self.assertIn("faster-whisper", plan["note"])

    def test_hearing_already_configured_is_reused_rather_than_lost(self):
        with mock.patch.object(local_fallback, "find_spec", return_value=None):
            plan = local_fallback.plan(self.url, current={
                "stt": "whisper@groq",
                "provider_config": {"whisper@groq": {"api_key": "kept", "base_url": "https://example.test"}},
            })
        self.assertTrue(plan["ok"])
        self.assertEqual(plan["pipeline"]["stt"], "whisper@groq")
        self.assertEqual(plan["creds"]["whisper@groq"]["api_key"], "kept")
        self.assertIn("faster-whisper", plan["note"])
        self.assertIn("Speech recognition still uses whisper@groq", plan["note"])

    def test_the_plan_writes_nothing(self):
        source = open(local_fallback.__file__, encoding="utf-8").read()
        for forbidden in ("save_providers(", "save_provider_config(", "CONFIG_FILE"):
            self.assertNotIn(forbidden, source,
                             "a fallback must not rewrite the settings file")


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
