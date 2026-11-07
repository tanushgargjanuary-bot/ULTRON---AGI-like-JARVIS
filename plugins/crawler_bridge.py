"""plugins/crawler_bridge.py — High-speed web scraping and LLM-ready markdown extraction bridge.

Integrates Crawl4AI (unclecode/crawl4ai on GitHub) for high-speed, LLM-ready
markdown extraction from modern web pages, with a robust zero-dependency fallback parser.
"""

from __future__ import annotations

import html.parser
import json
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from core import failures

PLUGIN = {
    "name": "crawler_bridge",
    "description": (
        "Extracts clean, LLM-ready markdown and structural text from any website or raw HTML. "
        "Use it when the user asks to crawl a URL, summarize a webpage, extract text from web content, "
        "or convert HTML documents into clean markdown without ads or tracking scripts."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "'crawl' to scrape a live URL, 'markdown' to parse raw HTML into markdown, or 'status' to check engine readiness.",
                "enum": ["crawl", "markdown", "status"],
            },
            "url": {
                "type": "STRING",
                "description": "Full HTTP/HTTPS URL of the webpage to crawl.",
            },
            "raw_html": {
                "type": "STRING",
                "description": "Optional raw HTML string to convert into clean markdown without web requests.",
            },
            "css_selector": {
                "type": "STRING",
                "description": "Optional tag or class filter (e.g. 'article', 'main', 'body') to restrict parsing.",
            },
            "max_chars": {
                "type": "INTEGER",
                "description": "Maximum characters of markdown to return (default: 4000, max: 12000).",
            },
        },
        "required": ["action"],
    },
    "tier": "ROUTINE",
}

DEFAULT_SERVICE_URL = "http://127.0.0.1:11235"
DEFAULT_MAX_CHARS = 4000
MAX_OUTPUT_LIMIT = 12000
FETCH_TIMEOUT = 15.0

_HEADER_PREFIXES = {f"h{i}": f"\n\n{'#' * i} " for i in range(1, 7)}
_TAG_PREFIXES = {
    "p": "\n\n",
    "br": "\n",
    "blockquote": "\n> ",
}


class _NativeHTMLToMarkdown(html.parser.HTMLParser):
    """Zero-dependency HTML to clean Markdown converter."""

    _IGNORE_TAGS = frozenset({"script", "style", "noscript", "svg", "head", "iframe", "nav", "footer"})

    def __init__(self, target_tag: str | None = None) -> None:
        super().__init__()
        self.target_tag = target_tag.lower() if target_tag else None
        self._pieces: list[str] = []
        self._ignore_depth = 0
        self._current_tag = ""
        self._tag_stack: list[str] = []
        self._in_pre = False
        self._list_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        self._tag_stack.append(tag_lower)
        if tag_lower in self._IGNORE_TAGS:
            self._ignore_depth += 1
            return
        if self._ignore_depth > 0:
            return

        if tag_lower in _HEADER_PREFIXES:
            self._pieces.append(_HEADER_PREFIXES[tag_lower])
            return
        if tag_lower in _TAG_PREFIXES:
            self._pieces.append(_TAG_PREFIXES[tag_lower])
            return
        if tag_lower in ("ul", "ol"):
            self._list_depth += 1
            self._pieces.append("\n")
            return
        if tag_lower == "li":
            indent = "  " * max(0, self._list_depth - 1)
            self._pieces.append(f"\n{indent}* ")
            return
        if tag_lower == "pre":
            self._in_pre = True
            self._pieces.append("\n```\n")
            return
        if tag_lower == "code" and not self._in_pre:
            self._pieces.append("`")
            return
        if tag_lower == "a":
            href = dict(attrs).get("href", "")
            if href and not href.startswith("javascript:"):
                self._pieces.append("[")
                self._current_tag = f"]({href})"
            else:
                self._current_tag = ""

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if self._tag_stack and self._tag_stack[-1] == tag_lower:
            self._tag_stack.pop()
        if tag_lower in self._IGNORE_TAGS:
            self._ignore_depth = max(0, self._ignore_depth - 1)
            return
        if self._ignore_depth > 0:
            return

        if tag_lower in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "blockquote"):
            self._pieces.append("\n")
            return
        if tag_lower in ("ul", "ol"):
            self._list_depth = max(0, self._list_depth - 1)
            self._pieces.append("\n")
            return
        if tag_lower == "pre":
            self._in_pre = False
            self._pieces.append("\n```\n")
            return
        if tag_lower == "code" and not self._in_pre:
            self._pieces.append("`")
            return
        if tag_lower == "a" and self._current_tag:
            self._pieces.append(self._current_tag)
            self._current_tag = ""

    def handle_data(self, data: str) -> None:
        if self._ignore_depth > 0:
            return
        clean = data if self._in_pre else re.sub(r"[ \t]+", " ", data)
        self._pieces.append(clean)

    def get_markdown(self) -> str:
        raw = "".join(self._pieces)
        lines = [line.rstrip() for line in raw.splitlines()]
        cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
        return cleaned.strip()


def _probe_engine() -> dict[str, Any]:
    """Check availability of Crawl4AI service, CLI, and native engine."""
    service_ok = False
    service_detail = ""
    try:
        req = urllib.request.Request(
            f"{DEFAULT_SERVICE_URL}/health",
            headers={"User-Agent": "Ultron-CrawlerBridge"},
        )
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            if resp.status == 200:
                service_ok = True
                service_detail = f"Active at {DEFAULT_SERVICE_URL}"
    except Exception as exc:
        failures.note("crawler_bridge.probe_http", exc)
        service_detail = f"Offline ({DEFAULT_SERVICE_URL})"

    cli_path = shutil.which("crawl4ai")
    cli_ok = bool(cli_path)

    return {
        "service_ready": service_ok,
        "service_detail": service_detail,
        "cli_ready": cli_ok,
        "cli_path": cli_path or "Not on PATH",
        "fallback_ready": True,
        "fallback_detail": "Native HTML parser ready (zero dependencies)",
    }


def _fetch_page(url: str, timeout: float = FETCH_TIMEOUT) -> str:
    """Fetch live web page using standard HTTP request."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        raw_bytes = resp.read()
        return raw_bytes.decode(charset, errors="replace")


def _html_to_markdown(html_text: str, target_tag: str | None = None) -> str:
    """Convert HTML string to clean Markdown."""
    try:
        parser = _NativeHTMLToMarkdown(target_tag=target_tag)
        parser.feed(html_text)
        return parser.get_markdown()
    except Exception as exc:
        failures.note("crawler_bridge.html_parser", exc)
        text_only = re.sub(r"<[^>]+>", " ", html_text)
        return re.sub(r"\s+", " ", text_only).strip()


def _safe_call(player, method: str, *args) -> None:
    if player is not None:
        try:
            fn = getattr(player, method, None)
            if callable(fn):
                fn(*args)
        except Exception as exc:
            failures.note(f"crawler_bridge.{method}", exc)


def _handle_status(player) -> str:
    info = _probe_engine()
    lines = [
        "### Crawl4AI & Web Crawler Bridge Status",
        f"- **Service Engine**: {info['service_detail']} (Ready: {info['service_ready']})",
        f"- **CLI Engine**: {info['cli_path']} (Ready: {info['cli_ready']})",
        f"- **Native Parser**: {info['fallback_detail']}",
        "\nInstall full headless browser crawling with: `pip install crawl4ai` && `crawl4ai-setup`.",
    ]
    summary = "\n".join(lines)
    _safe_call(player, "show_content", "CRAWLER BRIDGE", summary)
    return (
        f"Crawler engine status: Service {'ready' if info['service_ready'] else 'offline'}, "
        f"CLI {'ready' if info['cli_ready'] else 'not on PATH'}. Native parser ready."
    )


def _handle_markdown(raw_html: str, selector: str, max_chars: int, player) -> str:
    if not raw_html:
        return "Sir, I need raw HTML content to convert to markdown."
    md = _html_to_markdown(raw_html, target_tag=selector or None)
    if len(md) > max_chars:
        md = md[:max_chars] + f"\n\n… [Truncated at {max_chars} characters]"
    _safe_call(player, "show_content", "PARSED MARKDOWN", md)
    return f"Extracted {len(md)} characters of markdown:\n\n{md}"


def _crawl_via_service(url: str, selector: str, max_chars: int, player) -> str | None:
    try:
        payload = json.dumps({"url": url, "css_selector": selector}).encode("utf-8")
        req = urllib.request.Request(
            f"{DEFAULT_SERVICE_URL}/crawl",
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "Ultron-CrawlerBridge"},
        )
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
            md_res = data.get("markdown") or data.get("content") or ""
            if md_res:
                if len(md_res) > max_chars:
                    md_res = md_res[:max_chars] + f"\n\n… [Truncated at {max_chars} characters]"
                _safe_call(player, "show_content", "CRAWLED WEBPAGE", md_res)
                return f"Crawled {url} via Crawl4AI ({len(md_res)} chars):\n\n{md_res}"
    except Exception as exc:
        failures.note("crawler_bridge.service_fetch", exc)
    return None


def _handle_crawl(url: str, selector: str, max_chars: int, player) -> str:
    if not url:
        from core import context_detector
        clip_url = context_detector.get_clipboard_target()
        if clip_url and clip_url.startswith(("http://", "https://")):
            url = clip_url
            _safe_call(player, "write_log", f"CRAWLER: Auto-detected URL from clipboard: {url}")
        else:
            return "Sir, please specify a valid URL to crawl, or copy a link to your clipboard."
    clean_url = url if url.startswith(("http://", "https://")) else f"https://{url}"
    parsed = urllib.parse.urlparse(clean_url)
    if not parsed.netloc:
        return f"Sir, '{url}' is not a valid web URL."

    _safe_call(player, "write_log", f"CRAWLER: Crawling {parsed.netloc}...")

    engine_status = _probe_engine()
    if engine_status["service_ready"]:
        svc_result = _crawl_via_service(clean_url, selector, max_chars, player)
        if svc_result:
            return svc_result

    try:
        html_content = _fetch_page(clean_url)
    except urllib.error.HTTPError as exc:
        return f"Sir, fetching {clean_url} returned HTTP error {exc.code}: {exc.reason}."
    except urllib.error.URLError as exc:
        return f"Sir, unable to reach {clean_url}: {exc.reason}."
    except Exception as exc:
        return f"Sir, failed to crawl {clean_url}: {exc}"

    md = _html_to_markdown(html_content, target_tag=selector or None)
    if not md.strip():
        return f"Sir, {clean_url} was reached, but no readable text content could be extracted."
    if len(md) > max_chars:
        md = md[:max_chars] + f"\n\n… [Truncated at {max_chars} characters]"

    actions_card = (
        f"{md}\n\n"
        "── QUICK ACTIONS ──\n"
        "• Say 'Summarize this page'\n"
        "• Say 'Extract key code from this'\n"
        "• Say 'Save these notes to memory'"
    )
    _safe_call(player, "show_content", f"PAGE CONTENT ({parsed.netloc})", actions_card)
    _safe_call(player, "write_log", f"CRAWLER: Extracted {len(md)} chars from {parsed.netloc}")
    return f"Successfully extracted {len(md)} characters of markdown from {clean_url}:\n\n{md}"


def run(parameters: dict, player=None, session_memory=None) -> str:
    """Execute crawler bridge actions safely."""
    try:
        action = str(parameters.get("action") or "status").strip().lower()
        url = str(parameters.get("url") or "").strip()
        raw_html = str(parameters.get("raw_html") or "").strip()
        selector = str(parameters.get("css_selector") or "").strip()
        max_chars = min(int(parameters.get("max_chars") or DEFAULT_MAX_CHARS), MAX_OUTPUT_LIMIT)
        if max_chars < 100:
            max_chars = DEFAULT_MAX_CHARS

        handlers = {
            "status": lambda: _handle_status(player),
            "markdown": lambda: _handle_markdown(raw_html, selector, max_chars, player),
            "crawl": lambda: _handle_crawl(url, selector, max_chars, player),
        }
        if action in handlers:
            return handlers[action]()
        return f"Sir, unknown action '{action}'. Supported actions are 'crawl', 'status', and 'markdown'."
    except Exception as exc:
        failures.note("crawler_bridge.run", exc)
        return f"Sir, crawler bridge encountered an error: {type(exc).__name__}: {exc}"
