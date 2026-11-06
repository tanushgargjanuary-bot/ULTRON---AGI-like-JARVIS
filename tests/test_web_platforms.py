"""tests/test_web_platforms.py — the web layer, with no network in the room.

Every test here runs against a fake opener, because a test that needs the
internet is a test that fails on a plane and passes for the wrong reason. The
fake lets the suite check the four things that actually break in production:
a missing network, a spent quota, an oversized body, and a token that leaks into
a cache file.
"""

from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import github, platforms, webapi


class FakeResponse:
    def __init__(self, body, status=200, headers=None):
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.status = status
        self.headers = headers or {}

    def read(self, size=-1):
        return self._body if size in (-1, None) else self._body[:size]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeWeb:
    """A stand-in for urlopen: (url) -> response, and it remembers the requests."""

    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def __call__(self, request, timeout=None):
        url = request.full_url
        self.requests.append({"url": url, "headers": dict(request.headers)})
        answer = self.routes.get(url, self.routes.get("*"))
        if isinstance(answer, Exception):
            raise answer
        if callable(answer):
            return answer(request)
        return answer

    def urls(self):
        return [row["url"] for row in self.requests]


class Base(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "cache.json"
        self.web = None

    def tearDown(self):
        webapi.set_opener(None)
        self.folder.cleanup()

    def serve(self, routes):
        routes = dict(routes)
        routes.setdefault("*", FakeResponse({}))   # an unmatched URL is an empty 200
        self.web = FakeWeb(routes)
        webapi.set_opener(self.web)
        return self.web


class Transport(Base):
    def test_json_is_read_and_the_etag_is_stored(self):
        self.serve({"https://example.test/a": FakeResponse(
            {"hello": "world"}, headers={"ETag": '"abc"', "Content-Length": "17"})})
        status, data, note = webapi.fetch_json("https://example.test/a",
                                               cache=webapi.Cache(self.path))
        self.assertEqual((status, data, note), (200, {"hello": "world"}, ""))
        self.assertEqual(json.loads(self.path.read_text())["https://example.test/a"]["etag"],
                         '"abc"')

    def test_a_second_question_costs_no_quota(self):
        cache = webapi.Cache(self.path)
        self.serve({"https://example.test/a": FakeResponse(
            {"n": 1}, headers={"ETag": '"abc"'})})
        webapi.fetch_json("https://example.test/a", cache=cache)
        webapi.set_opener(None)

        self.serve({"https://example.test/a": urllib.error.HTTPError(
            "https://example.test/a", 304, "Not Modified",
            {"ETag": '"abc"'}, None)})
        status, data, note = webapi.fetch_json("https://example.test/a", cache=cache)
        self.assertEqual(status, 304)
        self.assertEqual(data, {"n": 1})
        self.assertEqual(note, "")
        self.assertEqual(self.web.requests[0]["headers"].get("If-none-match"), '"abc"')

    def test_no_network_is_a_sentence(self):
        self.serve({"*": urllib.error.URLError("down")})
        status, data, note = webapi.fetch_json("https://example.test/a")
        self.assertEqual((status, data), (0, None))
        self.assertIn("no network connection", note)

    def test_a_spent_quota_says_when_it_resets(self):
        self.serve({"*": urllib.error.HTTPError(
            "u", 403, "Forbidden",
            {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1800000000"}, None)})
        status, data, note = webapi.fetch_json("https://example.test/a")
        self.assertEqual(status, 403)
        self.assertIn("quota is used up until", note)

    def test_an_oversized_answer_is_refused_not_truncated(self):
        big = b'{"x": "' + b"a" * (webapi.BODY_LIMIT + 10) + b'"}'
        self.serve({"*": FakeResponse(big)})
        status, data, note = webapi.fetch_json("https://example.test/a")
        self.assertEqual((status, data), (0, None))
        self.assertIn("larger than 2 MB", note)

    def test_a_compressed_answer_is_decompressed(self):
        self.serve({"*": FakeResponse(gzip.compress(json.dumps({"ok": 1}).encode()))})
        status, data, _note = webapi.fetch_json("https://example.test/a")
        self.assertEqual((status, data), (200, {"ok": 1}))

    def test_a_404_names_the_address(self):
        self.serve({"*": urllib.error.HTTPError("u", 404, "Not Found", {}, None)})
        _status, _data, note = webapi.fetch_json("https://example.test/a")
        self.assertIn("does not exist", note)


class GitHubReads(Base):
    def client(self, token="", routes=None):
        self.serve(routes or {})
        return github.GitHub(token, webapi.Cache(self.path))

    def test_trending_asks_a_real_search_question(self):
        client = self.client(routes={"*": FakeResponse({"items": [
            {"full_name": "acme/rocket", "description": "fast", "stargazers_count": 900,
             "language": "Rust", "html_url": "https://github.com/acme/rocket"}]})})
        result = client.trending(days=7, minimum_stars=50, language="rust", limit=3)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["data"]["items"][0]["full_name"], "acme/rocket")
        asked = self.web.urls()[0]
        for piece in ("search/repositories", "sort=stars", "created%3A%3E",
                      "stars%3A%3E49", "language%3Arust", "per_page=3"):
            self.assertIn(piece, asked)
        self.assertIn("no trending API", result["data"]["source"])

    def test_a_token_is_sent_when_present_and_absent_when_not(self):
        self.client(token="").trending()
        without = self.web.requests[0]["headers"]
        self.client(token="ghp_secret").trending()
        with_token = self.web.requests[0]["headers"]
        self.assertNotIn("Authorization", without)
        self.assertEqual(with_token.get("Authorization"), "Bearer ghp_secret")

    def test_the_token_never_reaches_the_cache_file(self):
        self.client(token="ghp_secret", routes={
            "*": FakeResponse({"items": []}, headers={"ETag": '"x"'})}).trending()
        self.assertNotIn("ghp_secret", self.path.read_text(encoding="utf-8"))

    def test_notifications_without_a_token_say_what_is_missing(self):
        result = github.GitHub("", None).notifications()
        self.assertFalse(result["ok"])
        self.assertIn("token", result["note"])

    def test_a_repository_needs_an_owner_and_a_name(self):
        result = self.client().repo("mark-lvi")
        self.assertFalse(result["ok"])
        self.assertIn("owner/name", result["note"])

    def test_a_repository_answer_is_summarised(self):
        client = self.client(routes={"*": FakeResponse({
            "full_name": "FatihMakes/Mark-LVI", "description": "a HUD assistant",
            "stargazers_count": 1200, "forks_count": 300, "open_issues_count": 7,
            "language": "Python", "default_branch": "main",
            "updated_at": "2026-11-01T00:00:00Z", "archived": False,
            "html_url": "https://github.com/FatihMakes/Mark-LVI"})})
        row = client.repo("FatihMakes/Mark-LVI")["data"]
        self.assertEqual(row["stars"], 1200)
        self.assertEqual(row["open_issues"], 7)
        self.assertFalse(row["archived"])

    def test_workflow_runs_are_reported_with_their_verdict(self):
        client = self.client(routes={"*": FakeResponse({"workflow_runs": [
            {"name": "verify", "head_branch": "main", "status": "completed",
             "conclusion": "success", "html_url": "u"}]})})
        row = client.checks("acme/rocket")["data"]
        self.assertEqual(row["runs"][0]["conclusion"], "success")


class OtherPlatforms(Base):
    def test_hacker_news_reads_the_list_then_the_stories(self):
        self.serve({
            "https://hacker-news.firebaseio.com/v0/topstories.json": FakeResponse([1, 2]),
            "https://hacker-news.firebaseio.com/v0/item/1.json": FakeResponse(
                {"title": "A new CPU", "score": 300, "descendants": 42, "url": "u"}),
            "https://hacker-news.firebaseio.com/v0/item/2.json": FakeResponse(
                {"title": "An old idea", "score": 5, "descendants": 1}),
        })
        result = platforms.hackernews(2, webapi.Cache(self.path))
        self.assertTrue(result["ok"], result)
        self.assertEqual([row["title"] for row in result["data"]["items"]],
                         ["A new CPU", "An old idea"])
        self.assertIn("news.ycombinator.com", result["data"]["items"][1]["url"])

    def test_stack_overflow_needs_a_question(self):
        self.serve({"*": FakeResponse({})})
        result = platforms.stackexchange("   ")
        self.assertFalse(result["ok"])
        self.assertIn("something to search for", result["note"])

    def test_stack_overflow_returns_answered_state(self):
        self.serve({"*": FakeResponse({"items": [
            {"title": "Why is my socket closed?", "score": 12, "is_answered": True,
             "answer_count": 3, "link": "https://stackoverflow.com/q/1"}]})})
        result = platforms.stackexchange("socket closed")
        self.assertTrue(result["data"]["items"][0]["answered"])

    def test_pypi_and_npm_report_a_version(self):
        self.serve({"*": FakeResponse({"info": {
            "name": "httpx", "version": "0.28.1", "summary": "a client",
            "requires_python": ">=3.8", "license": "BSD-3-Clause", "project_url": "u"}})})
        result = platforms.package("httpx", "pypi")
        self.assertEqual(result["data"]["version"], "0.28.1")
        self.assertTrue(result["data"]["python"].startswith(">="))

        self.serve({"*": FakeResponse({"name": "left-pad", "version": "1.3.0",
                                       "description": "pad", "license": "MIT"})})
        result = platforms.package("left-pad", "npm")
        self.assertEqual(result["data"]["registry"], "npm")

    def test_a_bad_package_name_is_refused_before_a_request(self):
        self.serve({"*": FakeResponse({})})
        result = platforms.package("../../etc/passwd")
        self.assertFalse(result["ok"])
        self.assertEqual(self.web.requests, [])

    def test_an_unknown_source_lists_the_real_ones(self):
        result = platforms.ask("reddit", "python")
        self.assertFalse(result["ok"])
        for name in platforms.SOURCES:
            self.assertIn(name, result["note"])


class Plugins(Base):
    """The two new plugins must load and must degrade, not crash."""

    def test_the_plugin_metadata_is_complete(self):
        from plugins import github_tool, tech_platforms
        for module in (github_tool, tech_platforms):
            meta = module.PLUGIN
            self.assertTrue(meta["name"])
            self.assertTrue(meta["description"])
            self.assertEqual(meta["parameters"]["type"], "OBJECT")
            self.assertIn(meta["tier"], ("OBSERVE", "ROUTINE", "GUARDED"))
            self.assertTrue(callable(module.run))

    def test_an_unknown_action_is_a_sentence(self):
        from plugins import github_tool, tech_platforms
        self.assertIn("Not 'merge'", github_tool.run({"action": "merge"}))
        self.assertIn("hackernews", tech_platforms.run({"source": "myspace"}))

    def test_github_without_a_network_explains_itself(self):
        from plugins import github_tool
        self.serve({"*": urllib.error.URLError("down")})
        offline = github_tool.run({"action": "trending"})
        self.assertIn("no network", offline.lower())


if __name__ == "__main__":
    unittest.main()
