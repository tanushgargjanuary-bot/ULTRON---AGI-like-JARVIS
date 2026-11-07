"""tests/test_local_detector.py — Unit tests for local model autodetection and wise routing."""

import unittest
from unittest.mock import MagicMock, patch

from core import local_detector, local_router, policy
from plugins import local_models


class TestLocalDetector(unittest.TestCase):
    def test_estimate_params_and_tier(self):
        # 1. Vision & fast model
        param, vis, code, tier = local_detector._estimate_params_and_tier("lfm3-omni:2b")
        self.assertEqual(param, 2.0)
        self.assertTrue(vis)
        self.assertEqual(tier, "vision")

        # 2. Smart reasoning model
        param, vis, code, tier = local_detector._estimate_params_and_tier("qwen3:4b")
        self.assertEqual(param, 4.0)
        self.assertFalse(vis)
        self.assertEqual(tier, "smart")

        # 3. Coding model
        param, vis, code, tier = local_detector._estimate_params_and_tier("deepseek-coder:6.7b")
        self.assertEqual(param, 6.7)
        self.assertTrue(code)
        self.assertEqual(tier, "smart")

        # 4. Heavy model
        param, vis, code, tier = local_detector._estimate_params_and_tier("llama3:70b")
        self.assertEqual(param, 70.0)
        self.assertEqual(tier, "heavy")

    def test_wise_router_tier_selection(self):
        mock_models = [
            local_detector.LocalModelInfo(
                name="fast-model:1b",
                provider_id="ollama",
                base_url="http://127.0.0.1:11434/v1",
                running=True,
                param_size_b=1.0,
                has_vision=False,
                tier="fast",
            ),
            local_detector.LocalModelInfo(
                name="reasoning-model:8b",
                provider_id="ollama",
                base_url="http://127.0.0.1:11434/v1",
                running=True,
                param_size_b=8.0,
                has_vision=False,
                tier="smart",
            ),
            local_detector.LocalModelInfo(
                name="vision-model:2b",
                provider_id="ollama",
                base_url="http://127.0.0.1:11434/v1",
                running=True,
                param_size_b=2.0,
                has_vision=True,
                tier="vision",
            ),
        ]

        with patch("core.local_router.detect_all_local_models", return_value=mock_models):
            fast = local_router.choose_wise_local_model("fast")
            self.assertIsNotNone(fast)
            self.assertEqual(fast.name, "fast-model:1b")

            smart = local_router.choose_wise_local_model("smart")
            self.assertIsNotNone(smart)
            self.assertEqual(smart.name, "reasoning-model:8b")

            vision = local_router.choose_wise_local_model(need_vision=True)
            self.assertIsNotNone(vision)
            self.assertEqual(vision.name, "vision-model:2b")

    def test_running_only_excludes_offline_models(self):
        offline = local_detector.LocalModelInfo(
            name="offline-model:4b",
            provider_id="ollama",
            base_url="http://127.0.0.1:11434/v1",
            running=False,
            param_size_b=4.0,
            tier="smart",
        )

        with patch("core.local_router.detect_all_local_models", return_value=[offline]):
            self.assertIsNone(local_router.choose_wise_local_model(running_only=True))
            self.assertEqual(local_router.choose_wise_local_model(running_only=False), offline)

    def test_policy_includes_local_models(self):
        self.assertIn("local_models", policy.OBSERVE_TOOLS)
        dec = policy.decide("local_models")
        self.assertTrue(dec.allow)
        self.assertEqual(dec.tier, policy.Tier.OBSERVE)

    def test_plugin_run(self):
        mock_player = MagicMock()
        res = local_models.run({"action": "status"}, player=mock_player)
        self.assertIsInstance(res, str)
        self.assertTrue(len(res) > 0)
        # Verify player.show_content was called when player is provided
        mock_player.show_content.assert_called()


if __name__ == "__main__":
    unittest.main()
