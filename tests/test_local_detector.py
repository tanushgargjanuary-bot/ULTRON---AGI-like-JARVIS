"""Tests for the bounded, read-only local model inventory."""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from core import local_detector, policy
from core.local_detector import LocalModelInfo
from plugins import local_models


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "http://example.com/should-not-be-followed")
            self.end_headers()
            return
        if self.path == "/large":
            body = b"x" * (local_detector._MAX_PROBE_BYTES + 1)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/tags":
            body = json.dumps({
                "models": [{"name": "qwen3:2b-q4_K_M", "size": 1234}]
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def log_message(self, *_args):
        return


class LocalModelDetectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.httpd.server_address[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        self.allowed = set(local_detector._ALLOWED_LOOPBACK_PORTS)
        self.allowed.add(self.port)
        self.patch_ports = patch.object(local_detector, "_ALLOWED_LOOPBACK_PORTS", frozenset(self.allowed))
        self.patch_ports.start()
        self.addCleanup(self.patch_ports.stop)
        local_detector.clear_cache()

    def test_estimate_params_and_capabilities(self):
        size, vision, code, tier = local_detector._estimate_params_and_tier("lfm3-omni:2b")
        self.assertEqual(size, 2.0)
        self.assertTrue(vision)
        self.assertEqual(tier, "vision")
        size, vision, code, tier = local_detector._estimate_params_and_tier("deepseek-coder:6.7b")
        self.assertEqual(size, 6.7)
        self.assertTrue(code)
        self.assertEqual(tier, "smart")

    def test_probe_refuses_non_loopback_hosts_before_network_access(self):
        with patch.object(local_detector.urllib.request, "build_opener") as build:
            self.assertIsNone(local_detector._quick_http_get("http://example.com:11434/api/tags"))
            self.assertIsNone(local_detector._quick_http_get("http://127.0.0.2:11434/api/tags"))
            build.assert_not_called()

    def test_probe_does_not_follow_redirects(self):
        self.assertIsNone(local_detector._quick_http_get(f"{self.base}/redirect"))

    def test_probe_refuses_oversized_response(self):
        self.assertIsNone(local_detector._quick_http_get(f"{self.base}/large"))

    def test_probe_reads_a_valid_loopback_response(self):
        data = local_detector._quick_http_get(f"{self.base}/api/tags")
        self.assertEqual(data["models"][0]["name"], "qwen3:2b-q4_K_M")

    def test_running_ollama_models_are_detected(self):
        with patch.object(local_detector, "LOCAL_ENDPOINTS", (
            ("ollama", self.base, "/api/tags", "/v1"),
        )):
            models = local_detector.scan_running_servers()
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].name, "qwen3:2b-q4_K_M")
        self.assertTrue(models[0].running)
        self.assertEqual(models[0].provider_id, "ollama")

    def test_disk_scan_reports_gguf_without_exposing_file_contents(self):
        with TemporaryDirectory() as folder:
            model_file = Path(folder) / "tiny-model-2b-q4.gguf"
            model_file.write_bytes(b"fake-weights")
            found = local_detector._scan_gguf_folder(
                Path(folder), "lmstudio", "http://127.0.0.1:1234/v1", set()
            )
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].name, "tiny-model-2b-q4")
        self.assertEqual(found[0].size_bytes, len(b"fake-weights"))

    def test_local_models_tool_is_read_only_and_does_not_show_private_paths(self):
        model = LocalModelInfo(
            name="qwen3:2b-q4_K_M",
            provider_id="ollama",
            base_url="http://127.0.0.1:11434/v1",
            running=True,
            param_size_b=2.0,
            tier="fast",
            location="C:/Users/private/.ollama/models",
        )
        player = MagicMock()
        with patch.object(local_models, "detect_all_local_models", return_value=[model]):
            result = local_models.run({"action": "status"}, player=player)
            denied = local_models.run({"action": "configure"}, player=player)
        self.assertIn("qwen3:2b-q4_K_M", result)
        self.assertIn("RUNNING", result)
        self.assertNotIn("private", result)
        self.assertIn("read-only", denied)
        player.show_content.assert_called_once()

    def test_local_models_is_classified_as_observe(self):
        decision = policy.decide("local_models")
        self.assertTrue(decision.allow)
        self.assertEqual(decision.tier, policy.Tier.OBSERVE)


if __name__ == "__main__":
    unittest.main()
