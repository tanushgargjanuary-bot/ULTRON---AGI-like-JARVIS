"""Static checks for the remote dashboard's selectable interface variants."""

from __future__ import annotations

import re
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "dashboard" / "static" / "app.html"
LOGIN = ROOT / "dashboard" / "static" / "login.html"
VARIANTS = {"command", "citadel", "sentinel", "core", "terminal", "nexus"}


class _IdsAndVariants(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.duplicates: set[str] = set()
        self.options: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        element_id = values.get("id")
        if element_id:
            if element_id in self.ids:
                self.duplicates.add(element_id)
            self.ids.add(element_id)
        classes = (values.get("class") or "").split()
        variant = values.get("data-ui")
        if tag == "button" and "variant-option" in classes and variant:
            self.options.add(variant)


class DashboardUIVariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.read_text(encoding="utf-8")
        cls.login = LOGIN.read_text(encoding="utf-8")
        cls.app_parser = _IdsAndVariants()
        cls.app_parser.feed(cls.app)
        cls.login_parser = _IdsAndVariants()
        cls.login_parser.feed(cls.login)
        cls.css = cls.app.split("<style>", 1)[1].split("</style>", 1)[0]

    def test_six_distinct_layout_variants_are_offered_and_styled(self) -> None:
        self.assertEqual(self.app_parser.options, VARIANTS)
        for variant in VARIANTS - {"command"}:
            self.assertIn(f':root[data-ui="{variant}"] .workspace', self.css)
        self.assertIn("Command Bridge", self.app)
        self.assertIn("Tactical top-deck layout", self.app)
        self.assertIn("Right-side systems rail", self.app)
        self.assertIn("Orb-centered interface", self.app)
        self.assertIn("Dense operator console", self.app)
        self.assertIn("Modular systems board", self.app)

    def test_variant_choice_persists_and_is_applied_on_login(self) -> None:
        storage_key = "ultron_ui_variant"
        self.assertIn(storage_key, self.app)
        self.assertIn(storage_key, self.login)
        self.assertIn("localStorage.setItem(UI_VARIANT_STORAGE_KEY, variant)", self.app)
        self.assertIn("document.documentElement.dataset.ui = variant", self.app)
        self.assertIn("document.documentElement.dataset.ui = initialUiVariant", self.login)
        self.assertNotIn("ultron_ui_theme", self.app + self.login)

    def test_remote_controls_keep_their_dom_hooks_and_ids_are_unique(self) -> None:
        required = {
            "pill", "st", "enc", "wake", "feed", "inp", "file-inp", "mic-btn",
            "variant-toggle", "variant-menu", "variant-close", "variant-grid",
        }
        self.assertTrue(required.issubset(self.app_parser.ids))
        self.assertFalse(self.app_parser.duplicates)
        self.assertFalse(self.login_parser.duplicates)
        for path in (APP, LOGIN):
            text = path.read_text(encoding="utf-8")
            css = text.split("<style>", 1)[1].split("</style>", 1)[0]
            self.assertEqual(css.count("{"), css.count("}"), path.name)
            scripts = re.findall(r"<script>(.*?)</script>", text, flags=re.S)
            self.assertEqual(len(scripts), 2, path.name)


if __name__ == "__main__":
    unittest.main()
