"""The dashboard's failed-login counter forgets, and cannot be made to forget the wrong thing.

`dashboard/server.py` keeps a count of failed pairing-key attempts per client address. Two
things made its table grow for ever:

* `blocked_for` stored an empty list for every address that merely ASKED, so a client that never
  failed still got a row, and nothing removed it. Measured: 100,000 addresses, about 21 MB.
* `record_failure` never pruned and nothing capped the table.

The fix keeps rows only for addresses that failed, keeps the last few failures of each, and caps
the table. What must not change: who is blocked, and for how long. One test below compares the new
class with a copy of the old one over thousands of random steps. And one must be impossible to
break: filling the table with other addresses must never unlock a locked-out one.

`dashboard.server` imports without FastAPI, so nothing here starts a server.
"""

from __future__ import annotations

import random
import threading
import time
import unittest
from unittest import mock

from dashboard import server

CAP = server._THROTTLE_MAX_ADDRESSES
TRIES = server._LOGIN_MAX_TRIES
WINDOW = server._LOGIN_WINDOW
LOCKOUT = server._LOGIN_LOCKOUT


class _Clock:
    """A clock the test moves by hand, installed in place of the server module's `time`."""

    def __init__(self, start: float = 1_000_000.0):
        self.now = start

    def time(self) -> float:
        return self.now

    def __enter__(self):
        self._patch = mock.patch.object(server, "time", self)
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()
        return False

    def __getattr__(self, name):                    # anything else the module asks of `time`
        return getattr(time, name)


class _OldThrottle:
    """The class as it was before: the reference the new one is compared with."""

    def __init__(self):
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def blocked_for(self, who):
        now = server.time.time()
        with self._lock:
            tries = [t for t in self._fails.get(who, []) if now - t < WINDOW]
            self._fails[who] = tries
            if len(tries) < TRIES:
                return 0.0
            return max(0.0, LOCKOUT - (now - tries[-1]))

    def record_failure(self, who):
        with self._lock:
            self._fails.setdefault(who, []).append(server.time.time())

    def clear(self, who):
        with self._lock:
            self._fails.pop(who, None)


class AskingRecordsNothing(unittest.TestCase):
    def test_many_addresses_that_only_ask_leave_no_rows(self):
        throttle = server._Throttle()
        for number in range(10_000):
            self.assertEqual(throttle.blocked_for(f"198.51.{number // 250}.{number % 250}"), 0.0)
        self.assertEqual(len(throttle._fails), 0, "asking made rows; 100,000 of them were about 21 MB")

    def test_an_address_whose_failures_have_aged_out_loses_its_row_when_it_asks_again(self):
        with _Clock() as clock:
            throttle = server._Throttle()
            throttle.record_failure("203.0.113.9")
            self.assertEqual(len(throttle._fails), 1)
            clock.now += WINDOW + 1
            self.assertEqual(throttle.blocked_for("203.0.113.9"), 0.0)
            self.assertEqual(len(throttle._fails), 0)

    def test_an_address_with_live_failures_keeps_its_row_when_it_asks(self):
        with _Clock():
            throttle = server._Throttle()
            throttle.record_failure("203.0.113.9")
            throttle.blocked_for("203.0.113.9")
            self.assertEqual(len(throttle._fails["203.0.113.9"]), 1)


class TheTableIsBounded(unittest.TestCase):
    def test_a_flood_of_distinct_addresses_cannot_grow_it_past_the_cap(self):
        with _Clock():
            throttle = server._Throttle()
            for number in range(CAP * 3):
                throttle.record_failure(f"2001:db8::{number:x}")
                self.assertLessEqual(len(throttle._fails), CAP)

    def test_a_row_holds_only_the_last_few_failures(self):
        with _Clock():
            throttle = server._Throttle()
            for _ in range(500):
                throttle.record_failure("203.0.113.9")
            self.assertEqual(len(throttle._fails["203.0.113.9"]), TRIES)

    def test_rows_that_have_aged_out_are_the_first_to_go(self):
        with _Clock() as clock:
            throttle = server._Throttle()
            for number in range(CAP):
                throttle.record_failure(f"old-{number}")
            clock.now += WINDOW + 1
            throttle.record_failure("fresh-1")
            throttle.record_failure("fresh-2")
            self.assertEqual(set(throttle._fails), {"fresh-1", "fresh-2"},
                             "live rows were forgotten while dead ones were kept")

    def test_when_every_row_is_live_the_oldest_unlocked_ones_go_first(self):
        with _Clock() as clock:
            throttle = server._Throttle()
            for number in range(CAP + 10):
                clock.now += 0.001
                throttle.record_failure(f"a-{number}")
            self.assertLessEqual(len(throttle._fails), CAP)
            self.assertIn(f"a-{CAP + 9}", throttle._fails, "the newest row was forgotten")
            self.assertNotIn("a-0", throttle._fails, "the oldest row was kept")

    def test_it_goes_below_the_cap_so_the_next_failure_does_not_repeat_the_work(self):
        with _Clock() as clock:
            throttle = server._Throttle()
            for number in range(CAP + 1):
                clock.now += 0.001
                throttle.record_failure(f"a-{number}")
            self.assertLess(len(throttle._fails), CAP)
            with mock.patch.object(throttle, "_forget", wraps=throttle._forget) as forget:
                throttle.record_failure("one-more")
            forget.assert_not_called()


class AFloodCannotUnlockAnAddress(unittest.TestCase):
    def locked(self, throttle, who):
        for _ in range(TRIES):
            throttle.record_failure(who)
        self.assertGreater(throttle.blocked_for(who), 0)

    def test_filling_the_table_with_other_addresses_leaves_a_locked_one_locked(self):
        with _Clock() as clock:
            throttle = server._Throttle()
            self.locked(throttle, "203.0.113.9")
            for number in range(CAP * 3):
                clock.now += 0.001
                throttle.record_failure(f"198.51.100.{number}")
            self.assertGreater(throttle.blocked_for("203.0.113.9"), 0,
                               "a flood from other addresses unlocked a locked-out one")

    def test_even_when_the_oldest_row_of_all_is_the_locked_one(self):
        with _Clock() as clock:
            throttle = server._Throttle()
            self.locked(throttle, "203.0.113.9")             # the oldest row in the table
            clock.now += 1
            for number in range(CAP + 50):
                clock.now += 0.001
                throttle.record_failure(f"x-{number}")
            self.assertIn("203.0.113.9", throttle._fails)

    def test_a_locked_address_is_forgotten_only_when_the_lockout_has_run_out(self):
        with _Clock() as clock:
            throttle = server._Throttle()
            self.locked(throttle, "203.0.113.9")
            clock.now += WINDOW + 1
            self.assertEqual(throttle.blocked_for("203.0.113.9"), 0.0)
            self.assertEqual(len(throttle._fails), 0)


class WhoIsBlockedIsUnchanged(unittest.TestCase):
    def test_the_rules_the_routes_depend_on(self):
        with _Clock() as clock:
            throttle = server._Throttle()
            for _ in range(TRIES - 1):
                throttle.record_failure("203.0.113.9")
            self.assertEqual(throttle.blocked_for("203.0.113.9"), 0.0, "one try left is not blocked")
            throttle.record_failure("203.0.113.9")
            self.assertAlmostEqual(throttle.blocked_for("203.0.113.9"), LOCKOUT, places=3)
            clock.now += 100
            self.assertAlmostEqual(throttle.blocked_for("203.0.113.9"), LOCKOUT - 100, places=3)
            self.assertEqual(throttle.blocked_for("198.51.100.1"), 0.0, "another address is not blocked")
            clock.now += WINDOW
            self.assertEqual(throttle.blocked_for("203.0.113.9"), 0.0)

    def test_a_success_clears_the_count(self):
        with _Clock():
            throttle = server._Throttle()
            for _ in range(TRIES - 1):
                throttle.record_failure("203.0.113.9")
            throttle.clear("203.0.113.9")
            throttle.record_failure("203.0.113.9")
            self.assertEqual(throttle.blocked_for("203.0.113.9"), 0.0)

    def test_clearing_an_address_that_has_no_row_is_not_an_error(self):
        server._Throttle().clear("never-seen")

    def test_the_new_class_answers_exactly_as_the_old_one_did_over_random_histories(self):
        # Few enough addresses that the cap never comes into it, so the only difference allowed is
        # memory. Four seeds of 1,500 steps each.
        for seed in range(4):
            rng = random.Random(seed)
            with _Clock() as clock:
                new, old = server._Throttle(), _OldThrottle()
                addresses = [f"192.0.2.{n}" for n in range(1, 7)]
                for step in range(1500):
                    who = rng.choice(addresses)
                    action = rng.random()
                    clock.now += rng.choice([0.0, 0.5, 5.0, 40.0, 120.0, 400.0])
                    if action < 0.45:
                        new.record_failure(who)
                        old.record_failure(who)
                    elif action < 0.55:
                        new.clear(who)
                        old.clear(who)
                    else:
                        self.assertAlmostEqual(new.blocked_for(who), old.blocked_for(who), places=6,
                                               msg=f"seed {seed} step {step}: {who} is answered differently")


class ItIsSafeFromSeveralThreads(unittest.TestCase):
    def test_concurrent_failures_neither_raise_nor_break_the_cap(self):
        throttle = server._Throttle()
        errors: list[BaseException] = []

        def hammer(offset: int):
            try:
                for number in range(1500):
                    throttle.record_failure(f"t{offset}-{number}")
                    throttle.blocked_for(f"t{offset}-{number // 2}")
            except BaseException as error:              # noqa: BLE001
                errors.append(error)

        threads = [threading.Thread(target=hammer, args=(index,)) for index in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        self.assertEqual(errors, [])
        self.assertLessEqual(len(throttle._fails), CAP)


class TheRoutesStillUseIt(unittest.TestCase):
    def test_the_server_builds_one_and_the_routes_call_the_same_three_methods(self):
        import inspect
        text = inspect.getsource(server)
        self.assertIn("self._throttle                    = _Throttle()", text)
        for call in ("self._throttle.blocked_for(who)", "self._throttle.record_failure(who)",
                     "self._throttle.clear(who)"):
            self.assertIn(call, text)


if __name__ == "__main__":
    unittest.main()
