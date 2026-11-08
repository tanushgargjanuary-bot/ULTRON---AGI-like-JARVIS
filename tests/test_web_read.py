"""The page reader refuses unsafe targets and extracts only bounded public text."""

import socket
import unittest
from unittest.mock import patch

from actions import web_read


class WebReadTests(unittest.TestCase):
    def test_url_requires_http_and_refuses_credentials_private_hosts_and_custom_ports(self):
        for url in (
            "file:///etc/passwd", "http://user:pass@example.com/", "http://localhost/",
            "https://host.local/private", "https://example.com:8443/",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                web_read._normalize_url(url)

    def test_bare_domain_defaults_to_https_and_ipv6_is_bracketed(self):
        self.assertEqual(web_read._normalize_url("example.com/a"), "https://example.com/a")
        self.assertTrue(web_read._normalize_url("https://[2606:4700:4700::1111]/").startswith("https://["))

    def test_dns_resolution_rejects_private_and_mixed_answers(self):
        with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.4", 443))]):
            with self.assertRaisesRegex(ValueError, "private"):
                web_read._public_address("example.com", 443)
        with patch("socket.getaddrinfo", return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ]):
            with self.assertRaisesRegex(ValueError, "private"):
                web_read._public_address("example.com", 443)

    def test_public_dns_returns_a_pinned_address(self):
        with patch("socket.getaddrinfo", return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
        ]):
            self.assertEqual(web_read._public_address("example.com", 443), "8.8.8.8")

    def test_html_extraction_removes_script_navigation_and_caps_text(self):
        title, text = web_read._extract_text(
            "text/html",
            b"<html><title>Public page</title><nav>menu</nav><main>Useful text<script>secret</script></main></html>",
            "utf-8",
        )
        self.assertEqual(title, "Public page")
        self.assertEqual(text, "Useful text")
        _, capped = web_read._extract_text("text/plain", b"x" * 15000, "utf-8")
        self.assertEqual(len(capped), web_read.MAX_CHARS)

    def test_robots_denial_stops_before_page_request(self):
        with patch.object(web_read, "_robots_allowed", return_value=(False, "blocked by robots")), \
             patch.object(web_read, "_request_once") as request:
            with self.assertRaisesRegex(PermissionError, "robots"):
                web_read._fetch_page("https://example.com/blocked")
        request.assert_not_called()

    def test_redirect_to_private_address_is_refused(self):
        with patch.object(web_read, "_robots_allowed", return_value=(True, "")), \
             patch.object(web_read, "_request_once", return_value=(302, {"location": "http://127.0.0.1/admin"}, b"")):
            with self.assertRaisesRegex(ValueError, "Private, local"):
                web_read._fetch_page("https://example.com/")

    def test_http_403_is_reported_without_bypass(self):
        with patch.object(web_read, "_robots_allowed", return_value=(True, "")), \
             patch.object(web_read, "_request_once", return_value=(403, {}, b"")):
            with self.assertRaisesRegex(PermissionError, "no bypass"):
                web_read._fetch_page("https://example.com/")

    def test_tool_returns_untrusted_marked_content(self):
        with patch.object(web_read, "_fetch_page", return_value=(
            "https://example.com/", "text/plain", b"hello", "utf-8"
        )):
            result = web_read.web_read({"url": "https://example.com/"})
        self.assertIn("UNTRUSTED", result)
        self.assertIn("hello", result)


if __name__ == "__main__":
    unittest.main()
