"""core/routing.py — which provider and model answers which kind of request.

THE DECISIONS THIS IMPLEMENTS (all already agreed)
    * MARK is provider-independent: conversation, evolution/repair work and the
      independent critic can each point at a different provider and model.
    * The user can change them BY VOICE mid-conversation ("use Groq", "switch the
      critic to Gemma 4", "go local for now") and the change applies to the next
      request without restarting the session.
    * A fallback ladder ends at a local model. A fallback that would cost money
      or change the privacy terms of the data is NEVER taken silently.
    * Limits are per ACCOUNT, PROJECT, ORGANISATION or MODEL — not per key. N
      keys are one budget until proven otherwise, so quota is tracked per quota
      group and never multiplied by the number of keys.
    * Rotating keys or accounts to escape a limit is not a design goal and is not
      implemented here.

WHAT IS DELIBERATELY NOT IN THIS FILE
    No provider names, no model names, no endpoints, no prices, no key handling.
    Everything is derived from what the user configured, so a provider nobody
    here has heard of routes exactly as well as the famous ones, and no default
    silently ships. Nothing here opens a socket.

WHY A PARSER AND NOT A TOOL
    "Use Groq" is a control instruction, not a task. Round-tripping it through
    the model costs a request from the very quota it is trying to conserve, and
    the model can only confirm what this module already knows. Parsing it locally
    is instant, deterministic and testable.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Callable, Iterable, Optional


class Purpose(str, Enum):
    CONVERSATION = "conversation"
    EVOLUTION = "evolution"
    CRITIC = "critic"


@dataclass(frozen=True)
class Provider:
    """One configured provider. `quota_group` is what limits are really about."""

    name: str
    quota_group: str = ""
    local: bool = False
    paid: bool = False
    shares_data: bool = False        # may train on the content — cloud rows carry True until verified

    def __post_init__(self) -> None:
        if not self.quota_group:
            object.__setattr__(self, "quota_group", self.name.lower())

    @property
    def key(self) -> str:
        return self.name.lower()


@dataclass(frozen=True)
class Route:
    provider: str
    model: str = ""

    def describe(self) -> str:
        return f"{self.provider}/{self.model}" if self.model else self.provider


@dataclass(frozen=True)
class Fallback:
    route: Route
    reason: str = ""


class Refusal(Exception):
    """A switch that the policy will not perform, with a reason to speak."""


# ─────────────────────────────────────────────────────────────────────────────
#  Quota groups
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class QuotaGroup:
    """What one account/project is allowed, as configured by the user."""

    name: str
    requests_per_day: Optional[int] = None
    tokens_per_day: Optional[int] = None
    used_requests: int = 0
    used_tokens: int = 0
    blocked_until: float = 0.0
    day: str = ""

    def roll(self, today: str) -> None:
        if self.day != today:
            self.day = today
            self.used_requests = 0
            self.used_tokens = 0

    def exhausted(self, now: float) -> bool:
        if self.blocked_until > now:
            return True
        if self.requests_per_day is not None and self.used_requests >= self.requests_per_day:
            return True
        if self.tokens_per_day is not None and self.used_tokens >= self.tokens_per_day:
            return True
        return False


class QuotaLedger:
    """Usage per quota group. Cheap, thread-safe, no persistence of its own."""

    def __init__(self, clock: Callable[[], float] | None = None,
                 today: Callable[[], str] | None = None) -> None:
        self._lock = threading.RLock()
        self._groups: dict[str, QuotaGroup] = {}
        self._clock = clock or time.monotonic
        self._today = today or (lambda: time.strftime("%Y-%m-%d"))

    def configure(self, name: str, requests_per_day: Optional[int] = None,
                  tokens_per_day: Optional[int] = None) -> QuotaGroup:
        with self._lock:
            group = self._groups.get(name) or QuotaGroup(name=name)
            group.requests_per_day = requests_per_day
            group.tokens_per_day = tokens_per_day
            self._groups[name] = group
            return group

    def record(self, group: str, requests: int = 1, tokens: int = 0) -> None:
        with self._lock:
            entry = self._groups.setdefault(group, QuotaGroup(name=group))
            entry.roll(self._today())
            entry.used_requests += max(0, int(requests))
            entry.used_tokens += max(0, int(tokens))

    def block_for(self, group: str, seconds: float) -> None:
        """A 429 with Retry-After: honour it rather than trying the next key."""
        with self._lock:
            entry = self._groups.setdefault(group, QuotaGroup(name=group))
            entry.blocked_until = self._clock() + max(0.0, float(seconds))

    def available(self, group: str) -> bool:
        with self._lock:
            entry = self._groups.get(group)
            if entry is None:
                return True
            entry.roll(self._today())
            return not entry.exhausted(self._clock())

    def snapshot(self) -> dict[str, dict]:
        with self._lock:
            out = {}
            for name, group in self._groups.items():
                group.roll(self._today())
                out[name] = {
                    "used_requests": group.used_requests,
                    "used_tokens": group.used_tokens,
                    "requests_per_day": group.requests_per_day,
                    "tokens_per_day": group.tokens_per_day,
                    "blocked_for": max(0.0, round(group.blocked_until - self._clock(), 1)),
                }
            return out


# ─────────────────────────────────────────────────────────────────────────────
#  The routing table
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class RoutingTable:
    providers: dict[str, Provider] = field(default_factory=dict)
    routes: dict[str, Route] = field(default_factory=dict)
    fallbacks: list[Fallback] = field(default_factory=list)
    ledger: QuotaLedger = field(default_factory=QuotaLedger)
    allow_paid_fallback: bool = False
    allow_data_sharing_fallback: bool = False
    allow_local_fallback: bool = False

    # ── configuration ───────────────────────────────────────────────────────
    def add_provider(self, provider: Provider) -> Provider:
        self.providers[provider.key] = provider
        return provider

    def provider(self, name: str) -> Optional[Provider]:
        return self.providers.get(str(name or "").strip().lower())

    def set_route(self, purpose: Purpose | str, provider: str, model: str = "") -> Route:
        provider_name = str(provider or "").strip()
        found = self.provider(provider_name)
        if found is None:
            raise Refusal(f"{provider_name} is not one of your configured providers")
        route = Route(provider=found.name, model=str(model or "").strip())
        self.routes[Purpose(purpose).value] = route
        return route

    def route_for(self, purpose: Purpose | str) -> Optional[Route]:
        return self.routes.get(Purpose(purpose).value)

    # ── selection with the quota and privacy rules ──────────────────────────
    def candidates(self, purpose: Purpose | str) -> list[Route]:
        """The primary route, then the fallbacks that are ALLOWED right now."""
        primary = self.route_for(purpose)
        ordered: list[Route] = []
        if primary is not None:
            ordered.append(primary)
        ordered += [fallback.route for fallback in self.fallbacks]
        allowed: list[Route] = []
        for route in ordered:
            if route in allowed:
                continue
            provider = self.provider(route.provider)
            if provider is None:
                continue
            if not self.ledger.available(provider.quota_group):
                continue
            own_route = primary is not None and route == primary
            if not own_route:
                # A fallback may not silently cost money, change who sees the
                # data, or move the conversation onto this machine. Skipping
                # it is the whole point; the caller can say so.
                if provider.paid and not self.allow_paid_fallback:
                    continue
                if provider.shares_data and not self.allow_data_sharing_fallback:
                    continue
                if provider.local and not self.allow_local_fallback:
                    continue
            allowed.append(route)
        return allowed

    def choose(self, purpose: Purpose | str) -> Route:
        options = self.candidates(purpose)
        if not options:
            raise Refusal(
                "no provider is available for this request — every route is "
                "exhausted, or the only fallbacks left would cost money, share "
                "the data, or run on this machine without permission"
            )
        return options[0]

    def record_use(self, route: Route, requests: int = 1, tokens: int = 0) -> None:
        provider = self.provider(route.provider)
        if provider is not None:
            self.ledger.record(provider.quota_group, requests, tokens)

    def record_limit(self, route: Route, retry_after: float) -> None:
        """Honour a 429 on the whole quota group, not just the key that hit it."""
        provider = self.provider(route.provider)
        if provider is not None:
            self.ledger.block_for(provider.quota_group, retry_after)


# ─────────────────────────────────────────────────────────────────────────────
#  Voice and typed switching
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SwitchRequest:
    provider: str = ""
    model: str = ""
    purpose: Purpose | None = None
    local_only: bool = False
    raw: str = ""

    def describe(self) -> str:
        if self.local_only:
            return "local only"
        target = self.provider or ""
        if self.model:
            target = f"{target} {self.model}".strip()
        scope = f" for {self.purpose.value}" if self.purpose else ""
        return f"{target}{scope}"


_USE_WORDS = ("use", "switch", "switch to", "change to", "go", "go with", "run on",
              "route", "route to", "set", "set the", "put")

_PURPOSE_WORDS = {
    "conversation": Purpose.CONVERSATION,
    "chat": Purpose.CONVERSATION,
    "talking": Purpose.CONVERSATION,
    "evolution": Purpose.EVOLUTION,
    "repair": Purpose.EVOLUTION,
    "repairs": Purpose.EVOLUTION,
    "background": Purpose.EVOLUTION,
    "critic": Purpose.CRITIC,
    "reviewer": Purpose.CRITIC,
    "review": Purpose.CRITIC,
    "judge": Purpose.CRITIC,
}

# Bare "local" is deliberately absent: "the local shop closes at six" is not a
# routing instruction. Only phrasings that can only mean the local model count.
_LOCAL_WORDS = ("local model", "local only", "locally", "on device", "on-device",
                "offline", "go local", "run local", "use local", "switch to local")


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s.+-]", " ", str(text or "").lower())).strip()


def _match_provider(text: str, providers: Iterable[Provider]) -> Optional[str]:
    """Longest configured provider name that appears as words in the sentence."""
    best: Optional[str] = None
    best_len = 0
    for provider in providers:
        name = _normalise(provider.name)
        if not name:
            continue
        pattern = r"\b" + re.escape(name).replace(r"\ ", r"[\s_-]+") + r"\b"
        if re.search(pattern, text) and len(name) > best_len:
            best, best_len = provider.name, len(name)
    return best


def _match_model(text: str, models: Iterable[str]) -> Optional[str]:
    best: Optional[str] = None
    best_len = 0
    for model in models:
        name = _normalise(model)
        if not name:
            continue
        if re.search(r"\b" + re.escape(name).replace(r"\ ", r"[-\s_]+") + r"\b", text):
            if len(name) > best_len:
                best, best_len = model, len(name)
    return best


def parse_switch(text: str, providers: Iterable[Provider] = (),
                 models: Iterable[str] = ()) -> Optional[SwitchRequest]:
    """Read a switching instruction, or return None if this is not one.

    Only configured names are recognised. A sentence that mentions a provider
    the user has not added is not a switch — it is probably a question about it,
    and the model should answer that instead.
    """
    normalised = _normalise(text)
    if not normalised:
        return None

    provider_list = list(providers)
    purpose = None
    for word, mapped in _PURPOSE_WORDS.items():
        if re.search(r"\b" + re.escape(word) + r"\b", normalised):
            purpose = mapped
            break

    local = None
    for word in _LOCAL_WORDS:
        if re.search(r"\b" + re.escape(_normalise(word)).replace(r"\ ", r"[\s-]+") + r"\b",
                     normalised):
            local = word
            break

    provider = _match_provider(normalised, provider_list)
    model = _match_model(normalised, models)

    looks_like_command = any(
        re.match(r"^" + re.escape(word) + r"\b", normalised) for word in _USE_WORDS
    )
    if not (looks_like_command or (provider and "switch" in normalised)):
        return None
    if not (provider or model or local):
        return None

    return SwitchRequest(
        provider=provider or "",
        model=model or "",
        purpose=purpose,
        local_only=bool(local) and not provider,
        raw=text,
    )


def apply_switch(table: RoutingTable, request: SwitchRequest,
                 purposes: Iterable[Purpose] = ()) -> list[tuple[Purpose, Route]]:
    """Apply a parsed switch. Raises `Refusal` with something worth saying."""
    if request.local_only:
        local_providers = [p for p in table.providers.values() if p.local]
        if not local_providers:
            raise Refusal("no local model is configured, so I cannot go local")
        provider = local_providers[0]
        model = ""
    else:
        provider = table.provider(request.provider) if request.provider else None
        if request.provider and provider is None:
            raise Refusal(f"{request.provider} is not one of your configured providers")
        if provider is None:
            # A model-only switch keeps whichever provider is already answering.
            existing = table.route_for(request.purpose or Purpose.CONVERSATION)
            if existing is None:
                raise Refusal("say which provider to use; none is set yet")
            provider, model = table.provider(existing.provider), request.model or existing.model
            if provider is None:
                raise Refusal(f"{existing.provider} is not configured any more")
        else:
            model = request.model
            if not model:
                current = table.route_for(request.purpose or Purpose.CONVERSATION)
                if current is not None and current.provider == provider.name:
                    model = current.model

    targets = [request.purpose] if request.purpose else list(purposes or [Purpose.CONVERSATION])
    applied: list[tuple[Purpose, Route]] = []
    for purpose in targets:
        route = table.set_route(purpose, provider.name, model or "")
        applied.append((Purpose(purpose), route))
    return applied


def describe(table: RoutingTable) -> str:
    """For the status panel: what answers what, and what is left today."""
    lines = []
    for purpose in Purpose:
        route = table.route_for(purpose)
        lines.append(f"{purpose.value}: {route.describe() if route else 'not set'}")
    if table.fallbacks:
        lines.append("fallbacks: " + " -> ".join(f.route.describe() for f in table.fallbacks))
    for group, usage in table.ledger.snapshot().items():
        lines.append(
            f"quota[{group}]: {usage['used_requests']}"
            f"{'/' + str(usage['requests_per_day']) if usage['requests_per_day'] else ''} requests"
            f", {usage['used_tokens']} tokens"
            + (f", blocked {usage['blocked_for']}s" if usage["blocked_for"] else "")
        )
    return "\n".join(lines)


def with_route(table: RoutingTable, purpose: Purpose | str, provider: str,
               model: str = "") -> RoutingTable:
    """Copy-on-write variant, for callers that keep an immutable config."""
    clone = replace(table, providers=dict(table.providers), routes=dict(table.routes),
                    fallbacks=list(table.fallbacks), ledger=table.ledger)
    clone.set_route(purpose, provider, model)
    return clone
