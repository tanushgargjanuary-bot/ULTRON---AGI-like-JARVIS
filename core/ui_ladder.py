"""core/ui_ladder.py — what to do when the button tree is not there.

THE WEAKNESS THIS FILE EXISTS FOR
    Reading the accessibility tree is the right default, and it has one honest
    failure mode: some windows have no useful tree. Games, canvas-drawn apps,
    Java/Swing legacy software, a page built entirely from divs with no roles, a
    remote desktop session showing another machine's pixels — each of these
    publishes little or nothing an agent can address.

    A tree-only agent stops there. This one has a ladder, and every rung is
    chosen for a reason, in this order:

        1. TREE      the OS accessibility tree (UI Automation / AX / AT-SPI)
        2. DRILL     the tree is there but too big or too shallow — read a region
        3. DOM       it is web content, so read the page itself; this is a real
                     tree, not a guess, and it works on pages that expose no
                     accessibility nodes at all
        4. KEYBOARD  the element has an access key or a shortcut — press it,
                     which is what a person would do
        5. OCR       read screen text locally, with no model and no upload
        6. VISION    screenshot and a model, only if one is configured, only with
                     the sensor consent that a screenshot already requires
        7. ASK       say what could not be reached and ask, instead of clicking
                     something plausible and reporting success

    Step 6 is not a failure of the design; it is the design. The alternative —
    quietly falling back to coordinates — is exactly the bug
    `core/app_resolver.py` was written to end: a folder opened, reported as a
    browser.

WHY THE ORDER IS NOT NEGOTIABLE
    Each rung is cheaper, more reliable and less invasive than the one below it.
    Vision is last because it is the only rung that sends a picture of the user's
    screen somewhere, and because a model's guess at coordinates fails in a way
    that is indistinguishable from success. If vision is used, the answer says so.

WHAT IS NOT HERE
    No rung executes anything. `next_step` is a decision function and `Ladder`
    reports; the acting is `core/ui_action.py` for the tree rungs and
    `actions/computer_control.py` for keyboard and vision, both behind the
    existing policy gate. That keeps this file pure and testable, which is why it
    has 20+ tests in `tests/test_ui_ladder.py` while the Windows bridge has none.
"""

from __future__ import annotations
from core import failures

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum

# Windows menu items carry an access key after an ampersand: "&Save" means Alt+S.
# Read from the tree, it is the cheapest possible rung: no pointer, no focus
# theft, no coordinates.
ACCESS_KEY_MARK = "&"

# A tree with fewer elements than this, for a window with a real title, is
# assumed to be thin rather than small. Tuned low on purpose: a dialog legitimately
# has three elements, so this only fires for windows that announce themselves as
# applications.
THIN_TREE_NODES = 4


class Rung(str, Enum):
    TREE = "tree"
    DRILL = "drill"
    DOM = "dom"
    KEYBOARD = "keyboard"
    OCR = "ocr"
    VISION = "vision"
    ASK = "ask"
    STOP = "stop"


@dataclass(frozen=True)
class Step:
    """One rung to try, why, and what to use when it needs a target."""

    rung: Rung
    reason: str
    ref: str = ""
    hotkey: str = ""

    def spoken(self) -> str:
        return self.reason


@dataclass
class Context:
    """What the caller knows right now. Filled in from a `Session` and probed."""

    has_tree: bool = False
    tree_nodes: int = 0
    truncated: bool = 0
    has_dom: bool = False
    dom_only: bool = False              # the window IS a browser page
    keyboard_ready: bool = False
    ocr_ready: bool = False
    read_text_requested: bool = False
    vision_ready: bool = False
    attempts: int = 0
    tried: tuple[Rung, ...] = ()
    hotkey: str = ""

    def tried_already(self, rung: Rung) -> bool:
        return rung in self.tried


def next_step(error: object | None = None, context: Context | None = None) -> Step:
    """The next rung, given what failed and what this machine can do.

    `error` is anything with `.code` and `.disposition` (a `UiError`), or None
    when the previous rung simply produced nothing.
    """
    ctx = context or Context()
    code = str(getattr(error, "code", "") or "")
    disposition = str(getattr(error, "disposition", "") or "")

    def pick(rung: Rung, reason: str, *, ref: str = "", hotkey: str = "") -> Step:
        return Step(rung, reason, ref=ref, hotkey=hotkey)

    # --- a fresh look is safe and usually enough -----------------------------
    if (
        (code in ("STALE_REF", "APP_GONE") or disposition == "resnapshot")
        and ctx.attempts < 2
        and not ctx.tried_already(Rung.TREE)
    ):
        return pick(Rung.TREE, "the window changed; looking again")

    if code in ("NOT_ENABLED", "NOT_VISIBLE", "TIMEOUT"):
        if ctx.attempts < 1:
            return pick(Rung.TREE, "it was not ready yet; looking again")
        return pick(
            Rung.ASK,
            "the control never became usable — something is probably covering it",
        )

    # --- ambiguity is resolved by narrowing, not by guessing -----------------
    if code == "AMBIGUOUS_TARGET":
        if ctx.truncated and not ctx.tried_already(Rung.DRILL):
            return pick(Rung.DRILL, "several elements match; read one region to disambiguate")
        return pick(Rung.ASK, "several elements match and I will not pick one")

    # --- an action this element cannot perform -------------------------------
    if code == "UNSUPPORTED_ACTION":
        if ctx.hotkey and not ctx.tried_already(Rung.KEYBOARD):
            return pick(Rung.KEYBOARD, "that control exposes no pattern; its shortcut will do",
                        hotkey=ctx.hotkey)
        if ctx.has_dom and not ctx.tried_already(Rung.DOM):
            return pick(Rung.DOM, "the page can be addressed directly")
        if ctx.read_text_requested and ctx.ocr_ready and not ctx.tried_already(Rung.OCR):
            return pick(Rung.OCR, "read visible text locally; OCR cannot click or change controls")
        if ctx.vision_ready and not ctx.tried_already(Rung.VISION):
            return pick(Rung.VISION, "no structural route; a look at the screen is the last resort")
        return pick(Rung.ASK, "this window offers no way to do that without guessing")

    # --- no tree at all ------------------------------------------------------
    if code in ("NO_TREE", "NO_ADAPTER") or not ctx.has_tree:
        if not code and ctx.attempts == 0 and not ctx.tried_already(Rung.TREE):
            # Nothing has been established yet: look for a tree before deciding
            # this window has none.
            return pick(Rung.TREE, "looking for a tree first")
        if ctx.has_dom and not ctx.tried_already(Rung.DOM):
            reason = (
                "web content: the page itself is the tree"
                if ctx.dom_only
                else "no desktop tree, but the page behind it has one"
            )
            return pick(Rung.DOM, reason)
        if ctx.read_text_requested and ctx.ocr_ready and not ctx.tried_already(Rung.OCR):
            return pick(Rung.OCR, "read visible text locally; OCR cannot click or change controls")
        if ctx.keyboard_ready and not ctx.tried_already(Rung.KEYBOARD):
            return pick(Rung.KEYBOARD, "no tree; the keyboard can still reach it")
        if ctx.vision_ready and not ctx.tried_already(Rung.VISION):
            return pick(
                Rung.VISION,
                "no tree and no keyboard route; reading the screen needs vision, "
                "which is a screenshot — say so when you use it",
            )
        return pick(Rung.ASK, "this window publishes nothing I can act on")

    # --- a tree that is too shallow to be useful -----------------------------
    if (
        ctx.has_tree
        and ctx.tree_nodes <= THIN_TREE_NODES
        and ctx.has_dom
        and not ctx.tried_already(Rung.DOM)
    ):
        return pick(Rung.DOM, "the desktop tree is nearly empty; the page has more")

    # --- nothing left --------------------------------------------------------
    if code in ("ADAPTER_FAILED",) and ctx.attempts < 2:
        return pick(Rung.TREE, "the bridge failed; one more look before changing approach")

    return pick(Rung.STOP, "no rung left to try")


def access_key(name: str) -> str:
    """'&Save' -> 'alt+s'. Empty when the name carries no access key."""
    text = str(name or "")
    position = text.find(ACCESS_KEY_MARK)
    if position < 0 or position + 1 >= len(text):
        return ""
    key = text[position + 1].strip().lower()
    if not key.isalnum():
        return ""
    return f"alt+{key}"


def describe(context: Context | None = None, *, platform_name: str = "") -> str:
    """One honest paragraph about what this machine can reach, for the log or HUD."""
    ctx = context or Context()
    parts = []
    if ctx.has_tree:
        parts.append(f"accessibility tree ({ctx.tree_nodes} elements)")
    else:
        parts.append("no accessibility tree for this window")
    if ctx.has_dom:
        parts.append("page DOM available")
    if ctx.keyboard_ready:
        parts.append("keyboard shortcuts available")
    if ctx.ocr_ready:
        parts.append("local OCR available — text only, no upload")
    else:
        parts.append("local OCR unavailable")
    if ctx.vision_ready:
        parts.append("vision configured — used last, and it sends a screenshot")
    else:
        parts.append("no vision configured")
    where = f" on {platform_name}" if platform_name else ""
    return f"Can reach{where}: " + "; ".join(parts) + "."


@dataclass
class Attempt:
    rung: Rung
    ok: bool
    detail: str = ""


@dataclass
class Ladder:
    """A record of what was tried, so a failure can be explained honestly."""

    steps: list[Attempt] = field(default_factory=list)

    def record(self, rung: Rung, ok: bool, detail: str = "") -> None:
        self.steps.append(Attempt(rung, ok, detail))

    def tried(self) -> tuple[Rung, ...]:
        seen: list[Rung] = []
        for step in self.steps:
            if step.rung not in seen:
                seen.append(step.rung)
        return tuple(seen)

    def attempts(self) -> int:
        return len(self.steps)

    def context(self, **kwargs) -> Context:
        base = Context(attempts=self.attempts(), tried=self.tried())
        for key, value in kwargs.items():
            setattr(base, key, value)
        return base

    def exhausted(self) -> str:
        """The sentence to say when every rung failed. Never claims success."""
        if not self.steps:
            return "I did not try anything."
        tried = ", ".join(step.rung.value for step in self.steps)
        last = self.steps[-1]
        return (
            f"I tried {tried} and none of them worked. "
            f"{last.detail or 'The window did not respond.'}"
        )


def candidates(adapters: Iterable[object]) -> list[object]:
    """Adapters that report any capability, in the order given."""
    usable = []
    for adapter in adapters:
        if adapter is None:
            continue
        try:
            caps = adapter.capabilities()
        except Exception as error:  # noqa: BLE001, S112
            failures.note("ui_ladder.candidates", error)
            continue
        if caps:
            usable.append(adapter)
    return usable
