"""core/webapi.py — one bounded, cached JSON reader for the public web.

Five platforms now speak to Ultron: GitHub, Hacker News, Stack Exchange, PyPI and
the npm registry. They have different shapes and the same four problems, so the
four problems are solved once, here:

1. **A request must not hang.** Every call has a deadline, and a missing network
   is a sentence, not a traceback.
2. **Politeness must cost nothing.** Responses carry an `ETag`. We store it with
   the body. The next call sends `If-None-Match`, GitHub answers `304`, and —
   this is the part that matters — a `304` does not count against the hourly
   quota. A watch list therefore stays inside one quota instead of blowing it.
3. **The answer must not be enormous.** Bodies are capped, and the cap is a
   refusal with a reason, not a truncation that parses as valid JSON.
4. **A failure must be describable.** `(status, data, note)` where the note is
   one sentence a person can act on: "no network", "rate limited until 14:20",
   "GitHub said 404".

Nothing here knows what GitHub is. `core/github.py` adds the token and the
endpoints; `core/platforms.py` adds the other four.
"""

from __future__ import annotations

import gzip
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

TIMEOUT = 6.0                 # seconds a request may take
BODY_LIMIT = 2_000_000        # bytes of JSON we are willing to parse
CACHE_LIMIT = 400             # entries kept on disk
USER_AGENT = "Ultron/1.2.17 (+https://github.com/FatihMakes/Mark-LVI)"

# A note, not an exception: the caller is a language model reading a sentence.
NO_NETWORK = "I have no network connection, so I cannot reach that platform."
_opener: Callable[..., Any] | None = None


def set_opener(opener: Callable[..., Any] | None) -> None:
    """Replace the transport. Tests use this; production never calls it."""
    global _opener
    _opener = opener


def _open(request, timeout: float):
    return (_opener or urllib.request.urlopen)(request, timeout=timeout)


class Cache:
    """ETag-and-body cache in one JSON file. One file, because one is enough."""

    def __init__(self, path: Path | str | None) -> None:
        self.path = Path(path) if path else None
        self._rows: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._rows = {str(k): v for k, v in raw.items() if isinstance(v, dict)}
        except (OSError, ValueError):
            self._rows = {}

    def get(self, key: str) -> dict:
        return self._rows.get(key, {})

    def put(self, key: str, etag: str, body: Any) -> None:
        if not self.path:
            return
        self._rows[key] = {"etag": etag, "body": body, "at": round(time.time(), 3)}
        while len(self._rows) > CACHE_LIMIT:
            oldest = min(self._rows, key=lambda name: self._rows[name].get("at", 0.0))
            self._rows.pop(oldest, None)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self._rows, ensure_ascii=False),
                                 encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError:
            pass  # a cache that cannot write is a slow cache, not a broken tool


def fetch_json(url: str, *, headers: dict[str, str] | None = None,
               cache: Cache | None = None, key: str = "", ttl: float = 0.0,
               timeout: float = TIMEOUT) -> tuple[int, Any, str]:
    """Read JSON from `url`. Returns (status, data, note); status 0 means no answer.

    `ttl` is how long a cached body may be used with no request at all. The
    default 0 asks every time, which is right for a source that changes hourly
    and costs nothing to ask about because of the ETag.
    """
    lookup = key or url
    cached = cache.get(lookup) if cache else {}
    if ttl > 0 and cached.get("at", 0.0) and time.time() - cached["at"] < ttl:
        return 304, cached.get("body"), ""

    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    request_headers.update({str(k): str(v) for k, v in (headers or {}).items()})
    if cached.get("etag"):
        request_headers["If-None-Match"] = str(cached["etag"])

    request = urllib.request.Request(url, headers=request_headers, method="GET")
    try:
        with _open(request, timeout) as response:
            body = response.read(BODY_LIMIT + 1)
            etag = response.headers.get("ETag", "") or ""
            if len(body) > BODY_LIMIT:
                return 0, None, ("That answer is larger than 2 MB, so I did not read it. "
                                 "Ask for less: one repository, one page, one query.")
            if body[:2] == b"\x1f\x8b":       # some APIs compress without being asked
                body = gzip.decompress(body)
            data = json.loads(body.decode("utf-8", "replace") or "null")
        if cache and etag:
            cache.put(lookup, etag, data)
        return int(getattr(response, "status", 200) or 200), data, ""
    except urllib.error.HTTPError as error:
        if error.code == 304:
            return 304, cached.get("body"), ""
        if error.code == 404:
            return 404, None, "That address does not exist on the platform (404)."
        if error.code in (401, 403):
            reset = error.headers.get("X-RateLimit-Reset", "") if error.headers else ""
            remaining = (error.headers.get("X-RateLimit-Remaining", "")
                         if error.headers else "")
            if str(remaining).strip() == "0" and str(reset).strip().isdigit():
                when = time.strftime("%H:%M", time.localtime(int(reset)))
                return error.code, None, f"The API quota is used up until {when}."
            return error.code, None, ("That needs a valid token with the right "
                                      "permission, or the quota is spent.")
        return error.code, None, f"The platform refused the request ({error.code})."
    except urllib.error.URLError:
        return 0, None, NO_NETWORK
    except (TimeoutError, OSError):
        return 0, None, "The platform did not answer in time."
    except ValueError:
        return 0, None, "The platform answered with something that is not JSON."


def quote(text: str) -> str:
    """A query value safe for a URL, including the '+' and ':' GitHub queries use."""
    return urllib.parse.quote(str(text or ""), safe="")
