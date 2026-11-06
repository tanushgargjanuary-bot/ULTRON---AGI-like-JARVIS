"""A local stand-in for any OpenAI-compatible model server.

WHY THIS EXISTS
    "Live providers were not verified" is true and unsatisfying: no key, no
    network, and contacting a vendor from a test is the wrong thing to do
    anyway. But the thing that actually breaks is not the vendor — it is the
    transport: SSE framing split across chunks, a tool call arriving as deltas,
    a 401 arriving as HTML, a stream that stops mid-sentence, a timeout. None of
    that needs a vendor to reproduce, and all of it can be checked here.

    So: a real HTTP server, speaking the documented protocol, that a real
    provider talks to over a real socket. The model is fake; the transport is
    not.

USED BY
    scripts/verify_provider.py     manual run, prints what each scenario did
    tests/test_live_transport.py   the same scenarios as assertions

    server = FakeProvider().start()
    server.base_url            -> http://127.0.0.1:<port>/v1
    server.requests            -> every request body it received
    server.stop()

BEHAVIOURS, chosen by the model name the client asks for
    echo            streams a short answer in several SSE chunks
    slow            the same, with a delay between chunks
    tools           first request returns a tool call, later requests answer
    truncate        closes the stream in the middle of a word
    garbage         sends bytes that are not SSE at all
    unauth          401 with an HTML body, the way a proxy does
    ratelimit       429 with Retry-After
    boom            500
    notfound        404 "model not found"
    vision-ok       accepts an image part
    vision-no       400 "this model does not support image input"
    silent          closes without sending anything
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _chunk(payload: dict) -> bytes:
    return b"data: " + json.dumps(payload).encode() + b"\n\n"


def _text_chunk(text: str, index: int = 0) -> bytes:
    return _chunk({"id": "chatcmpl-1", "object": "chat.completion.chunk",
                   "created": int(time.time()), "model": "fake",
                   "choices": [{"index": 0, "delta": {"content": text},
                                "finish_reason": None}]})


def _tool_chunk(name: str, arguments: str, index: int = 0) -> bytes:
    return _chunk({"id": "chatcmpl-1", "object": "chat.completion.chunk",
                   "created": int(time.time()), "model": "fake",
                   "choices": [{"index": 0, "delta": {"tool_calls": [{
                       "index": index, "id": f"call_{name}", "type": "function",
                       "function": {"name": name, "arguments": arguments}}]},
                       "finish_reason": None}]})


DONE = b"data: [DONE]\n\n"


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # -- plumbing ---------------------------------------------------------
    def log_message(self, *_args):
        pass                                    # keep the test output readable

    def _send_json(self, code: int, payload: dict, headers: dict | None = None):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, code: int, body: bytes, ctype: str,
                   headers: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            self._send_json(200, {"data": [{"id": "echo"}, {"id": "tools"},
                                           {"id": "vision-ok"}]})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            self._send_json(400, {"error": "bad request body"})
            return

        server: FakeProvider = self.server.owner          # type: ignore[attr-defined]
        server.requests.append({"path": self.path,
                                "auth": self.headers.get("Authorization", ""),
                                "body": body})

        model = str(body.get("model") or "")
        messages = body.get("messages") or []
        has_image = "image_url" in json.dumps(messages)

        if server.api_key and not self.headers.get("Authorization", "").endswith(server.api_key):
            self._send_text(401, b"<html>unauthorized</html>", "text/html")
            return

        if model.startswith("unauth"):
            self._send_text(401, b"<html>unauthorized</html>", "text/html")
            return
        if model.startswith("ratelimit"):
            self._send_json(429, {"error": {"message": "slow down"}},
                            {"Retry-After": "2"})
            return
        if model.startswith("boom"):
            self._send_json(500, {"error": {"message": "internal"}})
            return
        if model.startswith("notfound"):
            self._send_json(404, {"error": {"message": "model not found"}})
            return

        if model.startswith("vision-no") and has_image:
            self._send_text(400, json.dumps({"error": {
                "message": "this model does not support image input"}}).encode(),
                "application/json")
            return

        if not body.get("stream"):
            message: dict = {"role": "assistant", "content": "pong"}
            finish = "stop"
            # The "tools" model has to be able to answer a NON-streamed request
            # too, or a caller that asks once and gets no tool call cannot tell
            # "this server has no tools" from "this server only speaks SSE".
            if model.startswith("tools") and not any(
                    m.get("role") == "tool" for m in messages):
                message = {"role": "assistant", "content": "",
                           "tool_calls": [{"id": "call-1", "type": "function",
                                           "function": {"name": "open_app",
                                                        "arguments": "{\"app_name\": \"spotify\"}"}}]}
                finish = "tool_calls"
            self._send_json(200, {"id": "chatcmpl-1", "object": "chat.completion",
                                  "choices": [{"index": 0, "message": message,
                                               "finish_reason": finish}]})
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        try:
            self._stream(model, messages, server)
        except (BrokenPipeError, ConnectionResetError):
            pass
        server.finished.append(model)

    def _write(self, data: bytes):
        # chunked transfer encoding, one write per event: this is what a real
        # server does, and it is what makes SSE framing bugs reproducible.
        self.wfile.write(b"%x\r\n" % len(data) + data + b"\r\n")
        self.wfile.flush()

    def _stream(self, model: str, messages: list, server: "FakeProvider"):
        if model.startswith("silent"):
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
            return

        if model.startswith("garbage"):
            self._write(b"this is not an event stream\n")
            self._write(DONE)
            return

        if model.startswith("truncate"):
            self._write(_text_chunk("The answer is"))
            self.wfile.write(b"0\r\n\r\n")          # stop mid-sentence
            self.wfile.flush()
            return

        if model.startswith("tools"):
            already_called = any(m.get("role") == "tool" for m in messages)
            if not already_called:
                self._write(_tool_chunk("open_app", '{"app_name": '))
                self._write(_tool_chunk("open_app", '"spotify"}', index=0))
                self._write(DONE)
                return
            for piece in ("Spotify", " is", " opening."):
                self._write(_text_chunk(piece))
            self._write(DONE)
            return

        if model.startswith("slow"):
            for piece in ("One", " moment", ",", " please."):
                self._write(_text_chunk(piece))
                time.sleep(0.05)
            self._write(DONE)
            return

        if model.startswith("vision"):
            self._write(_text_chunk("ok"))
            self._write(DONE)
            return

        for piece in ("Hello", ",", " sir.", " All", " systems", " nominal."):
            self._write(_text_chunk(piece))
            if server.chunk_delay:
                time.sleep(server.chunk_delay)
        self._write(DONE)


class FakeProvider:
    """A running server. `base_url` is what the provider is pointed at."""

    def __init__(self, api_key: str = "", chunk_delay: float = 0.0):
        self.api_key = api_key
        self.chunk_delay = chunk_delay
        self.requests: list[dict] = []
        self.finished: list[str] = []
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._httpd.owner = self                     # type: ignore[attr-defined]
        self._httpd.daemon_threads = True
        self._thread: threading.Thread | None = None

    # -- lifecycle --------------------------------------------------------
    def start(self) -> "FakeProvider":
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread:
            self._thread.join(timeout=5)

    def __enter__(self) -> "FakeProvider":
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.stop()

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def config(self, model: str = "echo", **extra) -> dict:
        """A provider config pointing at this server."""
        out = {"base_url": self.base_url, "model": model, "api_key": self.api_key}
        out.update(extra)
        return out


if __name__ == "__main__":                          # manual poke
    with FakeProvider() as srv:
        print("base_url:", srv.base_url)
        print("requests so far:", len(srv.requests))
