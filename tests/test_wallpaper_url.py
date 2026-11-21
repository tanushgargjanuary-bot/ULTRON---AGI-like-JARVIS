"""`desktop_control wallpaper_url` downloads a picture from the public web, and only that.

The action used to give its address to `urllib.request.urlretrieve`, which opens anything it is
handed. The model chooses the address, and the model reads web pages and files that other people
write, so an address in a page could make this machine:

* copy any file the owner can read: `file:///C:/Users/owner/Documents/passwords.txt`;
* call a device on the home network (`http://192.168.1.1/...`, a printer, a camera, a router
  page that acts on a plain GET) or a cloud metadata address (`http://169.254.169.254/...`);
* be redirected there by a public address that answers 302.

The policy table treats `wallpaper_url` as routine (no confirmation), which is fine for a picture
from the web and not for those. Now the download goes through the same checks the page reader
uses (`actions/web_read.py`), and what comes back has to be an image. Nothing here touches the
network: `_request_once` is replaced, or a fake connection stands in for the socket.
"""

from __future__ import annotations

import socket
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from actions import desktop, web_read

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _picture(kind: str = "image/jpeg", body: bytes = JPEG):
    return (200, {"content-type": kind}, body)


class _Recorder:
    """Stand in for `set_wallpaper`: remember the file it was given, and what was in it."""

    def __init__(self, answer: str = "done"):
        self.paths: list[Path] = []
        self.contents: list[bytes] = []
        self.answer = answer

    def __call__(self, path: str) -> str:
        self.paths.append(Path(path))
        self.contents.append(Path(path).read_bytes())
        return self.answer


class WhatIsRefusedBeforeAnythingIsOpened(unittest.TestCase):
    BAD = {
        "a local file": "file:///etc/passwd",
        "a local file, Windows style": "file:///C:/Users/owner/Documents/passwords.txt",
        "ftp": "ftp://example.com/pic.jpg",
        "a data address": "data:image/png;base64,AAAA",
        "localhost": "http://localhost/pic.jpg",
        "the loopback address": "http://127.0.0.1/pic.jpg",
        "loopback in a longer spelling": "http://127.1/pic.jpg",
        "loopback as a number": "http://2130706433/pic.jpg",
        "the IPv6 loopback": "http://[::1]/pic.jpg",
        "a home-network address": "http://192.168.1.1/pic.jpg",
        "a 10.x address": "http://10.0.0.5/pic.jpg",
        "a 172.16 address": "http://172.16.4.4/pic.jpg",
        "the cloud metadata address": "http://169.254.169.254/latest/meta-data/",
        "a .local name": "https://printer.local/pic.jpg",
        "a .internal name": "https://metadata.google.internal/pic.jpg",
        "credentials in the address": "https://user:secret@example.com/pic.jpg",
        "a non-standard port": "https://example.com:8443/pic.jpg",
        "a port on a public host that is not the web": "http://example.com:22/pic.jpg",
        "no hostname": "https:///pic.jpg",
    }

    def test_each_is_refused_before_any_connection_is_made_and_nothing_is_set(self):
        # Both of the reader's checks run for real here (the address as written, then the address
        # the name resolves to); only the sockets are faked, so a connection would show up.
        # `127.1` and `2130706433` get past the first check, which reads only dotted quads, and are
        # stopped by the second, which asks the resolver what they mean. Numeric names resolve
        # without a network, so this needs none.
        for name, url in self.BAD.items():
            with self.subTest(name), \
                 mock.patch.object(web_read, "_PinnedHTTPConnection") as plain, \
                 mock.patch.object(web_read, "_PinnedHTTPSConnection") as secure, \
                 mock.patch.object(urllib.request, "urlretrieve") as retrieve, \
                 mock.patch.object(urllib.request, "urlopen") as opened, \
                 mock.patch.object(desktop, "set_wallpaper") as setter:
                answer = desktop.set_wallpaper_from_url(url)
                self.assertIn("could not be downloaded", answer, f"{name}: {answer}")
                plain.assert_not_called()
                secure.assert_not_called()
                retrieve.assert_not_called()
                opened.assert_not_called()
                setter.assert_not_called()

    def test_the_short_and_numeric_spellings_of_loopback_are_the_second_checks_catch(self):
        for url in ("http://127.1/pic.jpg", "http://2130706433/pic.jpg", "http://0x7f.0.0.1/pic.jpg"):
            with self.subTest(url), mock.patch.object(web_read, "_PinnedHTTPConnection") as plain:
                answer = desktop.set_wallpaper_from_url(url)
                plain.assert_not_called()
                self.assertIn("could not be downloaded", answer)

    def test_a_local_file_is_not_copied_to_a_temporary_one(self):
        # The old code read this file and wrote a copy of it, which `set_wallpaper` then received.
        with tempfile.TemporaryDirectory() as folder:
            secret = Path(folder) / "secret.png"
            secret.write_bytes(b"MY-PRIVATE-NOTES")
            seen = _Recorder()
            with mock.patch.object(desktop, "set_wallpaper", seen):
                answer = desktop.set_wallpaper_from_url(secret.as_uri())
            self.assertEqual(seen.paths, [], "a local file reached the wallpaper setter")
            self.assertIn("could not be downloaded", answer)

    def test_the_reason_is_in_the_answer_so_it_can_be_said_aloud(self):
        with mock.patch.object(desktop, "set_wallpaper"):
            answer = desktop.set_wallpaper_from_url("http://192.168.1.1/pic.jpg")
        self.assertIn("Private", answer)

    def test_an_empty_or_missing_address_is_a_failure_not_a_traceback(self):
        for url in ("", "   ", None):
            with self.subTest(url=url), mock.patch.object(desktop, "set_wallpaper") as setter:
                self.assertIn("could not be downloaded", desktop.set_wallpaper_from_url(url))
                setter.assert_not_called()


class WhatIsFollowed(unittest.TestCase):
    def test_a_redirect_to_a_private_address_is_refused_and_nothing_is_set(self):
        responses = [(302, {"location": "http://127.0.0.1/admin"}, b"")]
        with mock.patch.object(web_read, "_request_once", side_effect=responses) as request, \
             mock.patch.object(desktop, "set_wallpaper") as setter:
            answer = desktop.set_wallpaper_from_url("https://example.com/pic.jpg")
        self.assertIn("could not be downloaded", answer)
        self.assertIn("Private", answer)
        self.assertEqual(request.call_count, 1, "the private address was requested")
        setter.assert_not_called()

    def test_a_redirect_to_a_local_file_is_refused(self):
        responses = [(301, {"location": "file:///etc/passwd"}, b"")]
        with mock.patch.object(web_read, "_request_once", side_effect=responses), \
             mock.patch.object(desktop, "set_wallpaper") as setter:
            answer = desktop.set_wallpaper_from_url("https://example.com/pic.jpg")
        self.assertIn("could not be downloaded", answer)
        setter.assert_not_called()

    def test_a_redirect_to_another_public_address_is_followed(self):
        responses = [(302, {"location": "https://cdn.example.net/real.jpg"}, b""), _picture()]
        seen = _Recorder("Wallpaper set")
        with mock.patch.object(web_read, "_request_once", side_effect=responses) as request, \
             mock.patch.object(desktop, "set_wallpaper", seen):
            answer = desktop.set_wallpaper_from_url("https://example.com/pic")
        self.assertEqual(answer, "Wallpaper set")
        self.assertEqual(request.call_args_list[1].args[0], "https://cdn.example.net/real.jpg")

    def test_a_relative_redirect_is_resolved_against_the_address_that_sent_it(self):
        responses = [(302, {"location": "/images/real.png"}, b""), _picture("image/png", PNG)]
        seen = _Recorder("Wallpaper set")
        with mock.patch.object(web_read, "_request_once", side_effect=responses) as request, \
             mock.patch.object(desktop, "set_wallpaper", seen):
            desktop.set_wallpaper_from_url("https://example.com/start")
        self.assertEqual(request.call_args_list[1].args[0], "https://example.com/images/real.png")

    def test_a_loop_of_redirects_ends(self):
        forever = (302, {"location": "https://example.com/again"}, b"")
        with mock.patch.object(web_read, "_request_once", return_value=forever) as request, \
             mock.patch.object(desktop, "set_wallpaper") as setter:
            answer = desktop.set_wallpaper_from_url("https://example.com/start")
        self.assertIn("redirected too many times", answer)
        self.assertEqual(request.call_count, web_read.MAX_REDIRECTS + 1)
        setter.assert_not_called()

    def test_a_redirect_with_nowhere_to_go_is_reported(self):
        with mock.patch.object(web_read, "_request_once", return_value=(302, {}, b"")), \
             mock.patch.object(desktop, "set_wallpaper") as setter:
            answer = desktop.set_wallpaper_from_url("https://example.com/pic.jpg")
        self.assertIn("without a redirect target", answer)
        setter.assert_not_called()

    def test_an_error_status_is_reported_with_its_number(self):
        for status in (403, 404, 500):
            with self.subTest(status=status), \
                 mock.patch.object(web_read, "_request_once", return_value=(status, {}, b"")), \
                 mock.patch.object(desktop, "set_wallpaper") as setter:
                answer = desktop.set_wallpaper_from_url("https://example.com/pic.jpg")
                self.assertIn(str(status), answer)
                setter.assert_not_called()

    def test_robots_txt_is_not_consulted_for_a_picture_the_owner_named(self):
        with mock.patch.object(web_read, "_request_once", return_value=_picture()) as request, \
             mock.patch.object(web_read, "_robots_allowed", side_effect=AssertionError("robots.txt was read")), \
             mock.patch.object(desktop, "set_wallpaper", _Recorder("Wallpaper set")):
            desktop.set_wallpaper_from_url("https://example.com/pic.jpg")
        self.assertEqual(request.call_count, 1)

    def test_the_request_asks_for_an_image_and_allows_a_big_one(self):
        with mock.patch.object(web_read, "_request_once", return_value=_picture()) as request, \
             mock.patch.object(desktop, "set_wallpaper", _Recorder("Wallpaper set")):
            desktop.set_wallpaper_from_url("https://example.com/pic.jpg")
        self.assertEqual(request.call_args.kwargs["accept"], "image/*")
        self.assertEqual(request.call_args.kwargs["max_bytes"], desktop.MAX_WALLPAPER_BYTES)
        self.assertGreater(desktop.MAX_WALLPAPER_BYTES, web_read.MAX_BYTES,
                           "a picture is bigger than a page of text; the page reader's cap would refuse most")


class WhatIsSet(unittest.TestCase):
    def test_a_public_picture_is_saved_under_its_real_type_and_set(self):
        seen = _Recorder("Wallpaper set: x")
        with mock.patch.object(web_read, "_request_once", return_value=_picture("image/png", PNG)), \
             mock.patch.object(desktop, "set_wallpaper", seen):
            answer = desktop.set_wallpaper_from_url("https://example.com/download?id=7")
        self.assertEqual(answer, "Wallpaper set: x")
        self.assertEqual(len(seen.paths), 1)
        self.assertEqual(seen.paths[0].suffix, ".png", "the type the server reported decides, not the address")
        self.assertEqual(seen.contents, [PNG])

    def test_the_temporary_file_is_removed_after_a_success(self):
        seen = _Recorder("Wallpaper set")
        with mock.patch.object(web_read, "_request_once", return_value=_picture()), \
             mock.patch.object(desktop, "set_wallpaper", seen):
            desktop.set_wallpaper_from_url("https://example.com/pic.jpg")
        self.assertFalse(seen.paths[0].exists())

    def test_the_temporary_file_is_removed_when_setting_it_fails_too(self):
        seen = _Recorder("Could not set wallpaper: nope")
        with mock.patch.object(web_read, "_request_once", return_value=_picture()), \
             mock.patch.object(desktop, "set_wallpaper", seen):
            answer = desktop.set_wallpaper_from_url("https://example.com/pic.jpg")
        self.assertIn("Could not set wallpaper", answer)
        self.assertFalse(seen.paths[0].exists())

    def test_the_temporary_file_is_removed_when_the_setter_raises(self):
        paths = []

        def boom(path):
            paths.append(Path(path))
            raise RuntimeError("the desktop fell over")

        with mock.patch.object(web_read, "_request_once", return_value=_picture()), \
             mock.patch.object(desktop, "set_wallpaper", boom):
            answer = desktop.set_wallpaper_from_url("https://example.com/pic.jpg")
        self.assertIn("could not be downloaded", answer)
        self.assertFalse(paths[0].exists())

    def test_a_file_that_cannot_be_removed_does_not_turn_a_success_into_an_error(self):
        # Windows can hold a wallpaper file for a moment after it was set; the old code ignored that.
        with mock.patch.object(web_read, "_request_once", return_value=_picture()), \
             mock.patch.object(desktop, "set_wallpaper", _Recorder("Wallpaper set")), \
             mock.patch.object(Path, "unlink", side_effect=PermissionError("in use")):
            answer = desktop.set_wallpaper_from_url("https://example.com/pic.jpg")
        self.assertEqual(answer, "Wallpaper set")

    def test_a_server_that_says_octet_stream_is_believed_when_the_address_names_an_image(self):
        seen = _Recorder("Wallpaper set")
        reply = (200, {"content-type": "application/octet-stream"}, JPEG)
        with mock.patch.object(web_read, "_request_once", return_value=reply), \
             mock.patch.object(desktop, "set_wallpaper", seen):
            desktop.set_wallpaper_from_url("https://example.com/files/sunset.jpeg")
        self.assertEqual(seen.paths[0].suffix, ".jpeg")


class WhatIsNotAPicture(unittest.TestCase):
    def test_a_web_page_is_refused_and_leaves_no_file(self):
        before = set(Path(tempfile.gettempdir()).glob("tmp*.html"))
        reply = (200, {"content-type": "text/html; charset=utf-8"}, b"<html>sign in</html>")
        with mock.patch.object(web_read, "_request_once", return_value=reply), \
             mock.patch.object(desktop, "set_wallpaper") as setter:
            answer = desktop.set_wallpaper_from_url("https://example.com/pic.jpg")
        self.assertIn("not a picture format", answer)
        self.assertIn("text/html", answer)
        setter.assert_not_called()
        self.assertEqual(set(Path(tempfile.gettempdir()).glob("tmp*.html")), before)

    def test_octet_stream_at_an_address_with_no_image_suffix_is_refused(self):
        reply = (200, {"content-type": "application/octet-stream"}, b"MZ....")
        with mock.patch.object(web_read, "_request_once", return_value=reply), \
             mock.patch.object(desktop, "set_wallpaper") as setter:
            answer = desktop.set_wallpaper_from_url("https://example.com/setup.exe")
        self.assertIn("could not be downloaded", answer)
        setter.assert_not_called()

    def test_a_vector_image_cannot_be_a_wallpaper(self):
        reply = (200, {"content-type": "image/svg+xml"}, b"<svg/>")
        with mock.patch.object(web_read, "_request_once", return_value=reply), \
             mock.patch.object(desktop, "set_wallpaper") as setter:
            answer = desktop.set_wallpaper_from_url("https://example.com/logo.svg")
        self.assertIn("image/svg+xml", answer)
        setter.assert_not_called()

    def test_no_content_type_at_all_is_not_trusted_as_a_picture(self):
        with mock.patch.object(web_read, "_request_once", return_value=(200, {}, b"?")), \
             mock.patch.object(desktop, "set_wallpaper") as setter:
            answer = desktop.set_wallpaper_from_url("https://example.com/thing")
        self.assertIn("unknown type", answer)
        setter.assert_not_called()


class TheSizeCap(unittest.TestCase):
    """`_request_once` with a fake connection: no socket, no DNS."""

    def _fake(self, body_bytes: int, sent: list):
        class Response:
            status = 200

            def getheaders(self):
                return [("Content-Type", "image/jpeg")]

            def read(self, amount=None):
                return b"x" * min(body_bytes, amount if amount is not None else body_bytes)

        class Connection:
            def __init__(self, host, port, address, timeout):
                self.address = address

            def request(self, method, target, headers=None):
                sent.append((method, target, dict(headers or {})))

            def getresponse(self):
                return Response()

            def close(self):
                pass

        return Connection

    def test_a_download_over_the_cap_is_refused_in_words(self):
        sent: list = []
        with mock.patch.object(web_read, "_public_address", return_value="93.184.216.34"), \
             mock.patch.object(web_read, "_PinnedHTTPSConnection", self._fake(5000, sent)):
            with self.assertRaisesRegex(ValueError, r"The file exceeds the 0\.001 MB read limit"):
                web_read._request_once("https://example.com/p.jpg", accept="image/*", max_bytes=1000)

    def test_a_download_at_the_cap_is_accepted(self):
        sent: list = []
        with mock.patch.object(web_read, "_public_address", return_value="93.184.216.34"), \
             mock.patch.object(web_read, "_PinnedHTTPSConnection", self._fake(1000, sent)):
            status, headers, body = web_read._request_once("https://example.com/p.jpg", accept="image/*",
                                                           max_bytes=1000)
        self.assertEqual((status, len(body)), (200, 1000))
        self.assertEqual(sent[0][2]["Accept"], "image/*")

    def test_the_connection_goes_to_the_address_that_was_checked(self):
        # Pinning: the name is resolved once, here, and the socket is opened to that address.
        seen = []

        class Spy:
            def __init__(self, host, port, address, timeout):
                seen.append(address)

            def request(self, *a, **k):
                pass

            def getresponse(self):
                class R:
                    status = 200

                    def getheaders(self):
                        return []

                    def read(self, n=None):
                        return b""

                return R()

            def close(self):
                pass

        with mock.patch.object(socket, "getaddrinfo",
                        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]), \
             mock.patch.object(web_read, "_PinnedHTTPSConnection", Spy):
            web_read._request_once("https://example.com/p.jpg")
        self.assertEqual(seen, ["93.184.216.34"])

    def test_a_name_that_resolves_to_a_private_address_is_refused_before_a_connection(self):
        with mock.patch.object(socket, "getaddrinfo",
                        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.0.9", 443))]), \
             mock.patch.object(web_read, "_PinnedHTTPSConnection") as connection:
            answer = None
            with mock.patch.object(desktop, "set_wallpaper") as setter:
                answer = desktop.set_wallpaper_from_url("https://rebinding.example.com/p.jpg")
        self.assertIn("could not be downloaded", answer)
        connection.assert_not_called()
        setter.assert_not_called()


class ThePageReaderIsUnchanged(unittest.TestCase):
    """`_request_once` gained two optional arguments. With neither, it is what it was."""

    def test_the_default_accept_header_is_the_html_one(self):
        sent: list = []

        class Response:
            status = 200

            def getheaders(self):
                return []

            def read(self, amount=None):
                return b"hi"

        class Connection:
            def __init__(self, host, port, address, timeout):
                pass

            def request(self, method, target, headers=None):
                sent.append(dict(headers or {}))

            def getresponse(self):
                return Response()

            def close(self):
                pass

        with mock.patch.object(web_read, "_public_address", return_value="93.184.216.34"), \
             mock.patch.object(web_read, "_PinnedHTTPSConnection", Connection):
            web_read._request_once("https://example.com/")
        self.assertEqual(sent[0]["Accept"], "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1")
        self.assertEqual(sent[0]["Accept-Encoding"], "identity")

    def test_the_page_limit_message_still_says_page_and_2_mb(self):
        class Response:
            status = 200

            def getheaders(self):
                return []

            def read(self, amount=None):
                return b"x" * (amount or 0)

        class Connection:
            def __init__(self, *args):
                pass

            def request(self, *args, **kwargs):
                pass

            def getresponse(self):
                return Response()

            def close(self):
                pass

        with mock.patch.object(web_read, "_public_address", return_value="93.184.216.34"), \
             mock.patch.object(web_read, "_PinnedHTTPSConnection", Connection):
            with self.assertRaisesRegex(ValueError, r"The page exceeds the 2 MB read limit\."):
                web_read._request_once("https://example.com/")


class TheToolSaysWhatItAccepts(unittest.TestCase):
    def test_the_url_parameter_says_public_and_not_a_local_file(self):
        text = desktop.TOOL["parameters"]["properties"]["url"]["description"]
        self.assertIn("Public", text)
        self.assertIn("never a local file", text)


if __name__ == "__main__":
    unittest.main()
