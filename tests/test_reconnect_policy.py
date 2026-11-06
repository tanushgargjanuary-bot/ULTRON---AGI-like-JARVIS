"""tests/test_reconnect_policy.py — the reconnect storm, and the fix.

The defect this pins down: the run loop decided a resumption handle had been
rejected by testing for the substring "handle" in the exception text. Anything
mentioning the word took that branch, delayed 0 s, and reconnected immediately —
a hot loop that filled the activity log with identical lines while the real error
stayed in a console the user never sees.

So these tests are mostly about what must NOT happen.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import reconnect_policy as policy


class ResumptionTests(unittest.TestCase):
    def test_a_dead_handle_is_dropped_and_the_retry_is_immediate(self):
        verdict = policy.classify(
            RuntimeError("INVALID_ARGUMENT: the resumption handle is no longer valid"),
            resumed_with=True,
        )
        self.assertTrue(verdict.drop_handle)
        self.assertEqual(verdict.retry_delay, policy.FIRST_RETRY)
        self.assertIn("starting fresh", verdict.message)
        self.assertTrue(verdict.tell_user)

    def test_an_ordinary_error_that_mentions_handle_is_not_a_resumption_failure(self):
        # The regression. This sentence contains "handle" and must not be treated
        # as a dead resumption handle.
        exc = RuntimeError("cannot schedule new futures after shutdown while handling audio")
        self.assertFalse(policy.looks_like_resumption_failure(exc))
        verdict = policy.classify(exc, resumed_with=True)
        self.assertFalse(verdict.drop_handle)
        self.assertGreaterEqual(verdict.retry_delay, policy.BASE_DELAY)

    def test_no_handle_means_no_handle_to_drop(self):
        verdict = policy.classify(
            RuntimeError("NOT_FOUND: session expired"), resumed_with=False
        )
        self.assertFalse(verdict.drop_handle)

    def test_the_handle_is_dropped_at_most_once_per_streak(self):
        exc = RuntimeError("the resumption handle is invalid")
        first = policy.classify(exc, resumed_with=True, consecutive=0)
        second = policy.classify(exc, resumed_with=False, consecutive=1)
        self.assertTrue(first.drop_handle)
        self.assertFalse(second.drop_handle)


class BackoffTests(unittest.TestCase):
    def test_the_delay_starts_at_the_base_and_doubles(self):
        exc = ValueError("socket closed")
        self.assertEqual(policy.classify(exc, resumed_with=False).retry_delay, 3.0)
        self.assertEqual(policy.classify(exc, resumed_with=False, backoff=3).retry_delay, 6.0)
        self.assertEqual(policy.classify(exc, resumed_with=False, backoff=6).retry_delay, 12.0)

    def test_the_delay_is_capped(self):
        verdict = policy.classify(ValueError("x"), resumed_with=False, backoff=600)
        self.assertEqual(verdict.retry_delay, policy.MAX_DELAY)

    def test_a_retry_delay_is_never_zero_after_the_first_drop(self):
        # A zero delay on a repeating failure is a spin loop.
        for consecutive in range(1, 6):
            verdict = policy.classify(ValueError("x"), resumed_with=False, consecutive=consecutive)
            self.assertGreaterEqual(verdict.retry_delay, policy.BASE_DELAY)


class TellingTheUserTests(unittest.TestCase):
    def test_the_first_failure_says_what_went_wrong(self):
        verdict = policy.classify(RuntimeError("model not found: gemini-9"), resumed_with=False)
        self.assertTrue(verdict.tell_user)
        self.assertIn("model not found", verdict.message)

    def test_a_long_streak_is_summarised_rather_than_repeated(self):
        verdict = policy.classify(RuntimeError("still failing"), resumed_with=False,
                                  consecutive=policy.TELL_USER_AFTER)
        self.assertTrue(verdict.is_storm)
        self.assertIn("4 attempts failed", verdict.message)

    def test_the_summary_is_said_once_and_not_on_every_attempt_after_it(self):
        # Saying it every time is how the log filled with identical lines.
        for consecutive in range(policy.TELL_USER_AFTER + 1, policy.TELL_USER_AFTER + 6):
            verdict = policy.classify(RuntimeError("still failing"), resumed_with=False,
                                      consecutive=consecutive)
            self.assertFalse(verdict.tell_user, consecutive)
            self.assertEqual(verdict.message, "", consecutive)
            self.assertGreaterEqual(verdict.retry_delay, policy.BASE_DELAY)


class WhichFailuresCountAsAResumptionFailureTests(unittest.TestCase):
    """The marker list is the whole point of this module — test it both ways."""

    def test_an_expired_session_is_one(self):
        for text in ("Failed to resume the session",
                     "INVALID_ARGUMENT: the resumption handle is no longer valid",
                     "NOT_FOUND: session expired",
                     "conversation handle was rejected"):
            self.assertTrue(policy.looks_like_resumption_failure(RuntimeError(text)), text)

    def test_a_bad_tuning_field_is_not(self):
        # INVALID_ARGUMENT here is about thinking/proactive config, and treating it
        # as a dead handle skipped the branch that repairs the real cause.
        for text in ("INVALID_ARGUMENT: Unknown name \"thinking_config\"",
                     "INVALID_ARGUMENT: media_resolution unsupported",
                     "invalid argument: proactive_audio unknown field"):
            self.assertFalse(policy.looks_like_resumption_failure(RuntimeError(text)), text)

    def test_a_wrong_model_name_is_not(self):
        for text in ("NOT_FOUND: model not found: gemini-9",
                     "404 model not found"):
            self.assertFalse(policy.looks_like_resumption_failure(RuntimeError(text)), text)

    def test_the_original_complaint_is_not(self):
        # The exact string that used to match the substring "handle".
        exc = RuntimeError("cannot schedule new futures after shutdown while handling audio")
        self.assertFalse(policy.looks_like_resumption_failure(exc))
        verdict = policy.classify(exc, resumed_with=True, consecutive=0)
        self.assertFalse(verdict.drop_handle)
        self.assertGreaterEqual(verdict.retry_delay, policy.BASE_DELAY)

    def test_a_nonsense_streak_number_does_not_raise(self):
        for bad in (None, "x", -5, 3.7):
            verdict = policy.classify(RuntimeError("x"), resumed_with=False,
                                      consecutive=bad)
            self.assertGreaterEqual(verdict.retry_delay, policy.BASE_DELAY)

    def test_later_failures_keep_quiet(self):
        quiet = policy.classify(RuntimeError("x"), resumed_with=False, consecutive=2)
        self.assertFalse(quiet.tell_user)


class RedactionTests(unittest.TestCase):
    def test_a_credential_shaped_token_never_reaches_the_log_line(self):
        exc = RuntimeError("401 for key AIzaSyB1234567890abcdefghijklmnop")
        verdict = policy.classify(exc, resumed_with=False)
        self.assertNotIn("AIzaSyB1234567890", verdict.message)
        self.assertIn("[redacted]", verdict.message)

    def test_a_bearer_token_is_redacted(self):
        self.assertNotIn("sk-live-abcdefghijklmnop",
                         policy.describe(RuntimeError("bad key sk-live-abcdefghijklmnop")))

    def test_the_message_is_one_short_line(self):
        exc = RuntimeError("line one\nline two\n" + "x" * 500)
        text = policy.describe(exc)
        self.assertNotIn("\n", text)
        self.assertLessEqual(len(text), 160)


class OrderingTests(unittest.TestCase):
    def test_a_handle_drop_never_both_drops_and_backs_off_for_ages(self):
        verdict = policy.classify(RuntimeError("resumption handle expired"),
                                  resumed_with=True, consecutive=0)
        self.assertLess(verdict.retry_delay, policy.BASE_DELAY)

    def test_every_verdict_carries_a_reason(self):
        for kwargs in ({"resumed_with": True}, {"resumed_with": False},
                       {"resumed_with": False, "consecutive": 9}):
            with self.subTest(**kwargs):
                self.assertTrue(policy.classify(RuntimeError("x"), **kwargs).reason)


if __name__ == "__main__":
    unittest.main()
