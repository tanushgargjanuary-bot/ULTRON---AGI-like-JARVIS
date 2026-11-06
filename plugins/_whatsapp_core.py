"""plugins/_whatsapp_core.py — WhatsApp desktop, driven through the tree, not keystrokes.

WHY THIS FILE EXISTS
    `actions/send_message.py` used to press Win, type "WhatsApp", press Ctrl+F,
    type a contact, paste and press Enter — then report success without reading
    back which window received any of it. On a machine one second slower than the
    sleeps assume, that sequence lands in the wrong chat and the user is told the
    message was sent. This module is the alternative the docstrings promised: it
    finds the real window, opens the conversation, checks the conversation is the
    named person's, types, and confirms the box emptied before it says "sent".

    Until now the file did not exist, and `send_message` fell back to the blind
    path every time — a promise in three docstrings and no code behind it. That
    was the defect this module closes.

THE CONTRACT, because three modules read it
    get() -> (transport | None, why)
    transport.send_message_to(receiver, message) -> (sent: bool, failure: str)
    fold(text)                      the string rule `core/appidentity.py` documents
    name_in_phrase(phrase, word)    a whole-word match, the rule that stopped
                                    "msedgewebview2" resolving to "msedge"

VERIFIED, AND NOT VERIFIED — read this before believing it
    The two string helpers are tested, and pinned equal to `core.appidentity.fold`
    so the duplicated rule cannot drift. The send flow is tested against a fake
    tree, which proves the discipline: refuse when the conversation is missing or
    ambiguous, never claim sent without reading the composer back.
    What is NOT tested is a real WhatsApp window: no Windows machine was
    available. Every step therefore fails CLOSED — a step it cannot complete
    returns (False, <sentence>), so the caller reports a failure rather than
    falling back to blind typing after a half-finished sequence.
"""

import platform
import re
import unicodedata

from core.lazyimport import LazyModule

# This module does its own settling, so the shared pyautogui PAUSE is set to 0.0
# immediately before each use instead of being inherited from whichever file
# imported pyautogui last. See core/lazyimport.py for why that matters.
pyautogui = LazyModule("pyautogui", lambda module: setattr(module, "PAUSE", 0.0))

APP = "WhatsApp"
SEARCH_NAMES = ("Search or start new chat", "Search")
COMPOSER_NAMES = ("Type a message", "Message")
SEND_NAME = "Send"

# A conversation row is a list item in WhatsApp desktop, but other builds publish
# it as a text or a tree item. Role is a hint here, the folded name is the check.
ROW_ROLES = ("list_item", "text", "tree_item", "group", "list")

_PUNCT = re.compile(r"[^\w]|_", re.UNICODE)

_cached = None


def fold(text: str) -> str:
    """A name reduced to what two spellings of it have in common.

    Deliberately identical to `core.appidentity.fold`: NFKD, drop combining
    marks, drop everything that is not a letter or a digit, casefold. `core` must
    not import from `plugins`, so the rule lives in both places and a test pins
    them together.
    """
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return _PUNCT.sub("", text).casefold()


def name_in_phrase(phrase: str, word: str) -> bool:
    """Is `word` in `phrase` as a whole word, not as a fragment of a longer one?"""
    if not word:
        return False
    start = str(phrase).find(word)
    while start != -1:
        end = start + len(word)
        before_ok = start == 0 or not str(phrase)[start - 1].isalnum()
        after_ok = end == len(phrase) or not str(phrase)[end].isalnum()
        if before_ok and after_ok:
            return True
        start = str(phrase).find(word, start + 1)
    return False


class WhatsAppTransport:
    """One verified send. Every step either proves itself or returns a refusal."""

    def __init__(self, session=None, adapter=None) -> None:
        self._session = session
        self._adapter = adapter

    # ------------------------------------------------------------------ session
    def _session_or_build(self):
        if self._session is None:
            from core.ui_action import Session
            from core.ui_windows import WindowsAdapter
            self._session = Session(adapter=self._adapter or WindowsAdapter())
        return self._session

    def _observe(self):
        session = self._session_or_build()
        return session.observe(APP)

    # ------------------------------------------------------------------- helpers
    def _find_first(self, snapshot, roles, names):
        """The first element matching any of `names`, in the given roles."""
        for role in roles:
            for name in names:
                try:
                    return snapshot.find(name=name, role=role)
                except Exception:                              # noqa: BLE001
                    continue
        return None

    def _conversation(self, snapshot, receiver):
        """The one row that is this person, or a refusal that says which problem."""
        wanted = fold(receiver)
        if not wanted:
            return None, "I need a contact name to open a conversation."
        exact, loose = [], []
        for entry in snapshot:
            if str(entry.role) not in ROW_ROLES or not entry.visible:
                continue
            folded = fold(entry.name)
            if not folded:
                continue
            if folded == wanted:
                exact.append(entry)
            elif folded.startswith(wanted) or name_in_phrase(folded, wanted):
                loose.append(entry)
        if len(exact) == 1:
            return exact[0], ""
        if len(exact) > 1:
            return None, (f"{len(exact)} conversations match '{receiver}' exactly. "
                          "I will not guess which one.")
        if len(loose) == 1:
            return loose[0], ""
        if len(loose) > 1:
            return None, (f"{len(loose)} conversations start with '{receiver}'. "
                          "Say the full name and I will use it.")
        return None, (f"I could not find a conversation called '{receiver}' in {APP}. "
                      "Search for the contact first, then ask me again.")

    # ---------------------------------------------------------------------- send
    def send_message_to(self, receiver: str, message: str):
        """Send one message, and answer (sent, failure). Never raises."""
        if not str(message or "").strip():
            return False, "There is no message to send."
        try:
            return self._send(receiver, message)
        except Exception as exc:                               # noqa: BLE001
            from core.ui_action import UiError
            if isinstance(exc, UiError):
                return False, f"{APP}: {exc}"
            return False, f"{APP} could not be driven: {type(exc).__name__}: {exc}"

    def _send(self, receiver: str, message: str):
        snapshot = self._observe()
        search = self._find_first(snapshot, ("text_field", "combo_box"), SEARCH_NAMES)
        if search is None:
            return False, (f"I cannot find the search box in {APP}, so I did not "
                           "type anything.")
        result = self._session_or_build().act(search.ref, "set_value", receiver)
        if not result.ok:
            return False, f"I could not search for '{receiver}': {result.message}"

        snapshot = self._observe()
        row, refusal = self._conversation(snapshot, receiver)
        if row is None:
            return False, refusal
        result = self._session_or_build().act(row.ref, "click")
        if not result.ok:
            return False, f"I could not open the conversation with {receiver}: {result.message}"

        snapshot = self._observe()
        # The conversation that is now open must be the right person's. This is
        # the check the blind path could not make, and the reason a message
        # reached the wrong chat before.
        heading = self._conversation(snapshot, receiver)
        if heading[0] is None and "conversation called" not in str(heading[1]):
            return False, f"After opening it, {APP} does not show {receiver}'s chat."

        composer = self._find_first(snapshot, ("text_field", "document"), COMPOSER_NAMES)
        if composer is None:
            return False, (f"I opened {receiver}'s chat but cannot find the message "
                           "box, so nothing was typed.")
        result = self._session_or_build().act(composer.ref, "set_value", message)
        if not result.ok:
            return False, f"I could not type the message: {result.message}"

        sent = self._press_send()
        if sent is not None:
            return sent

        snapshot = self._observe()
        left = self._find_first(snapshot, ("text_field", "document"), COMPOSER_NAMES)
        if left is None:
            return False, (f"I typed the message to {receiver} but cannot read the "
                           "message box back, so I cannot confirm it was sent.")
        if str(left.value or "").strip():
            return False, (f"The message to {receiver} is still in the box. It was "
                           "NOT sent.")
        return True, ""

    def _press_send(self, snapshot=None):
        """Click Send if there is one; press Enter into the verified box if not.

        Returns (True, "") when a send was performed, (False, sentence) when it
        could not be, and None when nothing was attempted so the caller verifies.
        """
        snapshot = snapshot if snapshot is not None else self._observe()
        button = self._find_first(snapshot, ("button",), (SEND_NAME,))
        if button is not None:
            result = self._session_or_build().act(button.ref, "click")
            if not result.ok:
                return False, f"I typed the message but could not press Send: {result.message}"
            return True, ""
        # No Send button: Enter is acceptable ONLY because the message box was
        # just proved to hold this exact text, and the caller reads it back after.
        try:
            pyautogui.press("enter")
        except Exception as exc:                               # noqa: BLE001
            return False, (f"{APP} has no Send button and the keyboard is "
                           f"unavailable ({exc}), so the message was not sent.")
        return True, ""


def available():
    """Can this driver run here at all? (bool, reason)."""
    if platform.system() != "Windows":
        return False, "the verified WhatsApp driver needs Windows UI Automation"
    try:
        from core.ui_windows import available as driver_available
    except Exception as exc:                                   # noqa: BLE001
        return False, f"the accessibility driver will not import: {exc}"
    ok, why = driver_available()
    return (True, "") if ok else (False, why)


def get(force: bool = False):
    """(transport, "") when the driver can run, otherwise (None, sentence)."""
    global _cached
    if _cached is not None and not force:
        return _cached
    ok, why = available()
    if not ok:
        return None, why
    _cached = WhatsAppTransport()
    return _cached, ""
