"""scripts/bench_connection.py — the cost of opening a connection per call.

The performance document lists "warm connection" as an unmeasured lever worth
100–300 ms per turn. This measures the part that can be measured on any machine
without a network: **how many connections a call pattern opens**, and what that
costs when the server is local.

WHAT IS MEASURED
    A counting HTTP server on loopback. Ten requests, twice:

      per call    a fresh `httpx.Client` inside a `with`, which is what every
                  provider call site did before providers/connections.py
      pooled      the shared client from providers/connections.py

    Reported: connections accepted, median milliseconds per request.

WHAT IS NOT MEASURED, AND SAID SO
    A TLS handshake and a real round trip. Loopback has neither, so the numbers
    here are a floor, not the prize. The prize on a residential connection to a
    provider in another country is the 100–300 ms already listed; this script
    proves the *count* of handshakes removed, which is the part that is true
    everywhere.

USAGE
    python scripts/bench_connection.py
"""

from __future__ import annotations

import argparse
import http.server
import socket
import statistics
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class _Counter(http.server.ThreadingHTTPServer):
    """An HTTP server that counts the connections it accepted."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.accepted = 0
        self.lock = threading.Lock()

    def get_request(self):
        request, address = super().get_request()
        # Without this the measurement is about the server, not the client: a
        # keep-alive socket on loopback falls into the Nagle + delayed-ACK trap
        # and every request waits 40 ms. The first version of this script
        # reported "pooled is slower" because of exactly that, which is the
        # measurement being wrong, not the pool.
        try:
            request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass
        with self.lock:
            self.accepted += 1
        return request, address


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"      # keep-alive, so a pooled socket can be reused

    def do_GET(self):                   # noqa: N802 - the name is fixed by http.server
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):                  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass                            # a benchmark that prints request logs measures io


def run_per_call(url: str, rounds: int) -> tuple[int, float]:
    import httpx
    times = []
    for _ in range(rounds):
        started = time.perf_counter()
        with httpx.Client(timeout=10.0) as client:
            client.get(url)
        times.append((time.perf_counter() - started) * 1000.0)
    return rounds, statistics.median(times)


def run_pooled(url: str, rounds: int) -> tuple[int, float, dict]:
    from providers import connections
    connections.reset_for_tests()
    times = []
    for _ in range(rounds):
        started = time.perf_counter()
        client = connections.sync_client(timeout=10.0)
        client.get(url)
        times.append((time.perf_counter() - started) * 1000.0)
    counts = connections.stats()
    connections.close_all()
    return counts["created"], statistics.median(times), counts


def main() -> int:
    parser = argparse.ArgumentParser(description="connections per call, measured")
    parser.add_argument("--rounds", type=int, default=10)
    args = parser.parse_args()

    server = _Counter(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/probe"

    try:
        server.accepted = 0
        per_call_conns, per_call_ms = run_per_call(url, args.rounds)
        accepted_per_call = server.accepted

        server.accepted = 0
        pooled_conns, pooled_ms, counts = run_pooled(url, args.rounds)
        accepted_pooled = server.accepted
    finally:
        server.shutdown()
        server.server_close()

    print(f"requests: {args.rounds}   server: loopback HTTP/1.1 keep-alive")
    print()
    print(f"{'pattern':<16}{'connections':>14}{'median/request':>18}")
    print(f"{'per call':<16}{accepted_per_call:>14}{per_call_ms:>15.3f} ms")
    print(f"{'pooled':<16}{accepted_pooled:>14}{pooled_ms:>15.3f} ms")
    print()
    saved = accepted_per_call - accepted_pooled
    print(f"connections removed: {saved}")
    if accepted_pooled > 0:
        print(f"per-request saving on loopback: {per_call_ms - pooled_ms:+.3f} ms")
    print()
    print("Loopback has no TLS and no distance, so this is a floor. Each removed")
    print("connection removes one handshake; on a remote provider that is the")
    print("100-300 ms listed in docs/PERFORMANCE.md, per call.")
    print(f"pool stats: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
