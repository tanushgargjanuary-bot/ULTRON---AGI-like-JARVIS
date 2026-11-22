"""Test automatic local model failover when cloud rungs are exhausted."""

import unittest
from unittest.mock import MagicMock, patch

from core import gemini


class TestGeminiLocalAutoFallback(unittest.TestCase):
    def test_detect_local_fallback_returns_best_running_model(self):
        fake_model = MagicMock()
        fake_model.name = "qwen2.5-coder:7b"
        fake_model.base_url = "http://127.0.0.1:11434/v1"
        fake_model.has_code = True
        fake_model.tier = "smart"

        with patch("core.local_detector.scan_running_servers", return_value=[fake_model]):
            target = gemini._detect_local_fallback()
            self.assertEqual(target, "auto_local@qwen2.5-coder:7b@http://127.0.0.1:11434/v1")

    def test_call_fails_over_to_local_when_cloud_exhausted(self):
        fake_model = MagicMock()
        fake_model.name = "qwen2.5-coder:7b"
        fake_model.base_url = "http://127.0.0.1:11434/v1"
        fake_model.has_code = True
        fake_model.tier = "smart"

        fake_reply = gemini._Reply("Generated answer from local Qwen")

        # DECISIONS.md: automatic failover onto this machine needs the owner's
        # `local_fallback_consent`; tests/test_gemini_resilience.py covers its absence.
        with patch("core.local_detector.scan_running_servers", return_value=[fake_model]), \
                patch.object(gemini, "_local_fallback_consented", return_value=True):
            with patch.object(gemini, "_provider_call", return_value=fake_reply) as mock_prov_call:
                # Force cloud models to fail by putting them on cooldown
                with patch.object(gemini, "_cooling", return_value=True):
                    result = gemini.call("Explain Navier-Stokes", tier=gemini.FAST, key="fake-key")
                    self.assertIsNotNone(result)
                    self.assertEqual(result.text, "Generated answer from local Qwen")
                    mock_prov_call.assert_called_once()


if __name__ == "__main__":
    unittest.main()
