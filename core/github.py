"""core/github.py — GitHub, natively, with the token kept where tokens belong.

What "native" means here, exactly:

- Ultron talks to the **documented REST API** (`api.github.com`). No scraping, no
  invented endpoints, no third-party service in the middle.
- The **token** is read from `config/api_keys.json` under `github_token`, or from
  `GITHUB_TOKEN` in the environment. It is sent in one header and nothing else.
  It is never written to a cache, a log line, a tool result or the transcript.
  A token that leaks into a prompt has to be revoked, so the design is that it
  cannot get there.
- With no token, the **public** endpoints still work at 60 requests an hour. With
  a token they work at 5,000 an hour. Both are stated rather than hidden.
- Answers are cached by ETag, so a repeated question costs no quota.

**"Trending" is an honest approximation.** GitHub publishes no trending API. The
closest documented thing is a search for repositories created in the last N days,
sorted by stars — which is what a trending list approximates anyway. `trending()`
says this in its own result so the model cannot present it as an official list.
"""

from __future__ import annotations
from core import failures

import datetime as _dt
import os
from typing import Any

from core import webapi

API = "https://api.github.com"
SEARCH = "https://api.github.com/search/repositories"


def token() -> str:
    """The user's token: config first, environment second, never hardcoded."""
    try:
        from memory.config_manager import load_api_keys
        value = load_api_keys().get("github_token")
        if isinstance(value, str) and value.strip():
            return value.strip()
    except Exception as error:                                          # noqa: BLE001
        failures.note("github.token", error)
    return (os.environ.get("GITHUB_TOKEN", "") or "").strip()


def _headers(secret: str = "") -> dict[str, str]:
    base = {"Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}
    if secret:
        base["Authorization"] = f"Bearer {secret}"
    return base


class GitHub:
    """One small client. Reads now; writes are a later, guarded step."""

    def __init__(self, secret: str = "", cache: webapi.Cache | None = None) -> None:
        self.secret = secret if secret is not None else token()
        self.cache = cache

    # ------------------------------------------------------------------ reads
    def _get(self, url: str, key: str = "") -> dict:
        status, data, note = webapi.fetch_json(url, headers=_headers(self.secret),
                                               cache=self.cache, key=key or url)
        if status == 0:
            return {"ok": False, "note": note or webapi.NO_NETWORK, "data": None}
        return {"ok": True, "note": note, "data": data}

    def whoami(self) -> dict:
        if not self.secret:
            return {"ok": False, "note": ("No GitHub token is set, so I cannot see your "
                                          "account. Add `github_token` in config to use "
                                          "your notifications and private repositories."),
                    "data": None}
        return self._get(f"{API}/user", "user")

    def repo(self, full_name: str) -> dict:
        name = str(full_name or "").strip().strip("/")
        if "/" not in name:
            return {"ok": False, "note": "Give the repository as owner/name, for example "
                                         "FatihMakes/Mark-LVI.", "data": None}
        result = self._get(f"{API}/repos/{name}", f"repo:{name}")
        if not result["ok"]:
            return result
        row = result["data"] or {}
        return {"ok": True, "note": "", "data": {
            "full_name": row.get("full_name", name),
            "description": row.get("description") or "",
            "stars": row.get("stargazers_count", 0),
            "forks": row.get("forks_count", 0),
            "open_issues": row.get("open_issues_count", 0),
            "language": row.get("language") or "",
            "default_branch": row.get("default_branch") or "",
            "updated_at": row.get("updated_at") or "",
            "archived": bool(row.get("archived")),
            "url": row.get("html_url") or "",
        }}

    def trending(self, days: int = 7, minimum_stars: int = 50,
                 language: str = "", limit: int = 8) -> dict:
        """Recent repositories with the most stars. Not an official trending list."""
        days = max(1, min(365, int(days)))
        minimum_stars = max(1, int(minimum_stars))
        limit = max(1, min(30, int(limit)))
        since = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days))
        query = f"created:>{since.date().isoformat()} stars:>{minimum_stars - 1}"
        if language:
            query += f" language:{str(language).strip()}"
        url = (f"{SEARCH}?q={webapi.quote(query)}&sort=stars&order=desc"
               f"&per_page={limit}")
        result = self._get(url, f"trending:{query}:{limit}")
        if not result["ok"]:
            return result
        items = ((result["data"] or {}).get("items") or [])[:limit]
        return {"ok": True, "note": "", "data": {
            "source": ("a search for repositories created in the last "
                       f"{days} days, sorted by stars — GitHub publishes no trending "
                       "API, so this is the closest documented equivalent"),
            "items": [{"full_name": row.get("full_name", ""),
                       "description": (row.get("description") or "")[:200],
                       "stars": row.get("stargazers_count", 0),
                       "language": row.get("language") or "",
                       "url": row.get("html_url") or ""} for row in items]}}

    def notifications(self, limit: int = 10, only_unread: bool = True) -> dict:
        if not self.secret:
            return {"ok": False, "note": "Notifications need a token with the "
                                         "notifications permission.", "data": None}
        limit = max(1, min(50, int(limit)))
        url = f"{API}/notifications?per_page={limit}"
        if only_unread:
            url += "&all=false"
        result = self._get(url, f"notifications:{limit}:{only_unread}")
        if not result["ok"]:
            return result
        rows = result["data"] or []
        return {"ok": True, "note": "", "data": {
            "unread": len(rows),
            "items": [{"repo": (row.get("repository") or {}).get("full_name", ""),
                       "title": row.get("subject", {}).get("title", ""),
                       "type": row.get("subject", {}).get("type", ""),
                       "reason": row.get("reason", ""),
                       "updated_at": row.get("updated_at", "")}
                      for row in rows if isinstance(row, dict)]}}

    def checks(self, full_name: str, limit: int = 5) -> dict:
        name = str(full_name or "").strip().strip("/")
        if "/" not in name:
            return {"ok": False, "note": "Give the repository as owner/name.", "data": None}
        url = f"{API}/repos/{name}/actions/runs?per_page={max(1, min(20, int(limit)))}"
        result = self._get(url, f"runs:{name}")
        if not result["ok"]:
            return result
        runs = ((result["data"] or {}).get("workflow_runs") or [])
        return {"ok": True, "note": "", "data": {
            "repository": name,
            "runs": [{"name": row.get("name", ""),
                      "branch": row.get("head_branch", ""),
                      "status": row.get("status", ""),
                      "conclusion": row.get("conclusion") or "",
                      "url": row.get("html_url", "")} for row in runs]}}

    def pulls(self, full_name: str, limit: int = 10) -> dict:
        name = str(full_name or "").strip().strip("/")
        if "/" not in name:
            return {"ok": False, "note": "Give the repository as owner/name.", "data": None}
        url = f"{API}/repos/{name}/pulls?state=open&per_page={max(1, min(30, int(limit)))}"
        result = self._get(url, f"pulls:{name}")
        if not result["ok"]:
            return result
        rows = result["data"] or []
        return {"ok": True, "note": "", "data": {
            "repository": name, "open": len(rows),
            "items": [{"number": row.get("number"),
                       "title": row.get("title", ""),
                       "author": (row.get("user") or {}).get("login", ""),
                       "draft": bool(row.get("draft")),
                       "updated_at": row.get("updated_at", "")}
                      for row in rows if isinstance(row, dict)]}}


def default(cache_path: Any = None) -> GitHub:
    """A client wired to the configured token and one on-disk ETag cache."""
    cache = webapi.Cache(cache_path) if cache_path else None
    return GitHub(token(), cache)
