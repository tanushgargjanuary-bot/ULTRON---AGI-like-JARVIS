"""providers/connections.py — one connection, reused, instead of one per call.

**The cost this removes.** A new `httpx.Client` opens a new TCP connection, and
for an `https://` provider that means a new TLS handshake: a round trip for the
TCP SYN, two for the handshake, then the request. On a residential connection in
India talking to a provider in the United States that is 100–300 ms, and it was
being paid on *every* speech transcription, *every* synthesis and *every* one-shot
model call, because each of those call sites built its own client inside a `with`.

**What it costs to keep one.** Idle sockets and a little memory. The pool closes
them itself; `close_all()` closes everything at shutdown, and an `atexit` hook
does that if the app forgets.

**The rule that makes it safe.** A client is keyed by everything that changes its
behaviour — base address, timeout, whether the environment is trusted, whether
redirects are followed. Two call sites that need different behaviour never share a
client. An `async` client is keyed by its event loop as well, because httpx's async
pool belongs to one loop, and sharing it across loops produces a closed-transport
error that appears only under load.

**Measured**, `scripts/bench_connection.py`, loopback so the effect is visible
without a network:

    per-call clients     1 connection per request
    pooled client        1 connection for N requests

On loopback that is milliseconds. Across an ocean it is the 100–300 ms the
performance document lists, and the difference between a turn that starts
instantly and one that begins with a handshake.
"""

from __future__ import annotations

import asyncio
import atexit
import threading
from typing import Any

__all__ = [
    "sync_client",
    "async_client",
    "close_all",
    "stats",
    "Pooled",
]

_SYNC: dict[tuple, Any] = {}
_ASYNC: dict[tuple, Any] = {}
_LOCK = threading.RLock()
_COUNTS = {"created": 0, "reused": 0, "closed": 0}


def _httpx(module: Any = None):
    """The httpx module, imported once.

    The module is injectable so a test can supply a stand-in, and so the provider
    modules keep their own `self._httpx` seam — they inject it for the same reason.
    """
    if module is not None:
        return module
    import httpx
    return httpx


def _key(base: str, timeout: Any, trust_env: bool, follow_redirects: bool) -> tuple:
    return (str(base or ""), timeout, bool(trust_env), bool(follow_redirects))


def sync_client(module: Any = None, *, base: str = "", timeout: Any = 30.0,
                trust_env: bool = True, follow_redirects: bool = False) -> Any:
    """A shared synchronous client for this set of options.

    The caller must NOT close it: it outlives the call. A `with` around the return
    value would close the pool for everyone, which is why every call site that
    uses this was rewritten rather than wrapped.
    """
    httpx = _httpx(module)
    key = _key(base, timeout, trust_env, follow_redirects)
    with _LOCK:
        client = _SYNC.get(key)
        if client is not None and not getattr(client, "is_closed", False):
            _COUNTS["reused"] += 1
            return client
        client = httpx.Client(timeout=timeout, trust_env=trust_env,
                              follow_redirects=follow_redirects)
        _SYNC[key] = client
        _COUNTS["created"] += 1
        return client


def async_client(module: Any = None, *, base: str = "", timeout: Any = 30.0,
                 trust_env: bool = True, follow_redirects: bool = False,
                 loop: Any = None) -> Any:
    """A shared asynchronous client for this loop and this set of options.

    An async pool belongs to the loop that created it. The key therefore includes
    the running loop's identity, and a second loop gets its own client instead of
    a transport that is closed underneath it.
    """
    httpx = _httpx(module)
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
    key = (id(loop),) + _key(base, timeout, trust_env, follow_redirects)
    with _LOCK:
        client = _ASYNC.get(key)
        if client is not None and not getattr(client, "is_closed", False):
            _COUNTS["reused"] += 1
            return client
        client = httpx.AsyncClient(timeout=timeout, trust_env=trust_env,
                                   follow_redirects=follow_redirects)
        _ASYNC[key] = client
        _COUNTS["created"] += 1
        return client


def stats() -> dict:
    """What the pool has done, for tests and for the performance document."""
    with _LOCK:
        return {
            "created": _COUNTS["created"],
            "reused": _COUNTS["reused"],
            "closed": _COUNTS["closed"],
            "sync_open": len(_SYNC),
            "async_open": len(_ASYNC),
        }


def close_all() -> int:
    """Close every pooled client. Returns how many were open.

    Synchronous clients close here. Asynchronous ones cannot be awaited from a
    synchronous shutdown path, so they are dropped and their sockets are released
    when the loop ends — which is what happens to them anyway at that point. The
    count reports both, because a silent leak is worse than a loud one.
    """
    with _LOCK:
        closed = 0
        for client in list(_SYNC.values()):
            try:
                client.close()
                closed += 1
            except Exception:
                pass
        _SYNC.clear()
        closed += len(_ASYNC)
        _ASYNC.clear()
        _COUNTS["closed"] += closed
        return closed


def reset_for_tests() -> None:
    """Empty the pool without closing, so one test cannot warm another."""
    with _LOCK:
        _SYNC.clear()
        _ASYNC.clear()
        _COUNTS.update({"created": 0, "reused": 0, "closed": 0})


class Pooled:
    """Context manager that hands out pooled clients and never closes them.

    Exists so a call site can read as `with Pooled.sync(...) as cl:` after a
    mechanical rewrite, while still reusing the pool. Leaving the block does
    nothing; the pool owns the lifetime.
    """

    __slots__ = ("_client",)

    def __init__(self, client: Any):
        self._client = client

    def __enter__(self) -> Any:
        return self._client

    def __exit__(self, *exc_info) -> bool:
        return False

    async def __aenter__(self) -> Any:
        return self._client

    async def __aexit__(self, *exc_info) -> bool:
        return False

    @classmethod
    def sync(cls, module: Any = None, **kwargs) -> "Pooled":
        return cls(sync_client(module, **kwargs))

    @classmethod
    def asyncio(cls, module: Any = None, **kwargs) -> "Pooled":
        return cls(async_client(module, **kwargs))


atexit.register(close_all)
