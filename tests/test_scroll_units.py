"""`actions/computer_control.py` `_scroll`: "scroll down 3" is three wheel notches on every system.

pyautogui hands the number straight to the operating system. On Windows the system counts a notch as 120
units (WHEEL_DELTA), so `scroll(3)` was a fortieth of a notch and the page did not move; everywhere else
a unit is a notch. A negative amount also turned the direction round, because the sign of the amount and
the sign of the direction were multiplied. A recording stand-in takes the place of pyautogui and the
platform is set by the test, so no real mouse is touched.

Read, not run: pyautogui 0.9.54 (`_pyautogui_win.py`, `_scroll`) passes the number on as `dwData` to
`mouse_event`. Not verified: a real scroll on a real Windows desktop.

Known and not changed here: on Windows pyautogui's `hscroll` calls the vertical `_scroll` (its own docstring says
explicit horizontal scrolling is "currently just Linux"), so "scroll left" and "scroll right" move the page down
and up there. The units below are right for that call as well; making sideways scrolling work is a separate fix.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from actions import computer_control

NOTCH_ON_WINDOWS = 120


class Wheel:
    """Stands in for pyautogui: records what `_scroll` asks the system for."""

    def __init__(self):
        self.calls = []

    def scroll(self, clicks):
        self.calls.append(("scroll", clicks))

    def hscroll(self, clicks):
        self.calls.append(("hscroll", clicks))


def scrolled(platform: str, direction: str, amount: int):
    """What `_scroll` sent to the wheel, and what it told the user, on this platform."""
    wheel = Wheel()
    with mock.patch.object(computer_control, "pyautogui", wheel), \
         mock.patch.object(computer_control, "_require_pyautogui"), \
         mock.patch.object(computer_control, "sys", SimpleNamespace(platform=platform)):
        said = computer_control._scroll(direction, amount)
    return wheel.calls, said


class OnWindows(unittest.TestCase):
    def test_three_notches_is_three_hundred_and_sixty_units_in_every_direction(self):
        for direction, call, units in (("down", "scroll", -360), ("up", "scroll", 360),
                                       ("left", "hscroll", -360), ("right", "hscroll", 360)):
            with self.subTest(direction=direction):
                self.assertEqual(scrolled("win32", direction, 3)[0], [(call, units)])

    def test_one_notch_is_one_wheel_delta(self):
        self.assertEqual(scrolled("win32", "down", 1)[0], [("scroll", -NOTCH_ON_WINDOWS)])


class Elsewhere(unittest.TestCase):
    def test_a_unit_is_a_notch_so_the_number_is_passed_as_it_is(self):
        for platform in ("linux", "darwin"):
            with self.subTest(platform=platform):
                self.assertEqual(scrolled(platform, "down", 3)[0], [("scroll", -3)])
                self.assertEqual(scrolled(platform, "up", 3)[0], [("scroll", 3)])
                self.assertEqual(scrolled(platform, "right", 2)[0], [("hscroll", 2)])


class TheAmountIsASizeAndNeverADirection(unittest.TestCase):
    def test_a_negative_amount_goes_the_way_the_word_says(self):
        # The old code multiplied the two signs: "down" by -3 scrolled UP.
        for platform, unit in (("linux", 1), ("win32", NOTCH_ON_WINDOWS)):
            with self.subTest(platform=platform):
                self.assertEqual(scrolled(platform, "down", -3)[0], [("scroll", -3 * unit)])
                self.assertEqual(scrolled(platform, "up", -3)[0], [("scroll", 3 * unit)])

    def test_the_amount_is_held_between_one_and_sixty_notches(self):
        for platform, unit in (("linux", 1), ("win32", NOTCH_ON_WINDOWS)):
            with self.subTest(platform=platform):
                self.assertEqual(scrolled(platform, "down", 0)[0], [("scroll", -1 * unit)], "zero still moves")
                self.assertEqual(scrolled(platform, "down", 999)[0], [("scroll", -60 * unit)], "a runaway is capped")

    def test_the_reply_names_the_notches_actually_scrolled(self):
        self.assertEqual(scrolled("win32", "down", 3)[1], "Scrolled down ×3")
        self.assertEqual(scrolled("win32", "up", 999)[1], "Scrolled up ×60")
        self.assertEqual(scrolled("win32", "down", -2)[1], "Scrolled down ×2")


if __name__ == "__main__":
    unittest.main()
