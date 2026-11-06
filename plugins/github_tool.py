"""github_tool — GitHub as a native capability, not a link.

Read-only in this build: your repositories, their state, the open pull requests,
the last CI runs, your unread notifications, and what is trending this week. It
also keeps a **watch list** and turns it into reminders (`reminders`), ordered by
the same expected-value arithmetic that chooses an action, with quiet hours and a
cooldown so the same repository cannot be mentioned twice in an afternoon.
Writing (a comment, a pull request, a merge) is deliberately not here yet: those
change an account other people can see, so they will arrive behind an approval
that names the exact action.

The token lives in `config/api_keys.json` as `github_token`, or in `GITHUB_TOKEN`.
Without it, public repositories still work; your notifications do not.

"Trending" is a search for recently created repositories sorted by stars. GitHub
publishes no trending API, and this plugin says so in its own answer instead of
letting the model describe it as an official list.
"""

from core import github, webapi

PLUGIN = {
    "name": "github_tool",
    "description": (
        "Reads GitHub: a repository's stars, forks, open issues and last update; "
        "open pull requests; the latest CI workflow runs; your unread "
        "notifications; and what is trending this week. Use it when the user asks "
        "about a GitHub repository, their notifications, or what is popular on "
        "GitHub now. It cannot write, comment or merge."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": ("status | trending | notifications | repo | pulls | "
                                "checks | watch | unwatch | watchlist | reminders"),
            },
            "repository": {"type": "STRING",
                           "description": "owner/name, for repo, pulls and checks"},
            "language": {"type": "STRING",
                         "description": "for trending: python, rust, typescript..."},
            "days": {"type": "INTEGER", "description": "for trending: created in the last N days (default 7)"},
            "limit": {"type": "INTEGER", "description": "how many items (default 8)"},
        },
        "required": ["action"],
    },
    "tier": "GUARDED",
    "brief": "GitHub reads: repositories, pull requests, CI runs, notifications, trending.",
}

_ACTIONS = ("status", "trending", "notifications", "repo", "pulls", "checks",
            "watch", "unwatch", "watchlist", "reminders")


def _cache():
    try:
        from core.paths import state_dir
        return webapi.Cache(state_dir() / "web_cache.json")
    except Exception:                                          # noqa: BLE001
        return None


# ── the watch list, and the reminders built from it ──────────────────────────

def _state(name: str):
    from core.paths import state_dir
    return state_dir() / name


def _load_watch() -> dict:
    import json
    path = _state("github_watch.json")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    repos = [str(item).strip() for item in (raw.get("repos") or []) if str(item).strip()]
    languages = [str(item).strip().lower() for item in (raw.get("languages") or [])
                 if str(item).strip()]
    return {"repos": repos[:10], "languages": languages[:5],
            "days": int(raw.get("days") or 7)}


def _save_watch(data: dict) -> None:
    import json
    path = _state("github_watch.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")


def _queue():
    """The reminder queue, with quiet hours taken from the user's own config."""
    from custom_jarvis.schedule import Queue
    start, end = 23, 7
    try:
        from memory.config_manager import load_api_keys
        config = load_api_keys()
        start = int(config.get("quiet_start", start) or start)
        end = int(config.get("quiet_end", end) or end)
    except Exception:                                          # noqa: BLE001
        pass
    return Queue(_state("reminders.json"), quiet_start=start, quiet_end=end)


def _reminders(client) -> str:
    """Build the cards, order them with the decision arithmetic, say the top few."""
    watch = _load_watch()
    if not watch["repos"] and not watch["languages"]:
        return ("I am not watching anything yet. Say 'watch owner/name' for a "
                "repository, or 'watch python' for a language's trending list.")
    queue = _queue()
    notes = []

    for repository in watch["repos"]:
        runs = client.checks(repository, limit=3)
        if runs["ok"]:
            failing = [row for row in (runs["data"] or {}).get("runs", [])
                       if (row.get("conclusion") or "") in ("failure", "timed_out",
                                                            "cancelled")]
            if failing:
                queue.add(f"ci:{repository}",
                          f"{repository}: the last CI run on "
                          f"{failing[0]['branch'] or 'a branch'} failed",
                          urgency=0.9, value=1.5, cost=0.2)
        pulls = client.pulls(repository, limit=10)
        if pulls["ok"]:
            open_count = (pulls["data"] or {}).get("open", 0)
            if open_count:
                queue.add(f"pr:{repository}",
                          f"{repository}: {open_count} pull request(s) open",
                          urgency=0.5, value=1.0, cost=0.2)
        repo = client.repo(repository)
        if repo["ok"]:
            updated = str((repo["data"] or {}).get("updated_at") or "")[:10]
            if updated and updated < _days_ago(45):
                queue.add(f"stale:{repository}",
                          f"{repository}: nothing has changed since {updated}",
                          urgency=0.3, value=0.8, cost=0.3, cooldown=24 * 3600)

    unread = client.notifications(limit=20)
    if unread["ok"]:
        count = (unread["data"] or {}).get("unread", 0)
        if count:
            queue.add("notifications:all", f"You have {count} unread GitHub notification(s)",
                      urgency=0.8, value=1.2, cost=0.2)

    for language in watch["languages"]:
        trending = client.trending(days=watch["days"], language=language, limit=3)
        if not trending["ok"]:
            notes.append(trending["note"])
            continue
        for row in (trending["data"] or {}).get("items", []):
            if row["full_name"] in watch["repos"]:
                continue
            queue.add(f"trending:{row['full_name']}",
                      f"Trending in {language or 'any language'}: {row['full_name']} "
                      f"— {row['stars']:,} stars. {row.get('description', '')}".strip(),
                      urgency=0.35, value=0.9, cost=0.2, cooldown=7 * 24 * 3600)

    due = queue.due(limit=3)
    if not due:
        return "Nothing needs you on GitHub right now." + (
            " " + " ".join(notes) if notes else "")
    queue.mark_shown([card["id"] for card in due])
    lines = [f"{len(due)} thing(s) worth your attention:"]
    for card in due:
        lines.append(f"- {card['title']}  ({card['score']:+.2f}; {card['why']})")
    return "\n".join(lines)


def _days_ago(days: int) -> str:
    import datetime as _dt
    return (_dt.date.today() - _dt.timedelta(days=days)).isoformat()


def _sentence(result, empty: str) -> str:
    if not result.get("ok"):
        return str(result.get("note") or "GitHub did not answer.")
    data = result.get("data") or {}
    if isinstance(data, list) and not data:
        return empty
    return ""


def _trending(client, parameters) -> str:
    result = client.trending(days=parameters.get("days") or 7,
                             language=parameters.get("language") or "",
                             limit=parameters.get("limit") or 8)
    if not result["ok"]:
        return result["note"]
    items = (result["data"] or {}).get("items") or []
    if not items:
        return "No recently created repository has passed that star count yet."
    lines = [f"Trending: {len(items)} repositories created recently, most stars first.",
             f"({result['data'].get('source')})"]
    for row in items:
        stars = row.get("stars", 0)
        language = row.get("language") or "no language"
        lines.append(f"- {row['full_name']} — {stars:,} stars, {language}. "
                     f"{row.get('description', '')}".rstrip())
    return "\n".join(lines)


def run(parameters, player=None, session_memory=None):
    action = str(parameters.get("action") or "status").strip().lower()
    if action not in _ACTIONS:
        return ("I can do " + ", ".join(_ACTIONS) + " on GitHub. Not '" + action + "'.")
    client = github.GitHub(github.token(), _cache())

    if action == "status":
        account = client.whoami()
        if not account["ok"]:
            return account["note"]
        user = account["data"] or {}
        return (f"Signed in as {user.get('login', '?')}"
                f" with {user.get('public_repos', 0)} public repositories.")

    if action == "trending":
        return _trending(client, parameters)

    if action in ("watch", "unwatch"):
        watch = _load_watch()
        target = str(parameters.get("repository") or parameters.get("language") or "").strip()
        if not target:
            return "Tell me which repository (owner/name) or language to watch."
        lowered = target.lower()
        if "/" in target:
            bucket = watch["repos"]
            key = target
        else:
            bucket = watch["languages"]
            key = lowered
        if action == "watch":
            if key not in bucket:
                bucket.append(key)
            _save_watch(watch)
            return f"Watching {key}. Say 'reminders' to see what I would tell you."
        if key in bucket:
            bucket.remove(key)
            _save_watch(watch)
            return f"No longer watching {key}."
        return f"I was not watching {key}."

    if action == "watchlist":
        watch = _load_watch()
        if not watch["repos"] and not watch["languages"]:
            return "The watch list is empty."
        parts = []
        if watch["repos"]:
            parts.append("repositories: " + ", ".join(watch["repos"]))
        if watch["languages"]:
            parts.append("languages: " + ", ".join(watch["languages"]))
        return "Watching " + "; ".join(parts) + "."

    if action == "reminders":
        return _reminders(client)

    if action == "notifications":
        result = client.notifications(limit=parameters.get("limit") or 10)
        if not result["ok"]:
            return result["note"]
        rows = (result["data"] or {}).get("items") or []
        if not rows:
            return "Nothing unread on GitHub."
        lines = [f"{len(rows)} unread notification(s):"]
        for row in rows:
            lines.append(f"- {row['repo']}: {row['title']} ({row['reason']})")
        return "\n".join(lines)

    repository = str(parameters.get("repository") or "").strip()
    if action == "repo":
        result = client.repo(repository)
        if not result["ok"]:
            return result["note"]
        row = result["data"] or {}
        state = "archived" if row.get("archived") else "active"
        return (f"{row['full_name']} — {row['stars']:,} stars, {row['forks']:,} forks, "
                f"{row['open_issues']} open issues, {row['language'] or 'no language'}, "
                f"{state}, last updated {str(row.get('updated_at'))[:10]}. "
                f"{row.get('description', '')}".strip())

    if action == "pulls":
        result = client.pulls(repository, limit=parameters.get("limit") or 10)
        if not result["ok"]:
            return result["note"]
        rows = (result["data"] or {}).get("items") or []
        if not rows:
            return f"No open pull requests on {repository}."
        lines = [f"{len(rows)} open pull request(s) on {repository}:"]
        for row in rows:
            draft = " (draft)" if row.get("draft") else ""
            lines.append(f"- #{row['number']} {row['title']} by {row['author']}{draft}")
        return "\n".join(lines)

    result = client.checks(repository, limit=parameters.get("limit") or 5)
    if not result["ok"]:
        return result["note"]
    rows = (result["data"] or {}).get("runs") or []
    if not rows:
        return f"No workflow runs on {repository}."
    lines = [f"Last {len(rows)} workflow run(s) on {repository}:"]
    for row in rows:
        verdict = row.get("conclusion") or row.get("status") or "unknown"
        lines.append(f"- {row['name']} on {row['branch'] or 'a branch'}: {verdict}")
    return "\n".join(lines)
