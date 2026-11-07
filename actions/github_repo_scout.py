"""Find public GitHub projects for a capability gap; inspect only, never install."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from core.github import SEARCH

TIMEOUT_SECONDS = 6


def _recency_bonus(pushed_at: str) -> float:
    try:
        pushed = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
        age_days = max(0, (datetime.now(timezone.utc) - pushed).days)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, 5.0 - math.log2(age_days / 30 + 1))


def _score(repo: dict) -> float:
    # Popularity is logarithmic so one enormous project cannot dominate solely
    # because it is old; recent maintenance and an explicit license matter too.
    return (
        math.log2(int(repo.get("stargazers_count") or 0) + 1)
        + _recency_bonus(repo.get("pushed_at", ""))
        + (2.0 if repo.get("license") else 0.0)
        + (1.0 if repo.get("description") else 0.0)
    )


def run(parameters: dict, player=None, session_memory=None) -> str:
    """Search GitHub's public repository index and return a small ranked shortlist."""
    query = str((parameters or {}).get("query") or "").strip()
    if not query:
        return "Name the missing capability or describe what the project should do."

    url = SEARCH + "?" + urlencode({"q": query, "sort": "stars", "order": "desc", "per_page": 10})
    request = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "ULTRON-capability-scout",
    })
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read(1_000_000).decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 403 or exc.code == 429:
            return "GitHub search is rate-limited. Try again later; no code was downloaded."
        return f"GitHub search failed with HTTP {exc.code}; no code was downloaded."
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        return f"GitHub search is unavailable ({exc}); no code was downloaded."

    candidates = payload.get("items", [])
    candidates.sort(key=_score, reverse=True)
    if not candidates:
        return f"No public repositories matched “{query}”."

    lines = [f"GitHub candidates for “{query}” (ranked by stars, maintenance, and metadata):"]
    for repo in candidates[:5]:
        license_name = (repo.get("license") or {}).get("spdx_id") or "license not detected"
        description = " ".join((repo.get("description") or "No description").split())
        if len(description) > 180:
            description = description[:177] + "..."
        lines.append(
            f"- {repo.get('full_name', 'unknown')} — {description}; "
            f"{int(repo.get('stargazers_count') or 0)} stars; "
            f"{repo.get('language') or 'language unknown'}; {license_name}; "
            f"updated {repo.get('pushed_at') or 'unknown'}. "
            f"{repo.get('html_url', '')}"
        )
    lines.append(
        "These are candidates, not endorsements. Review source, license, dependencies, "
        "security, and fit before adapting anything. This tool only reads repository "
        "metadata; it does not clone, download, or install code."
    )
    return "\n".join(lines)


TOOL = {
    "name": "github_repo_scout",
    "description": (
        "Use when no ready tool matches, or the user asks for candidate projects. "
        "Ranks public GitHub repositories for a missing Ultron skill. Reviews public "
        "metadata only; never downloads or installs code."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {
                "type": "STRING",
                "description": "Capability, tool category, or project behavior to search for."
            }
        },
        "required": ["query"],
    },
    "handler": run,
}
