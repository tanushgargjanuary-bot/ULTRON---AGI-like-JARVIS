"""net_check — the three network questions worth asking without a browser.

Resolve a name, check whether a TCP port answers, and read a URL's headers and TLS
certificate. All three are bounded: a short timeout, a single request, and no
follow-on traffic.

SAFETY, because this is the dual-use one
    A port checker that will aim anywhere is a scanning tool. This one refuses a
    public target unless the user has opted in for the session, so "check my dev
    server" works and "scan this host" does not happen by accident. DNS and HTTP
    are read-only and always allowed.
"""

import socket
import ssl
import urllib.request

PLUGIN = {
    "name": "net_check",
    "description": (
        "Answers three network questions: resolve a hostname (DNS A/AAAA), check "
        "whether one TCP port on a host is open, or fetch a URL's HTTP status, "
        "headers and TLS certificate. Use it for 'is my server up', 'what does this "
        "host resolve to', or 'when does this certificate expire'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "dns | port | headers"},
            "host": {"type": "STRING", "description": "Hostname or IP"},
            "port": {"type": "NUMBER", "description": "For action=port"},
            "url": {"type": "STRING", "description": "For action=headers"},
            "allow_public": {"type": "BOOLEAN",
                             "description": "Set true to test a port on a public host"},
        },
        "required": ["action"],
    },
    "tier": "SENSOR",
}

TIMEOUT = 3.0
_PRIVATE_HEADS = ("127.", "10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.",
                  "172.2", "172.30.", "172.31.", "0.0.0.0", "::1", "localhost")


def _is_private(host):
    lowered = str(host or "").strip().lower()
    return any(lowered == head or lowered.startswith(head) for head in _PRIVATE_HEADS)


def _dns(host):
    if not host:
        return "I need a hostname to resolve."
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        return f"{host} does not resolve: {exc}"
    addresses = sorted({info[4][0] for info in infos})
    return f"{host} resolves to: " + ", ".join(addresses[:8])


def _port(host, port, allow_public):
    if not host or not port:
        return "I need a host and a port."
    port = int(port)
    if not 0 < port < 65536:
        return f"{port} is not a valid port."
    if not _is_private(host) and not allow_public:
        return (f"{host} is not on this machine or a private network, so I will not "
                "probe it. Say allow_public if you own it and meant that.")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(TIMEOUT)
            code = sock.connect_ex((host, port))
    except OSError as exc:
        return f"Could not reach {host}:{port} — {exc}"
    return (f"{host}:{port} is open." if code == 0
            else f"{host}:{port} did not answer (code {code}).")


def _headers(url):
    if not str(url or "").startswith(("http://", "https://")):
        return "Give me a URL that starts with http:// or https://"
    request = urllib.request.Request(url, method="GET",
                                     headers={"User-Agent": "Ultron-net-check"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            status = response.status
            headers = dict(response.headers)
            scheme = url.split(":", 1)[0]
            cert_note = ""
            if scheme == "https":
                cert = response.fp.raw._sock.getpeercert() if hasattr(
                    response.fp, "raw") else None
                if cert:
                    cert_note = f" Certificate expires {cert.get('notAfter', 'unknown')}."
    except Exception as exc:                                    # noqa: BLE001
        return f"{url} did not answer: {type(exc).__name__}: {exc}"
    interesting = [k for k in ("Content-Type", "Server", "Content-Length",
                               "Cache-Control", "Strict-Transport-Security") if k in headers]
    shown = "; ".join(f"{k}: {headers[k][:80]}" for k in interesting) or "no notable headers"
    return f"{url} answered {status}.{cert_note} {shown}"


def run(parameters, player=None, session_memory=None):
    action = str(parameters.get("action") or "dns").strip().lower()
    try:
        if action == "dns":
            return _dns(str(parameters.get("host") or ""))
        if action == "port":
            return _port(str(parameters.get("host") or ""),
                         parameters.get("port"),
                         bool(parameters.get("allow_public")))
        if action == "headers":
            return _headers(str(parameters.get("url") or ""))
    except Exception as exc:                                    # noqa: BLE001
        return f"net_check failed: {type(exc).__name__}: {exc}"
    return "I can resolve a name, check a port, or read a URL's headers."
