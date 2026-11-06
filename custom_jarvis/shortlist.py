"""BM25 ranking: pick the few stored rules that match what was just said.

The problem this solves is small and real. Ultron keeps lessons, tools and
documents, and it must show the *relevant* handful. Counting shared words is the
usual answer and it is wrong twice over: a word in every entry ("tests") carries
no signal, and a rare word that appears three times in one entry carries more.

BM25 fixes both with two standard ideas — inverse document frequency, and a
length correction — and it is thirty lines of arithmetic, so it needs no model,
no download and no state. `rank()` is the only public function.
"""

from __future__ import annotations

import math
import re
from typing import Any, Sequence

_WORD = re.compile(r"[a-z0-9]+")

# Words that appear in everything, so they rank nothing. Deliberately short: a
# long stop-list is a guess about English, and a wrong guess deletes signal.
_STOP = frozenset(
    """a an and are as at be been by for from had has have in into is it its of
    on or that the their them then there these this to was were what when which
    will with you your""".split()
)

K1 = 1.5   # how fast extra occurrences stop helping
B = 0.75   # how strongly long entries are penalised


def terms(text: Any) -> list[str]:
    """The words worth ranking: lowercase, longer than one character, not stop words."""
    return [word for word in _WORD.findall(str(text or "").lower())
            if len(word) > 1 and word not in _STOP]


def rank(query: Any, documents: Sequence[dict], *, text_key: str = "text",
         id_key: str = "id", limit: int = 5, k1: float = K1, b: float = B) -> list[dict]:
    """Return the documents that share meaningful words with `query`, best first.

    Each result is `{"id", "score", "document"}`. A document with no shared word
    is left out rather than scored zero: an empty result is the honest answer to
    an unrelated question, and it is what stops advice being noise.
    """
    asked = terms(query)
    rows = [row for row in documents if isinstance(row, dict)]
    if not asked or not rows:
        return []

    counted = [(row, terms(row.get(text_key, ""))) for row in rows]
    total = len(counted)
    average = (sum(len(words) for _row, words in counted) / total) or 1.0

    seen_in = {}
    for _row, words in counted:
        for word in set(words):
            seen_in[word] = seen_in.get(word, 0) + 1

    results = []
    for row, words in counted:
        if not words:
            continue
        length = len(words)
        frequencies = {}
        for word in words:
            frequencies[word] = frequencies.get(word, 0) + 1
        score = 0.0
        for word in asked:
            times = frequencies.get(word, 0)
            if not times:
                continue
            idf = math.log(1.0 + (total - seen_in[word] + 0.5) / (seen_in[word] + 0.5))
            score += idf * (times * (k1 + 1.0)) / (
                times + k1 * (1.0 - b + b * length / average))
        if score > 0.0:
            results.append({"id": row.get(id_key), "score": round(score, 4),
                            "document": row})

    results.sort(key=lambda item: (-item["score"], str(item["id"])))
    return results[: max(1, int(limit))]
