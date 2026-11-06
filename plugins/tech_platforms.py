"""tech_platforms — the technical world outside GitHub, in one tool.

Four sources, all public and keyless, so there is nothing to configure:

    hackernews      what the technical world is reading right now
    stackexchange   Stack Overflow answers to a question
    pypi            a Python package's latest version and purpose
    npm             a JavaScript package's latest version and purpose

Each answer is cached by ETag, so asking twice costs nothing. A platform that is
unreachable says so in one sentence — it never returns an empty list that reads
like "nothing is happening".
"""

from core import platforms

PLUGIN = {
    "name": "tech_platforms",
    "description": (
        "Reads four technical sources: Hacker News top stories, Stack Overflow "
        "search, PyPI package facts and npm package facts. Use it when the user "
        "asks what developers are reading, how to solve a programming error, or "
        "what version a package is on."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "source": {
                "type": "STRING",
                "description": "hackernews | stackexchange | pypi | npm",
            },
            "query": {
                "type": "STRING",
                "description": "a search phrase, or a package name",
            },
            "limit": {"type": "INTEGER", "description": "how many items (default 6)"},
        },
        "required": ["source"],
    },
    "tier": "ROUTINE",
    "brief": "Hacker News, Stack Overflow, PyPI and npm, read-only.",
}


def _cache():
    try:
        from core import webapi
        from core.paths import state_dir
        return webapi.Cache(state_dir() / "web_cache.json")
    except Exception:                                          # noqa: BLE001
        return None


def run(parameters, player=None, session_memory=None):
    source = str(parameters.get("source") or "").strip().lower()
    query = str(parameters.get("query") or "").strip()
    limit = parameters.get("limit") or 6
    result = platforms.ask(source, query, limit, _cache())
    if not result["ok"]:
        return result["note"]

    data = result["data"] or {}
    if source == "hackernews":
        lines = [f"Hacker News, top {len(data['items'])} now:"]
        for row in data["items"]:
            lines.append(f"- {row['title']} — {row['score']} points, "
                         f"{row['comments']} comments. {row['url']}")
        return "\n".join(lines)
    if source == "stackexchange":
        items = data.get("items") or []
        if not items:
            return f"Stack Overflow has no answer for '{query}' yet."
        lines = [f"Stack Overflow, best {len(items)} for '{query}':"]
        for row in items:
            mark = "answered" if row["answered"] else "unanswered"
            lines.append(f"- {row['title']} — score {row['score']}, {row['answers']} "
                         f"answers, {mark}. {row['url']}")
        return "\n".join(lines)

    if not data.get("version"):
        return f"{data.get('name', query)} has no published version I can read."
    summary = f" — {data['summary']}" if data.get("summary") else ""
    python = f", needs Python {data['python']}" if data.get("python") else ""
    licence = f", licence {data['licence']}" if data.get("licence") else ""
    return (f"{data['name']} {data['version']} on {data['registry']}{summary}"
            f"{python}{licence}. {data.get('home', '')}").strip()
