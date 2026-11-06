"""Offline tests for capability-based application resolution (core/app_resolver.py)
and the way actions/open_app.py now uses it.

The bug these exist for: "open browser" typed the word `browser` into the
Start-menu search box, the shell matched a FOLDER called `browser`, and the
folder opened while the assistant reported success. Nothing here uses a list of
browser names; the tests inject the operating system's answers instead.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Import the project, not whatever happens to be on the path — the rest of the
# suite does this, and without it the module only works when the test runner was
# started from the project root.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import app_resolver
from core.app_resolver import App, Backends, Resolution


def make_backends(scheme=None, installed=(), running=(), directories=()):
    handlers = dict(scheme or {})
    dirs = set(directories)
    return Backends(
        scheme_handler=lambda name: handlers.get(name),
        installed=lambda: list(installed),
        running_labels=lambda: list(running),
        is_directory=lambda target: target in dirs,
    )


class CapabilityWordTests(unittest.TestCase):
    def test_category_words_are_recognised(self):
        for phrase in ("browser", "Browser", "the web browser", "my notes app",
                       "text editor", "terminal"):
            self.assertTrue(app_resolver.is_category_word(phrase), phrase)

    def test_product_names_are_not_categories(self):
        for phrase in ("vlc", "obsidian", "blender", "spotify premium"):
            self.assertFalse(app_resolver.is_category_word(phrase), phrase)


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        app_resolver.clear_cache()
        self.addCleanup(app_resolver.clear_cache)

    def test_browser_resolves_through_the_operating_system_handler(self):
        backends = make_backends(scheme={"http": r"C:\Apps\msedge.exe"})
        result = app_resolver.resolve("browser", backends)
        self.assertEqual(result.status, app_resolver.RESOLVED)
        self.assertEqual(result.target, r"C:\Apps\msedge.exe")
        self.assertEqual(result.name, "msedge")
        self.assertIn("http", result.reason)

    def test_a_handler_that_is_a_folder_is_refused(self):
        # The exact failure mode reported: the only thing answering to the name
        # is a directory, and a directory is never an application.
        backends = make_backends(scheme={"http": r"C:\Users\me\browser"},
                                 directories=[r"C:\Users\me\browser"])
        result = app_resolver.resolve("browser", backends)
        self.assertEqual(result.status, app_resolver.UNKNOWN)
        self.assertNotEqual(result.target, r"C:\Users\me\browser")

    def test_one_installed_match_is_resolved(self):
        backends = make_backends(installed=[App("Notes", r"C:\notes.lnk")])
        result = app_resolver.resolve("notes", backends)
        self.assertEqual(result.status, app_resolver.RESOLVED)
        self.assertEqual(result.name, "Notes")

    def test_two_comparable_matches_ask_instead_of_choosing(self):
        # No application is called exactly "notes", and both of these answer to
        # the same word. Guessing here is how a folder got opened once already.
        backends = make_backends(installed=[
            App("Samsung Notes", r"C:\a.lnk"),
            App("Notes Classic", r"C:\b.lnk"),
        ])
        result = app_resolver.resolve("notes", backends)
        self.assertEqual(result.status, app_resolver.AMBIGUOUS)
        self.assertGreaterEqual(len(result.candidates), 2)
        self.assertEqual(result.target, "")
        self.assertIn("candidates", result.as_facts())

    def test_a_clear_winner_beats_a_weaker_match(self):
        backends = make_backends(installed=[
            App("Visual Studio Code", r"C:\vscode.lnk"),
            App("Code Helper Logs", r"C:\logs.lnk"),
        ])
        result = app_resolver.resolve("visual studio code", backends)
        self.assertEqual(result.status, app_resolver.RESOLVED)
        self.assertEqual(result.name, "Visual Studio Code")

    def test_an_exact_name_beats_a_similar_one(self):
        backends = make_backends(installed=[
            App("Notes", r"C:\a.lnk"),
            App("Notes Classic", r"C:\b.lnk"),
        ])
        result = app_resolver.resolve("notes", backends)
        self.assertEqual(result.status, app_resolver.RESOLVED)
        self.assertEqual(result.name, "Notes")

    def test_a_folder_only_match_reports_what_it_is(self):
        backends = make_backends(installed=[App("browser", r"C:\Users\me\browser")],
                                 directories=[r"C:\Users\me\browser"])
        result = app_resolver.resolve("browser", backends)
        self.assertEqual(result.status, app_resolver.UNKNOWN)
        self.assertIn("folder", result.reason)

    def test_already_running_is_preferred_over_launching(self):
        backends = make_backends(running=["Firefox"])
        result = app_resolver.resolve("firefox", backends)
        self.assertEqual(result.status, app_resolver.RESOLVED)
        self.assertEqual(result.reason, "already running")

    def test_nothing_installed_is_an_honest_unknown(self):
        result = app_resolver.resolve("notes", make_backends())
        self.assertEqual(result.status, app_resolver.UNKNOWN)
        self.assertTrue(result.reason)

    def test_empty_request_is_refused(self):
        self.assertEqual(app_resolver.resolve("", make_backends()).status,
                         app_resolver.UNKNOWN)

    def test_the_installed_index_is_cached(self):
        calls = []

        def installed():
            calls.append(1)
            return [App("Notes", r"C:\notes.lnk")]

        backends = Backends(scheme_handler=lambda s: None, installed=installed,
                            running_labels=list, is_directory=lambda t: False)
        app_resolver.resolve("notes", backends)
        app_resolver.resolve("notes", backends)
        self.assertEqual(len(calls), 1)
        app_resolver.clear_cache()
        app_resolver.resolve("notes", backends)
        self.assertEqual(len(calls), 2)

    def test_broken_backends_do_not_raise(self):
        def explode(*_a, **_k):
            raise OSError("registry unavailable")

        backends = Backends(scheme_handler=explode, installed=explode,
                            running_labels=explode, is_directory=explode)
        result = app_resolver.resolve("browser", backends)
        self.assertEqual(result.status, app_resolver.UNKNOWN)

    def test_default_backends_exist_on_this_platform(self):
        self.assertIsInstance(app_resolver.default_backends(), Backends)

    def test_command_line_parsing(self):
        self.assertEqual(
            app_resolver._exe_from_command('"C:\\Program Files\\B\\b.exe" -- "%1"'),
            r"C:\Program Files\B\b.exe",
        )
        self.assertEqual(app_resolver._exe_from_command(""), None)


class OpenAppIntegrationTests(unittest.TestCase):
    """open_app must act on the resolver instead of the search box."""

    def setUp(self):
        app_resolver.clear_cache()
        from actions import open_app as module

        self.module = module

    def test_ambiguous_request_asks_and_launches_nothing(self):
        resolution = Resolution(status=app_resolver.AMBIGUOUS, capability="notes",
                                candidates=(App("Notes", "a"), App("Notepad", "b")),
                                reason="2 applications match 'notes'")
        with patch.object(self.module.app_resolver, "resolve", return_value=resolution), \
             patch.object(self.module.threading, "Thread") as thread:
            result = self.module.open_app({"app_name": "notes"})
        thread.assert_not_called()
        self.assertIn("status=ask", result)
        self.assertIn("Notes", result)

    def test_unresolvable_category_word_is_reported_not_guessed(self):
        resolution = Resolution(status=app_resolver.UNKNOWN, capability="browser",
                                reason="no application is registered for 'browser'")
        with patch.object(self.module.app_resolver, "resolve", return_value=resolution), \
             patch.object(self.module.threading, "Thread") as thread, \
             patch.object(self.module, "_desktop_search") as search:
            result = self.module.open_app({"app_name": "browser"})
        thread.assert_not_called()
        search.assert_not_called()
        self.assertIn("status=failed", result)

    def test_resolved_target_is_launched_with_search_disabled(self):
        resolution = Resolution(status=app_resolver.RESOLVED, capability="browser",
                                target=r"C:\Apps\msedge.exe", name="msedge",
                                reason="default handler")
        with patch.object(self.module.app_resolver, "resolve", return_value=resolution), \
             patch.object(self.module.appidentity, "running", return_value=[]), \
             patch.object(self.module.appidentity, "snapshot", return_value=set()), \
             patch.object(self.module.threading, "Thread") as thread:
            result = self.module.open_app({"app_name": "browser"})
        thread.assert_called_once()
        args = thread.call_args.kwargs["args"]
        self.assertEqual(args[1], "msedge")                 # verified identity
        self.assertEqual(args[2], r"C:\Apps\msedge.exe")    # what gets launched
        self.assertIs(args[4], False)                        # never typed into a search box
        self.assertIn("status=started", result)


if __name__ == "__main__":
    unittest.main()
