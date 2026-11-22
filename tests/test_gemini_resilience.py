"""`core/gemini.py`: what counts as an outage, which key is in use, and who may answer.

Three faults, each reproduced before it was fixed.

1. Error classification matched numbers ANYWHERE in the message. A 400 whose text said
   "maxOutputTokens 500" was a server error, a request id containing 429 was a quota
   error, a stray "404" meant "gone" — and the model was then rested for thirty minutes
   (six hours for "gone"), for a mistake in the request that resting does nothing about.
2. The API key was cached for the whole process, and an empty answer was cached too.
   Start the app, meet the first-run screen, type a key: every one-shot call said "no
   key" until the next launch. A key replaced after "API key not valid" was never
   picked up, and the models set aside under the old key stayed set aside.
3. After every cloud model failed, `call()` scanned the loopback ports and sent the
   prompt to whatever answered, without `local_fallback_consent`. DECISIONS.md: "a
   failover rung never switches silently, in any direction".
"""

from __future__ import annotations

import builtins
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from core import failures, gemini

QUOTA = "quota"
GONE = "gone"
UNAVAILABLE = "unavailable"
NONE = "none"


def classify(message: str) -> str:
    if gemini.is_quota_error(message):
        return QUOTA
    if gemini.is_gone_error(message):
        return GONE
    if gemini.is_unavailable_error(message):
        return UNAVAILABLE
    return NONE


CASES = [
    # (message, what it is, what was wrong with the old substring matching)
    ("429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'x'}}", QUOTA),
    ("RESOURCE_EXHAUSTED", QUOTA),
    ("429", QUOTA),
    ("Client error '429 Too Many Requests' for url 'https://x'", QUOTA),
    ("429 Client Error: Too Many Requests for url: https://x", QUOTA),
    ("1011 None. You exceeded your current quota, please check your plan.", QUOTA),
    ("503 UNAVAILABLE. The model is overloaded", UNAVAILABLE),
    ("504 DEADLINE_EXCEEDED", UNAVAILABLE),
    ("500 INTERNAL. oops", UNAVAILABLE),
    ("{'error': {'code': 503, 'message': 'x'}}", UNAVAILABLE),
    ("ConnectError: [Errno 111] Connection refused", UNAVAILABLE),
    ("The read operation timed out", UNAVAILABLE),
    ("received 1011 (internal error) keepalive ping timeout", UNAVAILABLE),
    ("404 NOT_FOUND. models/foo is not found for API version v1beta", GONE),
    ("403 PERMISSION_DENIED. The caller does not have permission", GONE),
    ("RuntimeError: 404 not configured: base_url", GONE),
    # The faults: none of these is the model's availability.
    ("400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': "
     "'maxOutputTokens 500 is too large'}}", NONE),            # was UNAVAILABLE ("500")
    ("400 INVALID_ARGUMENT. API key not valid. See the timeout docs", NONE),   # "timeout"
    ("400 INVALID_ARGUMENT. request id 14293 was rejected", NONE),             # was QUOTA
    ("422 UNPROCESSABLE. the 404 page of the manual", NONE),                   # was GONE
    ("401 UNAUTHENTICATED. key rejected, permission unclear", NONE),           # "permission"
    ("PermissionError: [Errno 13] Permission denied: '/tmp/x'", NONE),         # was GONE
    ("FileNotFoundError: [Errno 2] No such file or directory: 'x'", NONE),
    ("Request failed after 500 ms", NONE),                                      # was UNAVAILABLE
    ("", NONE),
]


class ErrorClassification(unittest.TestCase):
    def test_every_case(self):
        for message, expected in CASES:
            with self.subTest(message=message):
                self.assertEqual(classify(message), expected, message)

    def test_the_status_is_read_from_where_a_status_is_written(self):
        for message, status in [("429 RESOURCE_EXHAUSTED", 429),
                                ("ClientError: 503 UNAVAILABLE", 503),
                                ("HTTP 404", 404),
                                ("status_code=502", 502),
                                ("{'code': 504}", 504),
                                ("received 1011 (internal error)", 0),
                                ("Request failed after 500 ms", 0),
                                ("", 0), (None, 0)]:
            with self.subTest(message=message):
                self.assertEqual(gemini.http_status(message), status)

    def test_the_real_sdk_errors_are_classified(self):
        try:
            from google.genai import errors
        except ImportError as error:
            self.skipTest(f"google-genai is not installed: {error}")
        def make(code, status, message):
            return errors.APIError(code, {"error": {"code": code, "status": status,
                                                    "message": message}})
        for error, expected in [
                (make(429, "RESOURCE_EXHAUSTED", "You exceeded your current quota"), QUOTA),
                (make(503, "UNAVAILABLE", "The model is overloaded"), UNAVAILABLE),
                (make(404, "NOT_FOUND", "models/x is not found"), GONE),
                (make(400, "INVALID_ARGUMENT", "maxOutputTokens 500 timeout 403"), NONE)]:
            with self.subTest(code=error.code):
                self.assertEqual(classify(str(error)), expected, str(error))


class _StoppedClock:
    """`time` as `core.gemini` sees it, with a monotonic clock that has not ticked.

    Windows' clock in Python 3.12 moves in steps of 15.6 ms, so two reads in a row often give
    the same second. These tests read a rest back as `deadline - now`, and at some seconds of
    uptime that sum is not exact in floating point: 300.00000000000006 was seen on a hosted
    Windows runner (CI run 45037801726) against a limit of 300. With the clock standing at a
    whole second the sum is exact, so each test says what it means: this model is rested for
    exactly this long. Everything else on `time` stays real.
    """

    NOW = 1000.0

    def monotonic(self):
        return self.NOW

    def __getattr__(self, name):
        return getattr(time, name)


class LadderBehaviour(unittest.TestCase):
    """Drive `call()` with a fake client and look at which model is rested afterwards."""

    MODEL = "gemini-test-model"

    def setUp(self):
        failures.clear()
        patches = [
            mock.patch.object(gemini, "_cooldown", {}),
            mock.patch.object(gemini, "time", _StoppedClock()),
            mock.patch.object(gemini, "_LADDERS", {gemini.FAST: (self.MODEL,),
                                                   gemini.SMART: (self.MODEL,),
                                                   gemini.SEARCH: (self.MODEL,)}),
            mock.patch.object(gemini, "_provider_rungs", return_value=()),
            mock.patch.object(gemini, "_provider_first", return_value=False),
            mock.patch.object(gemini, "api_key", return_value="a-key"),
            mock.patch.object(gemini, "_local_refusal_noted", False),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def fail_with(self, message):
        fake = mock.MagicMock()
        fake.models.generate_content.side_effect = RuntimeError(message)
        return mock.patch.object(gemini, "client", return_value=fake)

    def call_without_local(self):
        with mock.patch.object(gemini, "_local_fallback_consented", return_value=False), \
                mock.patch.object(builtins, "print"):
            return gemini.call("hello", tier=gemini.FAST, key="a-key")

    def test_a_bad_request_does_not_rest_the_model(self):
        with self.fail_with("400 INVALID_ARGUMENT. maxOutputTokens 500 exceeds the limit; "
                            "timeout 403"):
            self.assertIsNone(self.call_without_local())
        self.assertFalse(gemini._cooling(self.MODEL), "a 400 is not the model's fault")

    def test_an_overloaded_model_is_rested_for_the_short_time(self):
        with self.fail_with("503 UNAVAILABLE. overloaded"):
            self.call_without_local()
        self.assertTrue(gemini._cooling(self.MODEL))
        remaining = gemini._cooldown[self.MODEL] - _StoppedClock.NOW
        self.assertEqual(remaining, gemini._UNAVAILABLE_SECONDS)
        self.assertGreater(remaining, gemini._COOLDOWN_SECONDS)

    def test_an_exhausted_model_is_rested_for_the_quota_time(self):
        with self.fail_with("429 RESOURCE_EXHAUSTED. quota"):
            self.call_without_local()
        remaining = gemini._cooldown[self.MODEL] - _StoppedClock.NOW
        self.assertEqual(remaining, gemini._COOLDOWN_SECONDS)

    def test_a_missing_model_is_set_aside_for_the_long_time(self):
        with self.fail_with("404 NOT_FOUND. models/x is not found"):
            self.call_without_local()
        remaining = gemini._cooldown[self.MODEL] - _StoppedClock.NOW
        self.assertGreater(remaining, gemini._UNAVAILABLE_SECONDS)


class LocalFailoverNeedsConsent(unittest.TestCase):
    """The existing test, `test_gemini_local_auto_fallback`, covers the consented path."""

    def setUp(self):
        failures.clear()
        patches = [
            mock.patch.object(gemini, "_cooldown", {}),
            mock.patch.object(gemini, "_LADDERS", {gemini.FAST: ("m",), gemini.SMART: ("m",),
                                                   gemini.SEARCH: ("m",)}),
            mock.patch.object(gemini, "_provider_rungs", return_value=()),
            mock.patch.object(gemini, "_provider_first", return_value=False),
            mock.patch.object(gemini, "_local_refusal_noted", False),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        broken = mock.MagicMock()
        broken.models.generate_content.side_effect = RuntimeError("503 UNAVAILABLE")
        patcher = mock.patch.object(gemini, "client", return_value=broken)
        patcher.start()
        self.addCleanup(patcher.stop)

    def call(self):
        with mock.patch.object(builtins, "print"):
            return gemini.call("hello", tier=gemini.FAST, key="a-key")

    def test_without_consent_nothing_is_probed_and_nothing_is_sent(self):
        with mock.patch.object(gemini, "_local_fallback_consented", return_value=False), \
                mock.patch.object(gemini, "_detect_local_fallback") as detect, \
                mock.patch.object(gemini, "_provider_call") as send:
            self.assertIsNone(self.call())
        detect.assert_not_called()
        send.assert_not_called()

    def test_the_refusal_leaves_one_note_not_one_per_call(self):
        with mock.patch.object(gemini, "_local_fallback_consented", return_value=False):
            for _ in range(5):
                self.call()
        notes = [n for n in failures.recent() if n["where"] == "gemini.local_fallback"]
        self.assertEqual(len(notes), 1)
        self.assertIn("local_fallback_consent", notes[0]["error"])

    def test_with_consent_the_local_model_answers_and_it_is_noted(self):
        reply = gemini._Reply("from the local model")
        with mock.patch.object(gemini, "_local_fallback_consented", return_value=True), \
                mock.patch.object(gemini, "_detect_local_fallback",
                                  return_value="auto_local@m@http://127.0.0.1:1/v1"), \
                mock.patch.object(gemini, "_provider_call", return_value=reply):
            result = self.call()
        self.assertEqual(result.text, "from the local model")
        notes = [n for n in failures.recent() if n["where"] == "gemini.local_fallback"]
        self.assertEqual(len(notes), 1, "a local answer must never be invisible")

    def test_with_consent_a_failing_local_model_is_noted_and_returns_none(self):
        with mock.patch.object(gemini, "_local_fallback_consented", return_value=True), \
                mock.patch.object(gemini, "_detect_local_fallback",
                                  return_value="auto_local@m@http://127.0.0.1:1/v1"), \
                mock.patch.object(gemini, "_provider_call",
                                  side_effect=RuntimeError("local server fell over")):
            self.assertIsNone(self.call())
        notes = [n for n in failures.recent() if n["where"] == "gemini.local_fallback"]
        self.assertEqual(len(notes), 1)
        self.assertIn("fell over", notes[0]["error"])

    def test_a_consent_lookup_that_fails_means_no(self):
        from memory import config_manager as cm
        with mock.patch.object(cm, "get_local_fallback_consent",
                               side_effect=OSError("config unreadable")):
            self.assertFalse(gemini._local_fallback_consented())

    def test_only_a_literal_true_is_consent(self):
        from memory import config_manager as cm
        for value, expected in [(True, True), ("true", False), (1, False), (None, False),
                                ("yes", False)]:
            with self.subTest(value=value), \
                    mock.patch.object(cm, "load_api_keys",
                                      return_value={"local_fallback_consent": value}):
                self.assertIs(cm.get_local_fallback_consent(), expected)


class KeyCaching(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name) / "api_keys.json"
        for patcher in (mock.patch.object(gemini, "_KEY_FILE", self.file),
                        mock.patch.object(gemini, "_cached_key", None),
                        mock.patch.object(gemini, "_key_sig", None),
                        mock.patch.object(gemini, "_cooldown", {})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def write(self, key):
        self.file.write_text(json.dumps({"gemini_api_key": key}), encoding="utf-8")
        # A filesystem stamps files with a coarse clock (1-4 ms on Linux), so two writes
        # in a row can get one timestamp. Give each write its own, as real edits have.
        self.ticks = getattr(self, "ticks", 0) + 1
        os.utime(self.file, ns=(self.ticks * 10**9, self.ticks * 10**9))

    def test_a_key_typed_after_an_empty_start_is_used_without_a_restart(self):
        self.assertEqual(gemini.api_key(), "", "no file yet")
        self.write("AIza-typed-on-first-run")
        self.assertEqual(gemini.api_key(), "AIza-typed-on-first-run")

    def test_an_empty_key_is_not_remembered_over_a_new_file(self):
        self.write("")
        self.assertEqual(gemini.api_key(), "")
        self.write("AIza-now-there")
        self.assertEqual(gemini.api_key(), "AIza-now-there")

    def test_a_replaced_key_is_picked_up(self):
        self.write("AIza-old")
        self.assertEqual(gemini.api_key(), "AIza-old")
        self.write("AIza-new")
        self.assertEqual(gemini.api_key(), "AIza-new")

    def test_an_unchanged_file_is_not_read_again(self):
        self.write("AIza-same")
        gemini.api_key()
        with mock.patch.object(Path, "read_text", side_effect=AssertionError("re-read")):
            self.assertEqual(gemini.api_key(), "AIza-same")

    def test_a_new_key_brings_back_the_models_the_old_one_lost(self):
        self.write("AIza-old")
        gemini.api_key()
        gemini._cool("gemini-x", gemini._GONE_SECONDS)       # a 403/404 earned under the old key
        self.assertTrue(gemini._cooling("gemini-x"))
        self.write("AIza-new")
        gemini.api_key()
        self.assertFalse(gemini._cooling("gemini-x"))

    def test_the_same_key_rewritten_keeps_the_rest(self):
        self.write("AIza-same")
        gemini.api_key()
        gemini._cool("gemini-x", gemini._GONE_SECONDS)
        self.write("AIza-same")                              # the file changed, the key did not
        gemini.api_key()
        self.assertTrue(gemini._cooling("gemini-x"))

    def test_a_read_that_fails_keeps_the_key_we_had(self):
        self.write("AIza-kept")
        self.assertEqual(gemini.api_key(), "AIza-kept")
        self.write("AIza-changed-but-unreadable")
        with mock.patch.object(Path, "read_text",
                               side_effect=PermissionError(13, "in use by another process")):
            self.assertEqual(gemini.api_key(), "AIza-kept")
        self.assertEqual(gemini.api_key(), "AIza-changed-but-unreadable",
                         "and it looks again next time")

    def test_a_damaged_file_does_not_raise(self):
        self.file.write_text('{"gemini_api_key": "AIzaHALF', encoding="utf-8")
        self.assertEqual(gemini.api_key(), "")

    def test_a_byte_order_mark_is_not_damage(self):
        self.file.write_bytes(b"\xef\xbb\xbf" + json.dumps({"gemini_api_key": "AIza-bom"}).encode())
        self.assertEqual(gemini.api_key(), "AIza-bom")

    def test_refresh_still_forces_a_read(self):
        self.write("AIza-one")
        gemini.api_key()
        with mock.patch.object(Path, "read_text", wraps=self.file.read_text) as reader:
            gemini.api_key(refresh=True)
        self.assertEqual(reader.call_count, 1)


if __name__ == "__main__":
    unittest.main()
