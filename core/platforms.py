"""core/platforms.py — the other technical platforms, read-only and honest.

GitHub is the one that gets a class of its own, because it needs a token, a quota
story and a watch list. The rest are simpler and share one shape:

    hackernews      what the technical world is reading right now
    stackexchange   answers to a question, from Stack Overflow
    pypi            what a Python package is, and its latest version
    npm             the same for a JavaScript package

Each is a **public, documented, keyless** endpoint, so there is nothing to
configure and nothing to leak. Each returns the same dict shape as GitHub's
methods — `{"ok", "note", "data"}` — with `note` a sentence when it fails.

The rule that keeps this honest: a platform that is not reachable says so. It
does not return an empty list that reads like "nothing is happening".
"""

from __future__ import annotations

from typing import Any

from core import webapi

HACKER_NEWS = "https://hacker-news.firebaseio.com/v0"
STACK_EXCHANGE = "https://api.stackexchange.com/2.3"
PYPI = "https://pypi.org/pypi"
NPM = "https://registry.npmjs.org"

SOURCES = ("hackernews", "stackexchange", "pypi", "npm")


def _failed(note: str) -> dict:
    return {"ok": False, "note": note, "data": None}


def hackernews(limit: int = 6, cache: webapi.Cache | None = None) -> dict:
    """The current top stories: title, score, comments, link."""
    limit = max(1, min(15, int(limit)))
    status, ids, note = webapi.fetch_json(f"{HACKER_NEWS}/topstories.json",
                                          cache=cache, key="hn:top")
    if status == 0 or not isinstance(ids, list):
        return _failed(note or webapi.NO_NETWORK)
    stories = []
    for story_id in ids[:limit]:
        code, item, item_note = webapi.fetch_json(
            f"{HACKER_NEWS}/item/{story_id}.json", cache=cache, key=f"hn:{story_id}")
        if code == 0 or not isinstance(item, dict):
            continue
        stories.append({"title": item.get("title", ""),
                        "score": item.get("score", 0),
                        "comments": item.get("descendants", 0),
                        "url": item.get("url") or f"https://news.ycombinator.com/item?id={story_id}"})
    if not stories:
        return _failed(note or "Hacker News returned no stories I could read.")
    return {"ok": True, "note": "", "data": {"source": "Hacker News", "items": stories}}


def stackexchange(query: str, limit: int = 5, cache: webapi.Cache | None = None) -> dict:
    """Search Stack Overflow. Answers carry a link; the body is not quoted back."""
    asked = str(query or "").strip()
    if not asked:
        return _failed("Give me something to search for, for example 'python asyncio "
                       "timeout'.")
    limit = max(1, min(10, int(limit)))
    url = (f"{STACK_EXCHANGE}/search/advanced?order=desc&sort=relevance"
           f"&q={webapi.quote(asked)}&site=stackoverflow&pagesize={limit}")
    status, data, note = webapi.fetch_json(url, cache=cache, key=f"se:{asked}:{limit}")
    if status == 0 or not isinstance(data, dict):
        return _failed(note or webapi.NO_NETWORK)
    rows = data.get("items") or []
    return {"ok": True, "note": "", "data": {
        "source": "Stack Overflow",
        "query": asked,
        "items": [{"title": row.get("title", ""),
                   "score": row.get("score", 0),
                   "answered": bool(row.get("is_answered")),
                   "answers": row.get("answer_count", 0),
                   "url": row.get("link", "")} for row in rows if isinstance(row, dict)]}}


def package(name: str, registry: str = "pypi",
            cache: webapi.Cache | None = None) -> dict:
    """What a package is: latest version, summary, licence, project page."""
    wanted = str(name or "").strip()
    if not wanted or not all(part.replace("-", "").replace("_", "").replace(".", "")
                             .isalnum() for part in wanted.split("/")):
        return _failed("Give me a package name, for example 'httpx'.")
    kind = str(registry or "pypi").strip().lower()
    if kind not in ("pypi", "npm"):
        return _failed("I can look up PyPI or npm, not " + repr(registry) + ".")
    url = (f"{PYPI}/{wanted}/json" if kind == "pypi"
           else f"{NPM}/{wanted}/latest")
    status, data, note = webapi.fetch_json(url, cache=cache, key=f"{kind}:{wanted}")
    if status == 0 or not isinstance(data, dict):
        return _failed(note or webapi.NO_NETWORK)
    if kind == "pypi":
        info = data.get("info") or {}
        return {"ok": True, "note": "", "data": {
            "registry": "PyPI", "name": info.get("name", wanted),
            "version": info.get("version", ""),
            "summary": (info.get("summary") or "")[:200],
            "python": info.get("requires_python") or "",
            "licence": (info.get("license") or "")[:60],
            "home": info.get("project_url") or info.get("home_page") or ""}}
    return {"ok": True, "note": "", "data": {
        "registry": "npm", "name": data.get("name", wanted),
        "version": data.get("version", ""),
        "summary": (data.get("description") or "")[:200],
        "licence": (data.get("license") or "")[:60],
        "home": data.get("homepage") or ""}}


def ask(source: str, query: str = "", limit: int = 6,
        cache: webapi.Cache | None = None) -> dict:
    """One entry point for a tool: pick the platform, get the same shape back."""
    kind = str(source or "").strip().lower()
    if kind not in SOURCES:
        return _failed("I know " + ", ".join(SOURCES) + ". Not " + repr(source) + ".")
    if kind == "hackernews":
        return hackernews(limit, cache)
    if kind == "stackexchange":
        return stackexchange(query, min(limit, 10), cache)
    return package(query, kind, cache)


def describe() -> dict[str, Any]:
    """For the tool catalog: what each source answers, in one line."""
    return {
        "hackernews": "top technical stories right now",
        "stackexchange": "Stack Overflow answers to a question",
        "pypi": "a Python package's latest version and purpose",
        "npm": "a JavaScript package's latest version and purpose",
    }
