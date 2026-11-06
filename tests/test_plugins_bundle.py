"""Tests for the twelve shipped plugins, run through the real plugin loader.

Each plugin is loaded the way the app loads it, validated, and then called with
real arguments. A plugin that only imports is not tested: the thing that breaks
is the call, and every one of these must answer with a string and never raise.
"""

import base64
import json
import unittest
from pathlib import Path

from core.plugin_loader import discover_plugins

PLUGINS = Path(__file__).resolve().parent.parent / "plugins"


def load():
    return discover_plugins(PLUGINS, core_tool_names=set(), logger=lambda _m: None)


def call(registry, name, **parameters):
    result = registry.run(name, parameters)
    assert isinstance(result, str), f"{name} returned {type(result).__name__}"
    assert result.strip(), f"{name} returned an empty string"
    return result


class AllPluginsLoad(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = load()
        cls.rows = {row["name"]: row for row in cls.registry.list_for_ui()}

    def test_there_are_at_least_twelve(self):
        self.assertGreaterEqual(len(self.rows), 12)

    def test_every_plugin_is_valid(self):
        for name, row in self.rows.items():
            self.assertTrue(row["valid"], f"{name}: {row['error']}")

    def test_every_plugin_has_a_description(self):
        for name, row in self.rows.items():
            self.assertGreater(len(str(row["description"])), 20, name)

    def test_the_five_bridges_are_present(self):
        for name in ("rea_bridge", "hyperframes_bridge", "hindsight_bridge",
                     "voicestudio_bridge", "hypit_bridge"):
            self.assertIn(name, self.rows)

    def test_absent_bridge_says_what_to_install(self):
        # No REA on a Linux test box: the plugin must name the blocker.
        text = call(self.registry, "rea_bridge", action="help")
        self.assertIsInstance(text, str)
        self.assertTrue("install" in text.lower() or "rea" in text.lower())


class DevJson(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = load()

    def test_validates(self):
        text = call(self.registry, "dev_json", action="validate",
                    text='{"a": [1, 2]}')
        self.assertIn("valid", text)

    def test_formats(self):
        text = call(self.registry, "dev_json", action="format", text='{"a":1}')
        self.assertIn('"a": 1', text)

    def test_minifies(self):
        text = call(self.registry, "dev_json", action="minify", text='{ "a" : 1 }')
        self.assertEqual(text, '{"a":1}')

    def test_reads_a_dotted_path(self):
        text = call(self.registry, "dev_json", action="get",
                    text='{"user": {"tags": ["x", "y"]}}', path="user.tags.1")
        self.assertEqual(text, "y")

    def test_reports_the_position_of_a_syntax_error(self):
        text = call(self.registry, "dev_json", action="validate", text='{"a": 1,}')
        self.assertIn("line", text)

    def test_missing_path_is_explained(self):
        text = call(self.registry, "dev_json", action="get", text='{"a": 1}', path="b.c")
        self.assertIn("could not read", text)


class DevRegex(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = load()

    def test_finds_matches_with_groups(self):
        text = call(self.registry, "dev_regex", pattern=r"(\w+)@(\w+)",
                    text="write to ada@lovelace and to alan@turing")
        self.assertIn("2 match", text)
        self.assertIn("ada", text)

    def test_no_match_is_said_plainly(self):
        text = call(self.registry, "dev_regex", pattern="zzz", text="abc")
        self.assertIn("No match", text)

    def test_bad_pattern_names_the_error(self):
        text = call(self.registry, "dev_regex", pattern="(unclosed", text="abc")
        self.assertIn("does not compile", text)

    def test_flags_are_honoured(self):
        text = call(self.registry, "dev_regex", pattern="abc", text="ABC", flags="i")
        self.assertIn("1 match", text)


class RegexIsBounded(unittest.TestCase):
    """A pattern must not be able to freeze a turn.

    `re` has no timeout, and `(a+)+$` against forty characters of "a" ran for
    ninety seconds inside this plugin. That is a frozen window, not a slow
    answer, so the work runs in a child process with a deadline.
    """

    @classmethod
    def setUpClass(cls):
        cls.registry = load()

    def test_catastrophic_backtracking_is_stopped(self):
        import time
        started = time.monotonic()
        text = call(self.registry, "dev_regex", pattern="(a+)+$", text="a" * 40 + "b")
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 10.0, f"it took {elapsed:.1f}s — the deadline is 2s")
        self.assertIn("took longer", text)

    def test_normal_patterns_still_work_after_the_change(self):
        text = call(self.registry, "dev_regex", pattern=r"\d+", text="a1 b22 c333")
        self.assertIn("3 match", text)


class DevHash(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = load()

    def test_sha256_known_answer(self):
        text = call(self.registry, "dev_hash", action="digest", text="abc",
                    algorithm="sha256")
        self.assertIn("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", text)

    def test_base64_round_trip(self):
        encoded = call(self.registry, "dev_hash", action="b64encode", text="Ultron")
        self.assertEqual(encoded, base64.b64encode(b"Ultron").decode())
        decoded = call(self.registry, "dev_hash", action="b64decode", text=encoded)
        self.assertEqual(decoded, "Ultron")

    def test_hmac_needs_a_secret(self):
        text = call(self.registry, "dev_hash", action="hmac", text="x")
        self.assertIn("secret", text)

    def test_unknown_algorithm_lists_the_known_ones(self):
        text = call(self.registry, "dev_hash", action="digest", text="x",
                    algorithm="sha999")
        self.assertIn("sha256", text)


class DevCron(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = load()

    def test_explains_each_field(self):
        text = call(self.registry, "dev_cron", expression="0 9 * * 1-5")
        self.assertIn("minute 0", text)
        self.assertIn("hour 9", text)
        self.assertIn("Next runs", text)

    def test_accepts_a_macro(self):
        text = call(self.registry, "dev_cron", expression="@daily")
        self.assertIn("Next runs", text)

    def test_rejects_six_bad_fields(self):
        text = call(self.registry, "dev_cron", expression="99 * * * *")
        self.assertIn("not valid", text)


class CryptoIdent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = load()

    def _jwt(self):
        def part(value):
            return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")
        return f"{part({'alg': 'HS256', 'typ': 'JWT'})}.{part({'sub': 'ultron'})}.sig"

    def test_decodes_a_jwt_and_admires_it_does_not_verify(self):
        text = call(self.registry, "crypto_ident", text=self._jwt())
        self.assertIn("JWT", text)
        self.assertIn("HS256", text)
        self.assertIn("NOT checked the signature", text)

    def test_recognises_a_sha256_digest(self):
        text = call(self.registry, "crypto_ident", text="a" * 64)
        self.assertIn("SHA-256", text)

    def test_refuses_private_key_material(self):
        text = call(self.registry, "crypto_ident",
                    text="-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----")
        self.assertIn("will not decode", text)

    def test_a_uuid_is_called_a_uuid_not_base64(self):
        text = call(self.registry, "crypto_ident",
                    text="550e8400-e29b-41d4-a716-446655440000")
        self.assertIn("UUID", text)
        self.assertNotIn("base64", text)

    def test_unknown_text_says_so(self):
        text = call(self.registry, "crypto_ident", text="hello there")
        self.assertIn("do not recognise", text)


class NetCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = load()

    def test_resolves_localhost(self):
        text = call(self.registry, "net_check", action="dns", host="localhost")
        self.assertIn("resolves to", text)

    def test_refuses_a_public_port_without_permission(self):
        text = call(self.registry, "net_check", action="port", host="8.8.8.8", port=53)
        self.assertIn("allow_public", text)

    def test_reports_a_closed_private_port(self):
        text = call(self.registry, "net_check", action="port", host="127.0.0.1", port=1)
        self.assertIn("did not answer", text)

    def test_rejects_a_url_without_a_scheme(self):
        text = call(self.registry, "net_check", action="headers", url="example.com")
        self.assertIn("http", text)


class Contract(unittest.TestCase):
    """Every plugin must survive rubbish arguments."""

    def test_empty_parameters_never_raise(self):
        registry = load()
        for row in registry.list_for_ui():
            if not row["valid"]:
                continue
            result = registry.run(row["name"], {})
            self.assertIsInstance(result, str, row["name"])
            self.assertTrue(result.strip(), row["name"])

    def test_unknown_action_never_raises(self):
        registry = load()
        for name in ("dev_json", "dev_hash", "net_check", "dev_cron", "crypto_ident"):
            self.assertIsInstance(registry.run(name, {"action": "nonsense"}), str)


if __name__ == "__main__":
    unittest.main()
