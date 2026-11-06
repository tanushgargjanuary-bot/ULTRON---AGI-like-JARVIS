"""core/trie.py — a prefix tree for "what could they be about to say?".

WHERE IT IS USED
    Two places, both of them keystroke-path:

      1. The HUD's command line completes names as they are typed. A linear
         scan over every installed app, tool and stored key per keystroke is
         ~300 string starts-with checks; a trie makes it a walk of `len(prefix)`
         pointer hops regardless of how many candidates exist.
      2. The app resolver's prefix tier ("chrom" → Chrome, Chromium, Chrome
         Remote Desktop) asks the same question in a different clothes.

COMPLEXITY, PRECISELY
    insert  O(len(key))
    lookup  O(len(prefix))
    complete O(len(prefix) + k) where k is the number of results returned,
              because the subtree walk stops as soon as `limit` items are
              collected — the usual mistake is to traverse the whole subtree and
              then sort, which turns a constant into O(n log n) for nothing.

IMPLEMENTATION NOTE
    Every traversal here is iterative. A trie over file paths on a deep install
    can be hundreds of levels deep, and CPython's default recursion limit is
    1000: a recursive `complete()` is the kind of code that works for a year
    and then takes the app down on one unusual path.
"""

from __future__ import annotations

from collections.abc import Iterator

_END = "\x00"          # sentinel key that cannot appear in a word


class Trie:
    """Weighted prefix tree. Higher weight sorts first within a prefix."""

    __slots__ = ("_root", "_size")

    def __init__(self, items=None) -> None:
        self._root: dict = {}
        self._size = 0
        if items:
            for item in items:
                if isinstance(item, tuple) and len(item) == 2:
                    key, weight = item
                else:
                    key, weight = item, 1.0
                self.insert(str(key), weight)

    def __len__(self) -> int:
        return self._size

    def __contains__(self, key: str) -> bool:
        node = self._walk(str(key))
        return node is not None and _END in node

    def insert(self, key: str, weight: float = 1.0) -> None:
        """Add `key`. Re-inserting the same key keeps the HIGHEST weight.

        Keeping the maximum rather than the latest means a key that was typed
        once by accident cannot bury one the user picks every day.
        """
        key = str(key)
        if not key:
            return
        node = self._root
        for char in key:
            node = node.setdefault(char, {})
        if _END not in node:
            self._size += 1
            node[_END] = float(weight)
        else:
            node[_END] = max(float(node[_END]), float(weight))

    def _walk(self, prefix: str):
        node = self._root
        for char in prefix:
            node = node.get(char)
            if node is None:
                return None
        return node

    def complete(self, prefix: str, limit: int = 10) -> list[tuple[str, float]]:
        """[(key, weight)] for keys starting with `prefix`, best first.

        Depth-first with a bounded frontier rather than a full traversal: the
        walk stops as soon as `limit` results are in hand, which is what makes
        this usable per keystroke.
        """
        if limit <= 0:
            return []
        node = self._walk(prefix)
        if node is None:
            return []

        found: list[tuple[str, float]] = []
        stack: list[tuple[str, dict]] = [(prefix, node)]
        while stack and len(found) < limit:
            text, current = stack.pop()
            if _END in current:
                found.append((text, current[_END]))
            # Push children in reverse so the alphabetically earliest is popped
            # first; sentinel is excluded because it is not a character.
            for char in sorted(current, reverse=True):
                if char == _END:
                    continue
                stack.append((text + char, current[char]))
        found.sort(key=lambda pair: (-pair[1], pair[0]))
        return found[:limit]

    def keys(self) -> Iterator[str]:
        stack: list[tuple[str, dict]] = [("", self._root)]
        while stack:
            text, node = stack.pop()
            if _END in node:
                yield text
            for char, child in node.items():
                if char != _END:
                    stack.append((text + char, child))

    def longest_prefix(self, text: str) -> str:
        """The longest stored key that `text` starts with — used to complete
        mid-command ("open chro" + Tab) without a full search."""
        node = self._root
        best = ""
        walked = ""
        for char in text:
            node = node.get(char)
            if node is None:
                break
            walked += char
            if _END in node:
                best = walked
        return best
