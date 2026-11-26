"""Every Gemini client the program builds says which API version it wants.

The fault, measured on 2026-11-26 with the line `core.gemini.client()` used to run:

    genai.Client(api_key=..., http_options=HttpOptions(timeout=...))

    google-genai 2.34.0 (what CI installs; requirements.txt allows >=2.8.0,<3)  ->  v1beta
    google-genai 3.6.1  (what Dependabot's pull request #41 would allow)        ->  v1

When the code does not name a version, the library picks one, and its maker may change the
pick. Google's notes for 3.0.0 say so: the default moved from `v1beta` to `v1`, and the
`-latest` model names, some `-preview` models and the Live API exist only on `v1beta`. The
Live session in `main.py` and the one-shot Live turn in `core/gemini.py` already named
`v1beta`. The third client, `core.gemini.client()` (every REST call goes through it), did
not. A library update would have moved it without a word, and nothing in this suite makes a
call to Google that could have shown it.

Two checks, both red on the old code:

1. the text client hands `v1beta` to the library (checked on the arguments it passes, so it
   is red on any library version, not only on the one that changed its mind);
2. no client in the program's own code is built without naming a version, so a new one added
   later cannot repeat the gap.

What these cannot show: that the live service answers on `v1beta` (it does today; that is a
call to Google, which only the owner's key can make).
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from unittest import mock

from core import gemini
from core.lazyimport import installed

ROOT = Path(__file__).resolve().parents[1]
CLIENTS_WE_KNOW_OF = 3  # main.py (Live session), core/gemini.py (REST client, one-shot Live turn)


def names_for_genai(tree: ast.AST) -> set[str]:
    """The names a file uses for the `google.genai` module: an import, or a LazyModule."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "google":
            names.update(alias.asname or alias.name for alias in node.names if alias.name == "genai")
        elif isinstance(node, ast.Import):
            names.update(alias.asname for alias in node.names
                         if alias.name == "google.genai" and alias.asname)
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value
            if (getattr(call.func, "id", "") == "LazyModule" and call.args
                    and isinstance(call.args[0], ast.Constant) and call.args[0].value == "google.genai"):
                names.update(target.id for target in node.targets if isinstance(target, ast.Name))
    return names


def client_calls(path: Path):
    """Every `<genai>.Client(...)` call in one file."""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    names = names_for_genai(tree)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "Client" and isinstance(node.func.value, ast.Name)
                and node.func.value.id in names):
            yield node


def names_a_version(call: ast.Call) -> bool:
    """Does `http_options` say `api_version` where the reader can see it? A variable, or
    `**options`, is not an answer: the check cannot tell, so it says no."""
    for keyword in call.keywords:
        if keyword.arg != "http_options":
            continue
        value = keyword.value
        if isinstance(value, ast.Dict):
            return any(isinstance(key, ast.Constant) and key.value == "api_version" for key in value.keys)
        if isinstance(value, ast.Call):
            return any(inner.arg == "api_version" for inner in value.keywords)
    return False


@unittest.skipUnless(installed("google.genai"), "google-genai is not installed here")
class TheTextClientAsksForV1beta(unittest.TestCase):
    def test_client_hands_the_version_to_the_library(self):
        with mock.patch("google.genai.Client") as build:
            gemini.client(key="a-key")
        options = build.call_args.kwargs["http_options"]
        version = options.get("api_version") if isinstance(options, dict) else getattr(options, "api_version", None)
        self.assertEqual(version, "v1beta",
                         "core.gemini.client() must name its API version; the library's own default "
                         "is v1beta in 2.x and v1 in 3.x")

    def test_the_timeout_is_still_there(self):
        # The fix touches the same argument. It must not cost the deadline the API insists on.
        with mock.patch("google.genai.Client") as build:
            gemini.client(timeout_ms=45_000, key="a-key")
        options = build.call_args.kwargs["http_options"]
        timeout = options.get("timeout") if isinstance(options, dict) else getattr(options, "timeout", None)
        self.assertEqual(timeout, 45_000)


class NoClientIsBuiltWithoutAVersion(unittest.TestCase):
    def test_every_client_in_the_programs_own_code_names_one(self):
        from tests.test_source_hygiene import python_files

        sites, unnamed = [], []
        for path in python_files():
            for call in client_calls(path):
                where = f"{path.relative_to(ROOT).as_posix()}:{call.lineno}"
                sites.append(where)
                if not names_a_version(call):
                    unnamed.append(where)
        self.assertGreaterEqual(
            len(sites), CLIENTS_WE_KNOW_OF,
            f"found only {sites}; the scan has gone blind (a renamed import?). Fix the scan, "
            "not the number, or this check passes on nothing")
        self.assertEqual(
            unnamed, [],
            "a Gemini client is built without `api_version` in its http_options. Name one "
            "(core.gemini.API_VERSION), as the library's default may change with an update")


if __name__ == "__main__":
    unittest.main()
