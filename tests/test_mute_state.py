"""`actions/computer_settings.py`: "mute" means muted, "unmute" means not muted, and the answer says what was read back.

What was wrong, read in the code and shown by these tests failing on it:

* On Windows and Linux "mute", "unmute" and "toggle mute" ran the same flip (the Windows mute key, or
  `pactl set-sink-mute ... toggle`), so "unmute" on a machine that was not muted muted it, and "mute" said
  twice unmuted it again. On macOS all three ran `set volume with output muted`, which only ever mutes, so
  "unmute" muted there.
* The answer was checked by reading the volume level before and after. Muting leaves the level where it
  was, so the answer was always "unverified ... the volume still reads N%", whether or not it had worked.
* "Undo" after a mute put the volume level back, which changes nothing that can be heard.
* The model was told the word `mute` and never `unmute`.

The stand-in machine below holds one mute flag, as a real one does, and can be reached the three ways Ultron
reaches a real one: the Windows audio interface and mute key, `osascript` on macOS, `pactl` on Linux. Nothing
real is touched. Read, not run: PulseAudio's `pactl` (`get-sink-mute`, `set-sink-mute SINK 1|0|toggle`) and
AppleScript's `output muted of (get volume settings)` and `set volume output muted true|false`. Not
verified: a real Windows audio device, a real PulseAudio or PipeWire server, a real Mac.
"""

from __future__ import annotations

import contextlib
import io
import re
import unittest
from types import SimpleNamespace
from unittest import mock

from actions import computer_settings
from core import undo

PLATFORMS = ("Windows", "Darwin", "Linux")


class Sound:
    """One machine's sound: a mute flag and a level, and every way Ultron can reach them."""

    def __init__(self, muted: bool = False, level: int = 43):
        self.muted = muted
        self.level = level
        self.commands: list[list[str]] = []     # what was run on macOS and Linux
        self.keys: list[str] = []               # what was typed on Windows
        self.stuck = False                      # accepts a change and never applies it
        self.no_audio = False                   # no audio interface at all (Windows), or no sound tools (elsewhere)
        self.unreadable = False                 # will take a change, but will not say whether it is muted
        self.failed_reads = 0                   # the next few reads of the mute flag fail
        self.localised = False                  # pactl answers "ja" or "nein" unless it is asked in English

    # -- Windows: the master-volume interface, and the keyboard
    def endpoint(self):
        if self.no_audio:
            raise RuntimeError("no audio interface")
        return self

    def _readable(self) -> bool:
        if self.unreadable:
            return False
        if self.failed_reads:
            self.failed_reads -= 1
            return False
        return True

    def GetMute(self):
        if not self._readable():
            raise RuntimeError("mute state not available")
        return int(self.muted)

    def SetMute(self, value, _context):
        if not self.stuck:
            self.muted = bool(value)

    def GetMasterVolumeLevelScalar(self):
        return self.level / 100

    def SetMasterVolumeLevelScalar(self, level, _context):
        self.level = round(level * 100)

    def press(self, key):                       # pyautogui.press: the mute key is a toggle, as on a real keyboard
        self.keys.append(key)
        if key == "volumemute" and not self.stuck:
            self.muted = not self.muted

    # -- macOS and Linux: the command line
    def run(self, command, **options):
        self.commands.append(list(command))
        if self.no_audio:
            raise FileNotFoundError(command[0])
        if command[0] == "pactl":
            out = self._pactl(command, options)
        elif command[0] == "osascript":
            out = self._osascript(command[2])
        else:
            out = ""
        return SimpleNamespace(stdout=out, stderr="", returncode=0)

    def _pactl(self, command, options) -> str:
        if command[2] != "@DEFAULT_SINK@":
            return ""                                   # not the speakers: the machine is unchanged
        verb = command[1]
        if verb == "get-sink-mute":
            plain = (options.get("env") or {}).get("LC_ALL") == "C"
            words = ("yes", "no") if plain or not self.localised else ("ja", "nein")
            return f"Mute: {words[0] if self.muted else words[1]}\n" if self._readable() else ""
        if verb == "get-sink-volume":
            return f"Volume: front-left: 28180 /  {self.level}% / -22.00 dB\n"
        if verb == "set-sink-mute" and not self.stuck:
            self.muted = {"1": True, "0": False}.get(command[3], not self.muted)      # "toggle" flips
        return ""

    def _osascript(self, script: str) -> str:
        if script == "output muted of (get volume settings)":
            return ("true\n" if self.muted else "false\n") if self._readable() else "missing value\n"
        if script == "output volume of (get volume settings)":
            return f"{self.level}\n"
        if self.stuck:
            return ""
        if script.startswith("set volume output muted not"):
            self.muted = not self.muted
        elif script.startswith("set volume output muted "):
            self.muted = script.endswith("true")
        elif script == "set volume with output muted":                                  # the old spelling: it only mutes
            self.muted = True
        return ""


@contextlib.contextmanager
def on(sound: Sound, platform: str):
    """Make `platform` and `sound` the machine that the tool's code is running on."""
    with contextlib.redirect_stdout(io.StringIO()), \
            mock.patch.object(computer_settings, "_OS", platform), \
            mock.patch.object(computer_settings, "_PYAUTOGUI", True), \
            mock.patch.object(computer_settings, "pyautogui", sound), \
            mock.patch.object(computer_settings, "_win_endpoint_volume", sound.endpoint), \
            mock.patch.object(computer_settings.subprocess, "run", sound.run):
        yield


def ask(sound: Sound, platform: str, action: str) -> str:
    """Call the tool's real handler the way the model does, on `platform`, against `sound`."""
    with on(sound, platform):
        return computer_settings.computer_settings({"action": action})


def take_back(sound: Sound, platform: str) -> str:
    """The `undo` tool, on the same machine the change was made on."""
    with on(sound, platform):
        return undo.undo_last()


def status(result: str) -> str:
    return re.match(r"status=(\w+) ", result).group(1)


def fact(result: str, name: str):
    found = re.search(rf"\b{name}=(\"[^\"]*\"|\S+)", result)
    return found.group(1).strip('"') if found else None


class StateTestCase(unittest.TestCase):
    def setUp(self):
        undo.clear()
        self.addCleanup(undo.clear)


class TheStateAfterEachWord(StateTestCase):
    def test_mute_leaves_it_muted_however_many_times_it_is_said(self):
        for platform in PLATFORMS:
            with self.subTest(platform=platform):
                sound = Sound(muted=False)
                for turn in (1, 2, 3):
                    ask(sound, platform, "mute")
                    self.assertTrue(sound.muted, f"muted after saying mute {turn} time(s)")

    def test_unmute_leaves_a_machine_that_was_not_muted_not_muted(self):
        for platform in PLATFORMS:
            with self.subTest(platform=platform):
                sound = Sound(muted=False)
                ask(sound, platform, "unmute")
                self.assertFalse(sound.muted, "asking to unmute a machine that was not muted must not mute it")

    def test_unmute_unmutes_a_muted_machine(self):
        for platform in PLATFORMS:
            with self.subTest(platform=platform):
                sound = Sound(muted=True)
                ask(sound, platform, "unmute")
                self.assertFalse(sound.muted)

    def test_toggle_flips_whatever_it_finds(self):
        for platform in PLATFORMS:
            with self.subTest(platform=platform):
                sound = Sound(muted=False)
                ask(sound, platform, "toggle_mute")
                self.assertTrue(sound.muted, "not muted -> muted")
                ask(sound, platform, "toggle_mute")
                self.assertFalse(sound.muted, "muted -> not muted")

    def test_none_of_them_touches_the_volume_level(self):
        for platform in PLATFORMS:
            with self.subTest(platform=platform):
                sound = Sound(muted=False, level=43)
                for action in ("mute", "unmute", "toggle_mute", "toggle_mute", "mute"):
                    ask(sound, platform, action)
                self.assertEqual(sound.level, 43)


class TheAnswerSaysWhatWasRead(StateTestCase):
    def test_a_change_that_took_is_confirmed_from_the_mute_flag(self):
        for platform in PLATFORMS:
            for action, expected in (("mute", "true"), ("unmute", "false")):
                with self.subTest(platform=platform, action=action):
                    result = ask(Sound(muted=(action == "unmute")), platform, action)
                    self.assertEqual(status(result), "done", result)
                    self.assertEqual(fact(result, "muted"), expected, result)
                    self.assertEqual(fact(result, "verified"), "true", result)

    def test_a_toggle_that_took_is_confirmed_from_the_mute_flag(self):
        for platform in PLATFORMS:
            for start, expected in ((False, "true"), (True, "false")):
                with self.subTest(platform=platform, start=start):
                    result = ask(Sound(muted=start), platform, "toggle_mute")
                    self.assertEqual(status(result), "done", result)
                    self.assertEqual(fact(result, "muted"), expected, result)

    def test_a_change_that_did_not_take_is_not_claimed(self):
        for platform in PLATFORMS:
            with self.subTest(platform=platform):
                sound = Sound(muted=False)
                sound.stuck = True
                result = ask(sound, platform, "mute")
                self.assertEqual(status(result), "unverified", result)
                self.assertIn("still reads not muted", result, "the reason must be about the mute flag, not the volume")
                self.assertIsNone(fact(result, "verified"), result)

    def test_pactl_is_asked_in_plain_english_so_a_translated_answer_cannot_hide_the_state(self):
        sound = Sound(muted=False)
        sound.localised = True
        result = ask(sound, "Linux", "mute")
        self.assertEqual(status(result), "done", result)
        self.assertEqual(fact(result, "muted"), "true", result)

    def test_a_system_that_will_not_say_gives_no_confirmation(self):
        for platform in PLATFORMS:
            with self.subTest(platform=platform):
                sound = Sound(muted=False)
                sound.unreadable = True
                result = ask(sound, platform, "mute")
                self.assertEqual(status(result), "unverified", result)
                self.assertIn("does not report whether its sound is muted", result, "say that it is not known, not a guess")
                self.assertNotIn("volume still reads", result)
                self.assertIsNone(fact(result, "verified"), result)

    def test_a_toggle_whose_starting_point_was_not_known_is_not_called_confirmed(self):
        sound = Sound(muted=False)
        sound.failed_reads = 1                  # the first read, before the change, fails; the later ones work
        result = ask(sound, "Windows", "toggle_mute")
        self.assertTrue(sound.muted, "it still flipped, from what it could read just before pressing")
        self.assertEqual(status(result), "unverified", result)
        self.assertIsNone(fact(result, "verified"), result)

    def test_a_toggle_with_no_reading_at_all_still_flips_once_and_confirms_nothing(self):
        for platform in PLATFORMS:
            with self.subTest(platform=platform):
                sound = Sound(muted=False)
                sound.unreadable = True
                result = ask(sound, platform, "toggle_mute")
                self.assertTrue(sound.muted, "the native toggle was used, once")
                self.assertEqual(status(result), "unverified", result)
                self.assertIsNone(fact(result, "verified"), result)

    def test_with_no_audio_interface_on_windows_the_mute_key_is_the_last_resort_and_nothing_is_confirmed(self):
        sound = Sound(muted=False)
        sound.no_audio = True
        result = ask(sound, "Windows", "mute")
        self.assertEqual(sound.keys, ["volumemute"], "one press of the mute key, once")
        self.assertEqual(status(result), "unverified", result)
        self.assertIn("muted", fact(result, "reason") or "", result)


class TheUndo(StateTestCase):
    def test_undo_puts_the_sound_back_as_it_was(self):
        for platform in PLATFORMS:
            for action, start in (("mute", False), ("unmute", True), ("toggle_mute", False), ("toggle_mute", True)):
                with self.subTest(platform=platform, action=action, start=start):
                    undo.clear()
                    sound = Sound(muted=start)
                    ask(sound, platform, action)
                    self.assertTrue(undo.can_undo(), "a change that can be read back can be taken back")
                    take_back(sound, platform)
                    self.assertEqual(sound.muted, start, f"{action} from muted={start}: undo must restore the flag")

    def test_undo_does_not_touch_the_volume_level(self):
        sound = Sound(muted=False, level=43)
        ask(sound, "Linux", "mute")
        take_back(sound, "Linux")
        self.assertEqual(sound.level, 43)

    def test_nothing_is_offered_to_undo_when_the_starting_point_is_not_known(self):
        for platform in PLATFORMS:
            with self.subTest(platform=platform):
                sound = Sound(muted=False)
                sound.unreadable = True
                ask(sound, platform, "mute")
                self.assertFalse(undo.can_undo(), "an undo that restores a guess is worse than none")


class TheWordsTheModelIsGiven(StateTestCase):
    def shown(self) -> list[str]:
        text = computer_settings.TOOL["parameters"]["properties"]["action"]["description"]
        return [word.strip() for word in text.split("pick one of:", 1)[1].split("|")]

    def test_unmute_is_one_of_them(self):
        words = self.shown()
        self.assertIn("mute", words)
        self.assertIn("unmute", words, "told only `mute`, the model asks for it when the user says unmute")

    def test_every_word_it_is_shown_is_one_the_tool_understands(self):
        for word in self.shown():
            with self.subTest(word=word):
                self.assertEqual(computer_settings._detect_action(word)["action"], word)


if __name__ == "__main__":
    unittest.main()
