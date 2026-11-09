"""Dashboard network binding defaults and remote-access policy."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dashboard import server


class DashboardNetworkPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_base = server.BASE_DIR
        server.BASE_DIR = Path(self.temp.name)
        (Path(self.temp.name) / "config").mkdir()

    def tearDown(self):
        server.BASE_DIR = self.old_base
        self.temp.cleanup()

    def write_config(self, data):
        (Path(self.temp.name) / "config" / "api_keys.json").write_text(
            json.dumps(data), encoding="utf-8"
        )

    def test_default_is_loopback_only(self):
        dashboard = server.DashboardServer()
        self.assertFalse(dashboard._allow_lan())
        self.assertEqual(dashboard._bind_host(), "127.0.0.1")
        with patch.object(dashboard, "_ssl_enabled", return_value=False):
            self.assertEqual(dashboard.get_url(), "http://127.0.0.1:8000")

    def test_lan_binding_requires_explicit_boolean_true(self):
        for value in (None, False, "true", 1):
            self.write_config({"dashboard_allow_lan": value})
            self.assertFalse(server.DashboardServer._allow_lan())

    def test_explicit_lan_permission_binds_to_all_interfaces_only_with_tls(self):
        self.write_config({"dashboard_allow_lan": True, "dashboard_https": True})
        certs = Path(self.temp.name) / "config" / "certs"
        certs.mkdir()
        (certs / "jarvis.key").write_text("test-key", encoding="utf-8")
        (certs / "jarvis.crt").write_text("test-cert", encoding="utf-8")
        dashboard = server.DashboardServer()
        self.assertTrue(dashboard._allow_lan())
        self.assertEqual(dashboard._bind_host(), "0.0.0.0")
        self.assertEqual(dashboard._display_host(), dashboard._ip)
        self.assertTrue(dashboard.get_url().startswith("https://"))

    def test_local_https_url_uses_loopback_without_lan_permission(self):
        dashboard = server.DashboardServer()
        with patch.object(dashboard, "_ssl_enabled", return_value=True):
            self.assertEqual(dashboard.get_url(), "https://127.0.0.1:8001")


if __name__ == "__main__":
    unittest.main()
