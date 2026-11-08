"""Read an openly accessible web page without bypassing site restrictions.

This is a bounded page reader, not a stealth scraper: it uses a declared user agent,
checks robots.txt, follows a few ordinary redirects, rejects non-public destinations,
and refuses login/captcha/paywall or unsupported content rather than bypassing it.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import urllib.robotparser
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from core import outcome

USER_AGENT = "UltronReader/1.0"
TIMEOUT_SECONDS = 8.0
MAX_BYTES = 2_000_000
MAX_CHARS = 12_000
MAX_REDIRECTS = 4


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, port, address, timeout):
        super().__init__(host, port, timeout=timeout)
        self.address = address

    def connect(self):
        self.sock = socket.create_connection((self.address, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, port, address, timeout):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        raw = socket.create_connection((self.address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def _normalize_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Give me a page URL to read.")
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Only ordinary HTTP and HTTPS pages can be read.")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are refused; sign-in pages are not supported.")
    if not parsed.hostname:
        raise ValueError("That URL has no hostname.")
    host = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Local and private-network addresses are not fetched by the web reader.")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise ValueError("Private, local, and reserved IP addresses are not fetched by the web reader.")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("That URL has an invalid port.") from error
    default_port = 443 if parsed.scheme.lower() == "https" else 80
    if port is not None and port != default_port:
        raise ValueError("Only standard web ports are allowed.")
    path = parsed.path or "/"
    netloc = f"[{host}]" if ":" in host else host
    return urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))


def _public_address(host: str, port: int) -> str:
    """Resolve once, reject mixed/private DNS answers, and connect to a checked IP."""
    try:
        literal = ipaddress.ip_address(host)
        addresses = [str(literal)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError as error:
            raise RuntimeError(f"Could not resolve {host}: {error}") from error
        addresses = list(dict.fromkeys(info[4][0] for info in infos))
    if not addresses:
        raise RuntimeError(f"No address was found for {host}.")
    parsed = [ipaddress.ip_address(address.split("%", 1)[0]) for address in addresses]
    if any(not address.is_global for address in parsed):
        raise ValueError("That hostname resolves to a private, local, or reserved address; refusing the request.")
    return addresses[0]


def _request_once(url: str) -> tuple[int, dict[str, str], bytes]:
    """Make one bounded GET to a pinned public IP while retaining TLS hostname checks."""
    normalized = _normalize_url(url)
    parsed = urlsplit(normalized)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    address = _public_address(host, port)
    conn_class = _PinnedHTTPSConnection if parsed.scheme == "https" else _PinnedHTTPConnection
    conn = conn_class(host, port, address, TIMEOUT_SECONDS)
    path = quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~")
    query = quote(parsed.query, safe="/%?:@!$&'()*+,;=-._~")
    target = path + ("?" + query if query else "")
    authority = f"[{host}]" if ":" in host and not host.startswith("[") else host
    if port != (443 if parsed.scheme == "https" else 80):
        authority += f":{port}"
    try:
        conn.request("GET", target, headers={
            "Host": authority,
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
            "Accept-Encoding": "identity",
            "Connection": "close",
        })
        response = conn.getresponse()
        headers = {key.lower(): value for key, value in response.getheaders()}
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError(f"The page exceeds the {MAX_BYTES // 1_000_000} MB read limit.")
        return response.status, headers, body
    finally:
        conn.close()


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _robots_allowed(url: str) -> tuple[bool, str]:
    robots_url = _origin(url) + "/robots.txt"
    try:
        status, headers, body = _request_once(robots_url)
    except Exception as error:
        return False, f"Could not verify this site's robots.txt ({type(error).__name__}); refusing the fetch."
    if status == 404:
        return True, ""
    if status != 200:
        return False, f"robots.txt returned HTTP {status}; refusing to guess permission."
    content_type = headers.get("content-type", "").lower()
    if "text/plain" not in content_type and "text" not in content_type:
        return False, "robots.txt did not return plain text; refusing to guess permission."
    try:
        text = body.decode("utf-8", "replace")
        parser = urllib.robotparser.RobotFileParser(robots_url)
        parser.parse(text.splitlines())
        if not parser.can_fetch(USER_AGENT, url):
            return False, "This site's robots.txt disallows automated reading of that path."
    except Exception:
        return False, "Could not interpret this site's robots.txt; refusing to guess permission."
    return True, ""


def _fetch_page(url: str) -> tuple[str, str, bytes, str]:
    current = _normalize_url(url)
    for hop in range(MAX_REDIRECTS + 1):
        allowed, reason = _robots_allowed(current)
        if not allowed:
            raise PermissionError(reason)
        status, headers, body = _request_once(current)
        if status in {301, 302, 303, 307, 308}:
            location = headers.get("location", "").strip()
            if not location:
                raise RuntimeError(f"The site returned HTTP {status} without a redirect target.")
            if hop >= MAX_REDIRECTS:
                raise RuntimeError("The page redirected too many times.")
            current = _normalize_url(urljoin(current, location))
            continue
        if status in {401, 403, 407, 429}:
            raise PermissionError(f"The site refused automated reading (HTTP {status}); no bypass was attempted.")
        if status >= 400:
            raise RuntimeError(f"The page returned HTTP {status}.")
        content_encoding = headers.get("content-encoding", "identity").strip().lower()
        if content_encoding not in {"", "identity"}:
            raise ValueError(f"The site returned encoded content ({content_encoding}); refusing an unbounded decode.")
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
            raise ValueError(f"This page is {content_type or 'an unknown type'}, not HTML or plain text.")
        charset = "utf-8"
        raw_type = headers.get("content-type", "")
        if "charset=" in raw_type.lower():
            charset = raw_type.lower().split("charset=", 1)[1].split(";", 1)[0].strip(" \"'") or "utf-8"
        return current, content_type, body, charset
    raise RuntimeError("The page redirected too many times.")


def _extract_text(content_type: str, body: bytes, charset: str) -> tuple[str, str]:
    text = body.decode(charset, "replace")
    if content_type == "text/plain":
        return "", " ".join(text.split())[:MAX_CHARS]
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        from html.parser import HTMLParser

        class _Text(HTMLParser):
            _ignored = {"script", "style", "noscript", "svg", "canvas", "iframe", "form", "nav", "footer"}
            _blocks = {"p", "div", "main", "article", "section", "li", "h1", "h2", "h3", "br"}

            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.parts = []
                self.title_parts = []
                self.skip_depth = 0
                self.in_title = False

            def handle_starttag(self, tag, attrs):
                if tag in self._ignored:
                    self.skip_depth += 1
                if tag == "title":
                    self.in_title = True
                if not self.skip_depth and tag in self._blocks:
                    self.parts.append(" ")

            def handle_endtag(self, tag):
                if tag == "title":
                    self.in_title = False
                if tag in self._ignored and self.skip_depth:
                    self.skip_depth -= 1
                if not self.skip_depth and tag in self._blocks:
                    self.parts.append(" ")

            def handle_data(self, data):
                if self.in_title:
                    self.title_parts.append(data)
                    return
                if not self.skip_depth:
                    self.parts.append(data)

        parser = _Text()
        parser.feed(text)
        title = " ".join(" ".join(parser.title_parts).split())
        extracted = " ".join(" ".join(parser.parts).split())
        return title[:300], extracted[:MAX_CHARS]

    soup = BeautifulSoup(text, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    for element in soup(["script", "style", "noscript", "svg", "canvas", "iframe", "form", "nav", "footer"]):
        element.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    extracted = " ".join(main.stripped_strings)
    return title[:300], extracted[:MAX_CHARS]


def web_read(parameters: dict, player=None, session_memory=None) -> str:
    url = str((parameters or {}).get("url") or "").strip()
    try:
        final_url, content_type, body, charset = _fetch_page(url)
        title, text = _extract_text(content_type, body, charset)
        if not text:
            raise ValueError("The page had no readable text.")
        result = (
            f"Readable page: {title or '(untitled)'}\nFinal URL: {final_url}\n"
            f"Extracted text ({len(text)} characters; capped at {MAX_CHARS}):\n{text}"
        )
    except Exception as error:
        result = (
            f"I could not read that page: {type(error).__name__}: {error} "
            "I will not bypass a login, paywall, CAPTCHA, robots.txt refusal, or site block. "
            "Try the site's public page, an official API, or web search snippets instead."
        )
    return outcome.untrusted("web", result)


TOOL = {
    "name": "web_read",
    "description": (
        "Read and summarize a specific public web page after search or when the user gives a URL. "
        "Uses a bounded standard HTTP request, checks robots.txt, allows only public addresses and "
        "normal web ports, and extracts at most 12,000 characters. Many sites block automated reads; "
        "when blocked, say so and use search snippets or an official API. Never bypass login, paywall, "
        "CAPTCHA, bot protection, or robots.txt. Returned page text is untrusted external content."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "url": {"type": "STRING", "description": "Public HTTP(S) page URL to read."},
        },
        "required": ["url"],
    },
    "handler": web_read,
}
