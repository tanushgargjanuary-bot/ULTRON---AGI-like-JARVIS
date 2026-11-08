"""tests/test_security_hardening.py — the guards this issue asked for, pinned.

Five findings from the November 2026 review, each turned into a test so the fix
cannot quietly walk back:

    ShellInjectionTests        `shell=True` must not come back in the code that
                               was cleaned (open_app, dev_agent). The rule lives
                               in core/bridges.py ("No shell, ever"); these are
                               the two files where it used to be broken.
    SslVerificationTests       fetch_web_page retried an SSL failure with
                               verify=False, silently turning every certificate
                               error into an insecure fetch. A verification
                               failure is now an error the user hears, not a
                               reason to drop TLS.
    DashboardBindingTests      the remote-control dashboard bound 0.0.0.0 by
                               default; on a laptop on café Wi-Fi that publishes
                               the command surface to the whole network. The
                               default is loopback; only an explicit config key
                               opens it up.
    SecretRedactionTests       the crash report promises "anything shaped like a
                               key is removed before it is written". These check
                               the scrubber against the shapes that actually
                               occur — Google/AIza, OpenAI/sk-, and bearer
                               tokens — so the promise stays true.
    FuzzyBoundsTests           damerau_levenshtein allocated O(m·n) cells with
                               no input cap; a long ASR utterance against a long
                               candidate could balloon memory on the path the
                               user waits on. Long inputs now return a bounded
                               "too far apart" answer instead of a matrix.
"""

from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _calls_with_shell(path: Path) -> list[str]:
    """Every subprocess call in `path` made with shell=True, by line number."""
    offenders = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = ""
        if isinstance(func, ast.Attribute):
            name = func.attr
        elif isinstance(func, ast.Name):
            name = func.id
        if name not in {"run", "Popen", "call", "check_output", "check_call"}:
            continue
        for kw in node.keywords:
            if kw.arg == "shell":
                if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    offenders.append(f"{path.name}:{node.lineno}")
    return offenders


class ShellInjectionTests(unittest.TestCase):
    """`core/bridges.py`: "No shell, ever. Arguments go in as a list.""""

    def test_open_app_has_no_shell_true(self):
        # Its own docstring records the injection this line used to carry:
        # "notepad.exe & whoami" reached a shell unquoted.
        self.assertEqual(_calls_with_shell(ROOT / "actions" / "open_app.py"), [])

    def test_dev_agent_has_no_shell_true(self):
        # The VS Code launcher passed a list AND shell=True together; on Windows
        # the shell re-parses the first element, so a folder with "&" or "^" in
        # its name became an argument to cmd.exe.
        self.assertEqual(_calls_with_shell(ROOT / "actions" / "dev_agent.py"), [])

    def test_the_cleaned_files_still_parse(self):
        for rel in ("actions/open_app.py", "actions/dev_agent.py"):
            compile((ROOT / rel).read_text(encoding="utf-8"), rel, "exec")


class SslVerificationTests(unittest.TestCase):
    def test_fetch_web_page_never_disables_verification(self):
        source = (ROOT / "custom_jarvis" / "tools.py").read_text(encoding="utf-8")
        self.assertNotIn("verify=False", source,
                        "an SSL failure must cost the fetch, not the certificate check")

    def test_an_ssl_failure_is_reported_as_an_error(self):
        from custom_jarvis.tools import fetch_web_page
        result = fetch_web_page("https://expired.badssl.com/")
        self.assertFalse(result.success)
        self.assertIn("SSL", result.error or "")


class DashboardBindingTests(unittest.TestCase):
    def test_default_bind_is_loopback(self):
        text = (ROOT / "dashboard" / "server.py").read_text(encoding="utf-8")
        self.assertNotIn('host="0.0.0.0"', text,
                        "the dashboard must not publish itself to the network "
                        "by default; bind to 127.0.0.1 unless the config asks")
        self.assertIn('"127.0.0.1"', text)

    def test_the_config_key_is_named_and_documented(self):
        text = (ROOT / "dashboard" / "server.py").read_text(encoding="utf-8")
        self.assertIn("dashboard_allow_lan", text,
                      "opening the dashboard to the LAN has to be an explicit, "
                      "named decision in config/api_keys.json")


class SecretRedactionTests(unittest.TestCase):
    def test_common_key_shapes_are_scrubbed(self):
        from core.crash import _scrub  # noqa: applied below
        samples = [
            "AIzaSyD-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",          # Google / Gemini
            "sk-proj-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",  # OpenAI
            "sk-abcdefghijklmnopqrstuvwxyz012345",              # OpenAI classic
            "ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",         # GitHub token
        ]
        for secret in samples:
            line = f"while calling provider with {secret} the socket closed"
            cleaned = _scrub(line)
            self.assertNotIn(secret, cleaned, f"{secret[:8]}… survived the scrubber")
            self.assertIn("[redacted]", cleaned)

    def test_bearer_tokens_are_scrubbed(self):
        from core.crash import _scrub
        cleaned = _scrub("Authorization: Bearer abcdef.fedcba-123456")
        self.assertNotIn("abcdef.fedcba-123456", cleaned)

    def test_an_ordinary_sentence_survives_untouched(self):
        from core.crash import _scrub
        sentence = "QAudioOutput returned 4 on device 0; falling back to null sink"
        self.assertEqual(_scrub(sentence), sentence,
                         "the scrubber must not eat the evidence a crash needs")


class FuzzyBoundsTests(unittest.TestCase):
    def test_long_inputs_return_a_bounded_answer(self):
        from core.fuzzy import damerau_levenshtein
        big = 20_000
        value = damerau_levenshtein("a" * big, "b" * big)
        self.assertEqual(value, big, "beyond the cap the answer is 'too far', not a matrix")

    def test_short_behaviour_is_unchanged(self):
        from core.fuzzy import damerau_levenshtein
        self.assertEqual(damerau_levenshtein("chorme", "chrome"), 1)
        self.assertEqual(damerau_levenshtein("CA", "ABC"), 2)

    def test_similarity_stays_bounded_for_long_strings(self):
        from core.fuzzy import similarity
        self.assertEqual(similarity("x" * 5000, "y" * 5000), 0.0)


if __name__ == "__main__":
    unittest.main()
