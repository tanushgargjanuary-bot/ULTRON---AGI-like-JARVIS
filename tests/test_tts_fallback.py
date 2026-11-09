"""TTS fallback tests: cloud/neural failures must not silence system speech."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.tts import TTSPlayer


class WorkingEngine:
    def speak(self, _text: str) -> None:
        return None


class BrokenEngine:
    def speak(self, _text: str) -> None:
        raise RuntimeError("primary TTS unavailable")


class TTSFallbackTests(unittest.TestCase):
    def test_primary_failure_uses_installed_system_voice(self):
        on_start = Mock()
        on_done = Mock()

        with (
            patch("providers.tts_system.SystemTTS") as system_tts,
            patch("core.tts._play_audio_bytes") as play_audio,
            patch("core.tts.failures.note") as note,
        ):
            system_tts.return_value._synth_blocking.return_value = b"wav-data"

            player = TTSPlayer(BrokenEngine())
            player.speak("Hello", on_start=on_start, on_done=on_done)

        system_tts.assert_called_once_with({})
        system_tts.return_value._synth_blocking.assert_called_once_with("Hello")
        play_audio.assert_called_once_with(b"wav-data")
        note.assert_called_once()
        self.assertEqual(note.call_args.args[0], "tts.primary")
        on_start.assert_called_once_with()
        on_done.assert_called_once_with()
        self.assertFalse(player.is_playing)

    def test_empty_system_audio_is_reported_without_crashing_the_turn(self):
        on_done = Mock()

        with (
            patch("providers.tts_system.SystemTTS") as system_tts,
            patch("core.tts._play_audio_bytes") as play_audio,
            patch("core.tts.failures.note") as note,
        ):
            system_tts.return_value._synth_blocking.return_value = b""

            player = TTSPlayer(BrokenEngine())
            player.speak("Hello", on_done=on_done)

        play_audio.assert_not_called()
        self.assertEqual(note.call_count, 2)
        self.assertEqual(note.call_args_list[-1].args[0], "tts.fallback")
        on_done.assert_called_once_with()
        self.assertFalse(player.is_playing)

    def test_fallback_exception_is_logged_and_does_not_escape(self):
        on_done = Mock()

        with (
            patch("providers.tts_system.SystemTTS") as system_tts,
            patch("core.tts.failures.note") as note,
        ):
            system_tts.return_value._synth_blocking.side_effect = RuntimeError("no system voice")

            player = TTSPlayer(BrokenEngine())
            player.speak("Hello", on_done=on_done)

        self.assertEqual(note.call_count, 2)
        self.assertEqual(note.call_args_list[-1].args[0], "tts.fallback")
        on_done.assert_called_once_with()
        self.assertFalse(player.is_playing)

    def test_primary_success_does_not_create_system_fallback(self):
        with (
            patch("providers.tts_system.SystemTTS") as system_tts,
            patch("core.tts._play_audio_bytes") as play_audio,
            patch("core.tts.failures.note") as note,
        ):
            player = TTSPlayer(WorkingEngine())
            player.speak("Hello")

        system_tts.assert_not_called()
        play_audio.assert_not_called()
        note.assert_not_called()
        self.assertFalse(player.is_playing)

    def test_on_start_error_is_not_misreported_as_primary_tts_failure(self):
        on_done = Mock()
        bad_start = Mock(side_effect=RuntimeError("start callback failed"))

        with (
            patch("providers.tts_system.SystemTTS") as system_tts,
            patch("core.tts.failures.note") as note,
        ):
            player = TTSPlayer(BrokenEngine())
            player.speak("Hello", on_start=bad_start, on_done=on_done)

        system_tts.assert_not_called()
        self.assertEqual(note.call_count, 1)
        self.assertEqual(note.call_args.args[0], "tts.lifecycle")
        on_done.assert_called_once_with()
        self.assertFalse(player.is_playing)


if __name__ == "__main__":
    unittest.main()
