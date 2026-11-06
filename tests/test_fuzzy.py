"""tests/test_fuzzy.py — the matcher, measured as an accuracy, not a vibe.

THE FIXTURE IS THE POINT
    `MISHEARD` below is the test: 33 pairs of (what speech recognition hands us,
    what the user actually meant). It is scored as top-1 accuracy, so a change
    that "feels better" but drops the number fails. Each entry earned its place
    from a real failure mode — transposition ("chorme"), no space ("whatsapp"),
    phonetic respelling ("vyber"), initials ("vscode"), abbreviations ("ppt"),
    partial phrasing ("excel sheet").

    The junk list matters just as much: a matcher that resolves everything is
    worse than one that resolves nothing, because it acts confidently on noise.
"""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.fuzzy import (
    FuzzyIndex,
    damerau_levenshtein,
    match_score,
    metaphone,
    normalise,
    phonetic_key,
    similarity,
    soundex,
)

APPS = [
    "WhatsApp", "Google Chrome", "Visual Studio Code", "Notepad", "Microsoft Word",
    "Microsoft Excel", "Viber", "Telegram", "Spotify", "Calculator", "MS Paint",
    "Task Manager", "File Explorer", "Steam", "Discord", "Windows Terminal",
    "Microsoft PowerPoint", "Camera", "Settings",
]

# (spoken, expected app)
MISHEARD = [
    ("whats app", "WhatsApp"),
    ("whatsapp", "WhatsApp"),
    ("what's up", "WhatsApp"),
    ("what sapp", "WhatsApp"),
    ("whatsap", "WhatsApp"),
    ("chrome", "Google Chrome"),
    ("chorme", "Google Chrome"),
    ("google chorme", "Google Chrome"),
    ("vs code", "Visual Studio Code"),
    ("vscode", "Visual Studio Code"),
    ("notepad", "Notepad"),
    ("note pad", "Notepad"),
    ("word", "Microsoft Word"),
    ("excel", "Microsoft Excel"),
    ("excel sheet", "Microsoft Excel"),
    ("viber", "Viber"),
    ("vyber", "Viber"),
    ("telegram", "Telegram"),
    ("tele gram", "Telegram"),
    ("spotify", "Spotify"),
    ("spot ify", "Spotify"),
    ("calc", "Calculator"),
    ("calculator", "Calculator"),
    ("paint", "MS Paint"),
    ("task manager", "Task Manager"),
    ("file explorer", "File Explorer"),
    ("steam", "Steam"),
    ("discord", "Discord"),
    ("terminal", "Windows Terminal"),
    ("powerpoint", "Microsoft PowerPoint"),
    ("ppt", "Microsoft PowerPoint"),
    ("camera", "Camera"),
    ("settings", "Settings"),
]

JUNK = ["zxqv", "blah blah", "qqqq", "open the pod bay doors", "what is the weather today"]


class DistanceTests(unittest.TestCase):
    def test_identical(self):
        self.assertEqual(damerau_levenshtein("chrome", "chrome"), 0)

    def test_single_edit(self):
        self.assertEqual(damerau_levenshtein("chrome", "chorme"), 1)   # transposition
        self.assertEqual(damerau_levenshtein("chrome", "chrom"), 1)    # deletion
        self.assertEqual(damerau_levenshtein("chrome", "chromee"), 1)  # insertion
        self.assertEqual(damerau_levenshtein("chrome", "chrone"), 1)   # substitution

    def test_transposition_counts_once_not_twice(self):
        """The reason this is Damerau and not plain Levenshtein."""
        self.assertEqual(damerau_levenshtein("ca", "ac"), 1)

    def test_true_damerau_beats_the_restricted_variant(self):
        # OSA (adjacent-only, single pass) reports 3 here; the true distance is 2.
        self.assertEqual(damerau_levenshtein("ca", "abc"), 2)

    def test_empty_and_lengths(self):
        self.assertEqual(damerau_levenshtein("", "abc"), 3)
        self.assertEqual(damerau_levenshtein("abc", ""), 3)
        self.assertEqual(damerau_levenshtein("", ""), 0)

    def test_symmetry(self):
        for a, b in (("chorme", "chrome"), ("visual studio", "visul studio"), ("abc", "xyz")):
            self.assertEqual(damerau_levenshtein(a, b), damerau_levenshtein(b, a))

    def test_triangle_inequality(self):
        # A distance function that violates this is not a metric, and the
        # bucketing argument below silently assumes one.
        for a, b, c in (("chrome", "chorme", "chrom"), ("abc", "abd", "abe")):
            self.assertLessEqual(
                damerau_levenshtein(a, c),
                damerau_levenshtein(a, b) + damerau_levenshtein(b, c),
            )


class PhoneticTests(unittest.TestCase):
    def test_soundex_known_values(self):
        self.assertEqual(soundex("Robert"), "R163")
        self.assertEqual(soundex("Rupert"), "R163")
        self.assertEqual(soundex("Ashcraft"), "A261")
        self.assertEqual(soundex("Tymczak"), "T522")
        self.assertEqual(soundex(""), "")

    def test_soundex_collapses_the_way_names_do(self):
        self.assertEqual(soundex("Google"), soundex("Gogle"))
        self.assertNotEqual(soundex("Google"), soundex("Gargle"))

    def test_metaphone_handles_the_english_digraphs(self):
        self.assertEqual(metaphone("phone"), metaphone("fone"))
        self.assertEqual(metaphone("knight"), metaphone("nite"))
        # 'ch' and 'k' are NOT the same sound, and must not collapse.
        self.assertNotEqual(metaphone("chrome"), metaphone("krome"))

    def test_metaphone_drops_vowels_but_keeps_the_first(self):
        self.assertEqual(metaphone("viber"), metaphone("vyber"))
        self.assertTrue(metaphone("excel").startswith("e"))

    def test_phonetic_key_is_bounded_and_stable(self):
        for word in ("chrome", "viber", "whatsapp", "x", ""):
            self.assertLessEqual(len(phonetic_key(word)), 4)


class ScoreTests(unittest.TestCase):
    def test_exact_beats_everything(self):
        # The full name is a perfect match; a single word of it is strong but
        # deliberately not perfect, so an exact hit can outrank it.
        self.assertEqual(match_score("google chrome", "Google Chrome"), 1.0)
        self.assertEqual(match_score("whatsapp", "WhatsApp"), 1.0)
        self.assertLess(match_score("chrome", "Google Chrome"), 1.0)
        self.assertGreater(match_score("chrome", "Google Chrome"), 0.85)

    def test_spacing_is_irrelevant_for_exact_names(self):
        self.assertEqual(match_score("whats app", "WhatsApp"), 1.0)

    def test_scores_are_ordered_sensibly(self):
        exact = match_score("chrome", "Google Chrome")
        prefix = match_score("chrom", "Google Chrome")
        typo = match_score("chorme", "Google Chrome")
        unrelated = match_score("chrome", "Microsoft Excel")
        self.assertGreaterEqual(exact, prefix)
        self.assertGreater(prefix, unrelated)
        self.assertGreater(typo, unrelated, "a typo must beat an unrelated name")

    def test_unrelated_names_score_zero_or_near_it(self):
        self.assertLess(match_score("blah", "Microsoft Excel"), 0.5)

    def test_aliases_are_honoured(self):
        self.assertEqual(match_score("teams", "Microsoft Teams", aliases=("teams",)), 1.0)
        self.assertEqual(match_score("ms teams", "Microsoft Teams", aliases=("ms teams",)), 1.0)

    def test_score_is_bounded(self):
        for spoken in MISHEARD:
            for app in APPS:
                self.assertGreaterEqual(match_score(spoken[0], app), 0.0)
                self.assertLessEqual(match_score(spoken[0], app), 1.0)


class IndexAccuracyTests(unittest.TestCase):
    def setUp(self):
        self.index = FuzzyIndex(APPS)

    def test_top_one_accuracy_on_the_fixture(self):
        index = FuzzyIndex(APPS)
        hits, misses = 0, []
        for spoken, expected in MISHEARD:
            results = index.query(spoken, limit=3, threshold=0.5)
            got = results[0][1] if results else None
            if got == expected:
                hits += 1
            else:
                misses.append(f"{spoken!r} -> {got!r} (wanted {expected!r})")
        self.assertEqual(misses, [], f"top-1 {hits}/{len(MISHEARD)}")
        self.assertEqual(hits, len(MISHEARD))

    def test_junk_matches_nothing(self):
        index = FuzzyIndex(APPS)
        for junk in JUNK:
            with self.subTest(junk=junk):
                self.assertEqual(index.query(junk, limit=3, threshold=0.5), [])

    def test_results_are_ranked(self):
        results = FuzzyIndex(APPS).query("chrome", limit=5, threshold=0.4)
        scores = [score for score, _ in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_limit_and_threshold_are_respected(self):
        index = FuzzyIndex(APPS)
        self.assertLessEqual(len(index.query("a", limit=2, threshold=0.0)), 2)
        self.assertTrue(all(score >= 0.9 for score, _ in index.query("chrome", threshold=0.9)))

    def test_aliases_and_weights_survive_indexing(self):
        index = FuzzyIndex(
            [("Microsoft Teams", ("teams", "msteams")), ("Slack", ())],
            name_of=lambda item: item[0],
            aliases_of=lambda item: item[1],
        )
        self.assertEqual(index.query("teams")[0][1][0], "Microsoft Teams")

    def test_a_large_index_stays_fast(self):
        """The resolver runs on the path a user waits on."""
        apps = [f"Program Number {i} Edition" for i in range(600)] + APPS
        index = FuzzyIndex(apps)
        start = time.perf_counter()
        for spoken, _expected in MISHEARD:
            index.query(spoken, limit=3, threshold=0.5)
        elapsed_ms = (time.perf_counter() - start) * 1000 / len(MISHEARD)
        self.assertLess(elapsed_ms, 40.0, f"{elapsed_ms:.1f} ms per query on 600 candidates")

    def test_len_and_empty_index(self):
        self.assertEqual(len(FuzzyIndex([])), 0)
        self.assertEqual(FuzzyIndex([]).query("chrome"), [])
        self.assertEqual(len(self.index), len(APPS))


class NormaliseTests(unittest.TestCase):
    def test_accents_and_case(self):
        self.assertEqual(normalise("Süper Café"), "super cafe")

    def test_punctuation_collapses(self):
        self.assertEqual(normalise("Chrome!!!"), "chrome")
        self.assertEqual(normalise("  Windows   Terminal  "), "windows terminal")

    def test_similarity_is_bounded(self):
        for a, b in (("abc", "abc"), ("abc", ""), ("", ""), ("chrome", "excel")):
            value = similarity(a, b)
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)


if __name__ == "__main__":
    unittest.main()


class IndexCostTests(unittest.TestCase):
    """The index runs before the user hears an answer, so its cost is a feature.

    The first version normalised every candidate on every query: 11.7 ms per
    utterance against 600 names. Gating on bigrams took it to ~0.3 ms. This test
    exists so a future "harmless" extra tier cannot quietly give that back.
    """

    def test_a_query_against_a_large_index_stays_cheap(self):
        import time

        from core.fuzzy import FuzzyIndex

        names = [f"Program Number {i} Edition" for i in range(580)] + [
            "WhatsApp", "Google Chrome", "Microsoft PowerPoint", "Notepad",
        ]
        index = FuzzyIndex(names)
        spoken = ["whats app", "chorme", "ppt", "note pad", "vscode"]

        for phrase in spoken:                       # warm the branch predictor
            index.query(phrase, limit=1)

        start = time.perf_counter()
        rounds = 20
        for _ in range(rounds):
            for phrase in spoken:
                index.query(phrase, limit=1)
        per_query_ms = (time.perf_counter() - start) * 1000 / (rounds * len(spoken))
        self.assertLess(per_query_ms, 2.0, f"{per_query_ms:.2f} ms per query")

    def test_the_gate_does_not_lose_the_matches_it_protects(self):
        from core.fuzzy import FuzzyIndex

        index = FuzzyIndex([f"Program Number {i} Edition" for i in range(200)] + [
            "WhatsApp", "Google Chrome", "Microsoft PowerPoint", "Notepad",
        ])
        for spoken, expected in (
            ("whats app", "WhatsApp"),
            ("chorme", "Google Chrome"),
            ("ppt", "Microsoft PowerPoint"),
            ("note pad", "Notepad"),
        ):
            with self.subTest(spoken=spoken):
                results = index.query(spoken, limit=1)
                self.assertTrue(results)
                self.assertEqual(results[0][1], expected)


class ResolverIntegrationTests(unittest.TestCase):
    """The matcher, through the resolver that actually opens applications.

    This is the bug the whole module exists for: "open whatsapp" must not fall
    through to the path matcher just because speech recognition produced
    "what's up".
    """

    def _resolver(self):
        from core import app_resolver

        apps = [
            app_resolver.App(name="WhatsApp", target=r"C:\Apps\WhatsApp.exe", source="start menu"),
            app_resolver.App(name="Google Chrome", target=r"C:\Apps\chrome.exe", source="start menu"),
            app_resolver.App(name="Notepad", target=r"C:\Windows\notepad.exe", source="start menu"),
        ]
        app_resolver.clear_cache()
        return app_resolver, app_resolver.Backends(
            scheme_handler=lambda scheme: None,
            installed=lambda: list(apps),
            running_labels=list,
            is_directory=lambda target: False,
        )

    def test_a_mispronounced_name_resolves(self):
        app_resolver, backends = self._resolver()
        for spoken, expected in (
            ("what's up", "WhatsApp"),
            ("whats app", "WhatsApp"),
            ("chorme", "Google Chrome"),
        ):
            with self.subTest(spoken=spoken):
                result = app_resolver.resolve(spoken, backends)
                self.assertTrue(result.ok, result.reason)
                self.assertEqual(result.name, expected)

    def test_a_directory_is_still_rejected(self):
        """The fuzzy tier must not resurrect the folder bug it was added next to."""
        from core import app_resolver

        app_resolver.clear_cache()
        folder = app_resolver.App(name="WhatsApp", target=r"C:\Users\me\Desktop\WhatsApp")
        backends = app_resolver.Backends(
            scheme_handler=lambda scheme: None,
            installed=lambda: [folder],
            running_labels=list,
            is_directory=lambda target: True,
        )
        self.assertFalse(app_resolver.resolve("whats app", backends).ok)

    def test_junk_still_does_not_resolve(self):
        from core import app_resolver

        app_resolver.clear_cache()
        backends = app_resolver.Backends(
            scheme_handler=lambda scheme: None,
            installed=lambda: [app_resolver.App("Notepad", r"C:\notepad.exe")],
            running_labels=list,
            is_directory=lambda target: False,
        )
        self.assertFalse(app_resolver.resolve("qqqq zzzz", backends).ok)
