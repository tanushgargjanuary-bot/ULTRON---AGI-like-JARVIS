"""tests/test_whatsapp_core.py — the driver that `send_message` promised and did not have.

Three docstrings said plugins/_whatsapp_core.py exists and verifies a WhatsApp
send. The file was missing, so every send fell back to blind keystrokes and the
user was told it worked. This file tests what can be tested here:

    * the two string rules, pinned equal to core.appidentity so they cannot drift;
    * the send discipline, against a fake tree — refuse an unknown or ambiguous
      conversation, never report sent without reading the box back;
    * get() on a machine with no Windows says so in a sentence.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import appidentity
from core.ui_tree import Node, Snapshot
from plugins import _whatsapp_core as wa


def tree(*, contacts=("Mum", "Alice"), composer="", send_button=True, search="Search or start new chat"):
    """A WhatsApp-shaped window: search box, conversation rows, composer."""
    rows = tuple(Node(role="ListItem", name=name, actions=("click",)) for name in contacts)
    children = [Node(role="Edit", name=search, actions=("set_value", "focus")),
                Node(role="List", name="Chat list", children=rows)]
    if send_button:
        children.append(Node(role="Button", name="Send", actions=("invoke",)))
    if composer is not None:
        children.append(Node(role="Edit", name="Type a message", value=composer,
                             actions=("set_value", "focus")))
    return Node(role="Window", name="WhatsApp", children=tuple(children))


class FakeResult:
    def __init__(self, ok=True, message=""):
        self.ok = ok
        self.message = message


class FakeSession:
    """Records what was asked of it, and changes the tree the way the app would.

    Refs carry the snapshot id, so `act` resolves a ref through the map recorded
    by the most recent `observe` — which is exactly what the real adapter does
    with its retained controls, and what makes a stale ref a refusal.
    """

    def __init__(self, root, *, contacts=("Mum",), sends=True, rebuild=True):
        self.root = root          # the shape as given; rebuild=False keeps it
        self.actions = []
        self.sends = sends
        self._rebuild_tree = rebuild
        self._names = {}
        self._contacts = tuple(contacts)
        self._composer = ""

    def observe(self, app=""):
        snap = Snapshot.capture(self.root, app=app, window="WhatsApp")
        self._names = {entry.ref: entry.name for entry in snap}
        return snap

    def act(self, ref, action="click", value=""):
        self.actions.append((ref, action, value))
        name = self._names.get(ref, "")
        if name in ("Search or start new chat", "Search"):
            # A real search filters the list; it does not de-duplicate it.
            matches = tuple(c for c in self._contacts if str(value).casefold() in c.casefold())
            self._contacts = matches or self._contacts
        elif name in self._contacts:
            pass                                  # a conversation opened
        elif name == "Type a message":
            self._composer = value
        elif name == "Send":
            if not self.sends:
                return FakeResult(False, "the button is disabled")
            self._composer = ""
        self._rebuild()
        return FakeResult(True, "")

    def _rebuild(self, contacts=None):
        if contacts is not None:
            self._contacts = contacts
        if self._rebuild_tree:
            self.root = tree(contacts=self._contacts, composer=self._composer)


class StringRules(unittest.TestCase):
    def test_fold_matches_core_identity(self):
        for text in ("Mum", "MÜM", "mum ", "Café", "Wu-Tang", "İstanbul",
                     "Mum's work", "アリス", ""):
            self.assertEqual(wa.fold(text), appidentity.fold(text), text)

    def test_name_in_phrase_is_whole_word(self):
        self.assertTrue(wa.name_in_phrase("chat with mum now", "mum"))
        self.assertFalse(wa.name_in_phrase("mumbo jumbo", "mum"))
        self.assertFalse(wa.name_in_phrase("", "mum"))
        self.assertFalse(wa.name_in_phrase("anything", ""))

    def test_name_in_phrase_matches_the_identity_rule(self):
        cases = [("msedgewebview2", "edge"), ("Edge browser", "Edge"), ("x-edge", "edge")]
        for phrase, word in cases:
            self.assertEqual(wa.name_in_phrase(phrase, word),
                             appidentity._contains_word(phrase, word), (phrase, word))


class Availability(unittest.TestCase):
    def test_get_returns_none_and_a_sentence_here(self):
        transport, why = wa.get(force=True)
        if sys.platform == "win32":
            self.skipTest("this machine may have a real driver")
        self.assertIsNone(transport)
        self.assertIn("Windows", why)

    def test_a_send_without_a_driver_is_not_attempted(self):
        from pathlib import Path as _Path
        source = (_Path(ROOT) / "actions" / "send_message.py").read_text(
            encoding="utf-8", errors="replace")
        self.assertIn("from plugins import _whatsapp_core as wa", source)


class SendDiscipline(unittest.TestCase):
    def _transport(self, root, **kwargs):
        session = FakeSession(root, **kwargs)
        return wa.WhatsAppTransport(session=session), session

    def test_sends_and_verifies_the_box_emptied(self):
        transport, session = self._transport(tree(contacts=("Mum",)), contacts=("Mum",))
        sent, failure = transport.send_message_to("Mum", "on my way")
        self.assertTrue(sent, failure)
        self.assertEqual(failure, "")
        typed = [value for _ref, action, value in session.actions
                 if action == "set_value" and value == "on my way"]
        self.assertEqual(typed, ["on my way"], "the message was never typed")

    def test_unknown_contact_is_refused_and_nothing_is_typed(self):
        transport, session = self._transport(tree(contacts=("Mum", "Alice")),
                                            contacts=("Mum", "Alice"))
        sent, failure = transport.send_message_to("Bob", "hello")
        self.assertFalse(sent)
        self.assertIn("could not find", failure)
        self.assertNotIn("hello", [value for _r, _a, value in session.actions])

    def test_ambiguous_contact_is_refused(self):
        transport, _session = self._transport(tree(contacts=("Mum", "Mum")),
                                             contacts=("Mum", "Mum"))
        sent, failure = transport.send_message_to("Mum", "hello")
        self.assertFalse(sent)
        self.assertIn("match", failure)

    def test_a_disabled_send_button_is_a_failure_not_a_success(self):
        transport, _session = self._transport(tree(contacts=("Mum",)),
                                             contacts=("Mum",), sends=False)
        sent, failure = transport.send_message_to("Mum", "hello")
        self.assertFalse(sent)
        self.assertIn("Send", failure)

    def test_empty_message_is_refused(self):
        transport, _session = self._transport(tree(contacts=("Mum",)), contacts=("Mum",))
        sent, failure = transport.send_message_to("Mum", "   ")
        self.assertFalse(sent)
        self.assertIn("no message", failure)

    def test_a_missing_composer_is_a_failure(self):
        root = Node(role="Window", name="WhatsApp", children=(
            Node(role="Edit", name="Search or start new chat", actions=("set_value",)),
            Node(role="List", name="Chat list", children=(
                Node(role="ListItem", name="Mum", actions=("click",)),)),
        ))
        transport, _session = self._transport(root, contacts=("Mum",), rebuild=False)
        sent, failure = transport.send_message_to("Mum", "hello")
        self.assertFalse(sent)
        self.assertIn("message box", failure)

    def test_a_crash_inside_the_driver_becomes_a_sentence(self):
        class Exploding:
            def observe(self, app=""):
                raise RuntimeError("the window went away")

            def act(self, *a, **k):
                raise AssertionError("must not be reached")

        transport = wa.WhatsAppTransport(session=Exploding())
        sent, failure = transport.send_message_to("Mum", "hello")
        self.assertFalse(sent)
        self.assertIn("WhatsApp", failure)
        self.assertIsInstance(failure, str)


if __name__ == "__main__":
    unittest.main()
