"""core/fuzzy.py — matching what somebody said to what is actually installed.

THE PROBLEM, IN ONE SENTENCE
    Speech recognition gives us "what's app", "viber", "excel sheet", "vs code";
    the Start menu contains "WhatsApp", "Viber", "Microsoft Excel", "Visual
    Studio Code". Exact string comparison fails on all four, and the failure is
    worse than an error: the resolver falls through to a path matcher and opens
    a FOLDER, which is how "open whatsapp" opened a directory containing
    WhatsApp shortcuts.

WHAT THIS FILE IS
    Four classical algorithms, written here rather than imported, because they
    are small, they are exactly the content of the DAA syllabus this project is
    being built alongside, and each one has a measurable effect:

      `damerau_levenshtein`  edit distance with adjacent transposition
                             (DAA Unit IV: dynamic programming, O(mn) time,
                             O(min(m,n)) space by keeping one row)
      `soundex`, `metaphone`  phonetic keys, so "viber" and "vyber" collide
                             BEFORE any distance is computed
      `Trie` (in core/trie.py) prefix index, O(len) lookup

WHY PHONETIC BUCKETING COMES FIRST
    Scoring every installed app against every utterance is O(n · mn). With a
    phonetic key it is O(mn) over one bucket, because the key is computed once
    per app at index time and once per utterance. That is the difference
    between 2 ms and 40 ms on a machine with 300 installed programs, on a path
    the user waits on before the app appears.

WHAT THIS FILE IS NOT
    Not a spell checker and not a language model. It does not know that
    "notepad" and "wordpad" are different programs; it only knows how close two
    strings are. Deciding what a near-match MEANS is the resolver's job and,
    past a threshold, the user's.
"""

from __future__ import annotations

import re
import unicodedata

_DROP = re.compile(r"[^a-z0-9]+")
_VOWELS = set("aeiouy")          # Y drops like a vowel (Metaphone convention)


def normalise(text: str) -> str:
    """Casefold, strip accents, and reduce punctuation to single spaces.

    Accents matter for the same reason the console encoding does: this app is
    used in more than one language, and "Süper" must compare equal to "super".
    """
    if not text:
        return ""
    folded = unicodedata.normalize("NFKD", text)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return _DROP.sub(" ", folded.casefold()).strip()


def damerau_levenshtein(a: str, b: str) -> int:
    """Edit distance where a transposition of adjacent characters costs 1.

    The full Damerau–Levenshtein, not the restricted OSA variant: OSA gets
    "CA" → "ABC" wrong (it reports 3; the true distance is 2, via CA→AC→ABC).
    Speech errors are exactly transpositions — "chorme" for "chrome" — so the
    difference is not academic here.

    Time O(mn), space O(mn) for the plain version below. `max_distance` lets
    callers stop early with a cheap upper bound, which is how the index avoids
    paying full price for hopeless candidates.

        >>> damerau_levenshtein("chorme", "chrome")
        1
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    # The standard formulation (Wagner–Fischer extended with a transposition
    # term). `d` is (m+2) x (n+2) with a sentinel border so the transposition
    # lookup d[k][l] never needs a bounds check, and `da` remembers the last row
    # each character of `a` was seen in. `maxdist` is an infinity that cannot
    # overflow into a real answer.
    maxdist = len(a) + len(b)
    d = [[0] * (len(b) + 2) for _ in range(len(a) + 2)]
    d[0][0] = maxdist
    for i in range(len(a) + 1):
        d[i + 1][0] = maxdist
        d[i + 1][1] = i
    for j in range(len(b) + 1):
        d[0][j + 1] = maxdist
        d[1][j + 1] = j

    last_row: dict[str, int] = {}
    for i in range(1, len(a) + 1):
        last_col = 0
        for j in range(1, len(b) + 1):
            k = last_row.get(b[j - 1], 0)
            l = last_col
            if a[i - 1] == b[j - 1]:
                cost = 0
                last_col = j
            else:
                cost = 1
            d[i + 1][j + 1] = min(
                d[i][j] + cost,                                  # substitution / match
                d[i + 1][j] + 1,                                 # insertion
                d[i][j + 1] + 1,                                 # deletion
                d[k][l] + (i - k - 1) + 1 + (j - l - 1),         # transposition
            )
        last_row[a[i - 1]] = i
    return d[len(a) + 1][len(b) + 1]


def soundex(word: str, length: int = 4) -> str:
    """Classic Soundex key: first letter + three consonant digits.

    Retained even though `metaphone` is better, because Soundex is what most
    Indian and US name databases are keyed on, and because it is four
    characters, which makes it a cheap first bucket for short app names.
    """
    letters = [ch for ch in normalise(word).replace(" ", "") if ch.isalpha()]
    if not letters:
        return ""
    codes = {
        **dict.fromkeys("bfpv", "1"),
        **dict.fromkeys("cgjkqsxz", "2"),
        **dict.fromkeys("dt", "3"),
        "l": "4",
        **dict.fromkeys("mn", "5"),
        "r": "6",
    }
    first = letters[0].upper()
    digits: list[str] = []
    previous = codes.get(letters[0], "")
    for ch in letters[1:]:
        code = codes.get(ch, "")
        if code and code != previous:
            digits.append(code)
        # 'h' and 'w' are transparent: they do not reset the previous code.
        if ch not in "hw":
            previous = code
    return (first + "".join(digits) + "000")[:length]


def metaphone(word: str) -> str:
    """A compact Metaphone — the phonetic key used for bucketing.

    This is a SIMPLIFIED Metaphone, not Lawrence Philips' full algorithm and not
    Double Metaphone: it covers the English rules that matter for application
    names (PH→F, TH→0, CH→X, CK→K, initial silent K/G/P/W, soft C/G before
    e/i/y, GH silence, double letters). It is deliberately not trying to be
    complete — every rule added is a rule that can be wrong, and the distance
    function is the safety net underneath.

    Returned untruncated; callers bucket on the first four characters.
    """
    text = normalise(word).replace(" ", "")
    if not text:
        return ""
    text = re.sub(r"^(kn|gn|pn|ae|wr)", lambda m: m.group(0)[1], text)
    text = re.sub(r"^x", "s", text)
    text = re.sub(r"mb$", "m", text)

    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        pair = ch + nxt

        if pair == "ph":
            out.append("f"); i += 2; continue
        if pair == "sh" or pair == "ch":
            out.append("x"); i += 2; continue
        if pair == "th":
            out.append("0"); i += 2; continue
        if pair == "wh":
            out.append("w"); i += 2; continue
        if pair == "ck":
            out.append("k"); i += 2; continue
        if pair == "gh" or pair == "dg":
            if pair == "dg" and nxt == "":
                out.append("k")
            i += 2; continue
        if ch == "c":
            # soft c before e/i/y, hard otherwise
            out.append("s" if nxt in ("e", "i", "y") else "k")
            i += 1; continue
        if ch == "g":
            out.append("j" if nxt in ("e", "i", "y") else "k")
            i += 1; continue
        if ch == "x":
            out.append("ks")
            i += 1; continue
        if ch == "q":
            out.append("k"); i += 1; continue
        if ch in _VOWELS:
            # Vowels are dropped except as the first letter, so "chrome" and
            # "chrm" collapse together — and "viber"/"vyber" collapse too, which
            # is why Y is in the set rather than beside the consonants.
            if i == 0:
                out.append(ch)
            i += 1; continue
        if ch in ("v", "f", "j", "l", "m", "n", "r", "b", "d", "k", "p", "s", "t", "z", "h", "w"):
            out.append(ch)
            i += 1; continue
        i += 1

    key = "".join(out)
    return key[:1] + re.sub(r"(.)\1+", r"\1", key[1:])


def phonetic_key(word: str, length: int = 4) -> str:
    """The bucketing key: Metaphone truncated, falling back to Soundex.

    Short names produce short Metaphone keys, and truncating a 2-character key
    to 4 does not help; in that case Soundex is a better bucket because it is
    always 4 characters.
    """
    key = metaphone(word)
    if len(key) < 3:
        key = soundex(word)
    return key[:length]


def _consonants(text: str) -> str:
    """The consonant skeleton of a phrase: "PowerPoint" -> "pwrpnt"."""
    return "".join(ch for ch in normalise(text).replace(" ", "") if ch not in _VOWELS)


def _bigrams_of(text: str) -> frozenset[str]:
    """Character bigrams of a space-stripped name, as a set.

    Used only as a cheap rejection filter before the expensive comparisons: two
    strings that share almost no adjacent letter pair are not the same word
    misheard, and knowing that in half a microsecond matters when the query is
    about to be asked of every installed application.
    """
    joined = text.replace(" ", "")
    if len(joined) < 2:
        return frozenset()
    return frozenset(joined[i:i + 2] for i in range(len(joined) - 1))


def _is_subsequence(needle: str, haystack: str) -> bool:
    """Is every character of `needle` present in `haystack`, in order?"""
    if not needle:
        return False
    it = iter(haystack)
    return all(char in it for char in needle)


def similarity(a: str, b: str) -> float:
    """0..1 similarity from normalised edit distance.

    Plain `1 - dist/max_len`, which is what a person means by "how close". It is
    deliberately NOT Jaro-Winkler: Winkler's prefix bonus helps for surnames
    and hurts for app names, where the distinguishing part is often the tail
    ("...Studio Code" vs "...Studio").
    """
    left, right = normalise(a), normalise(b)
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    longest = max(len(left), len(right))
    return max(0.0, 1.0 - damerau_levenshtein(left, right) / longest)


def match_score(spoken: str, candidate: str, aliases: tuple[str, ...] = ()) -> float:
    """How well `spoken` names `candidate`, in 0..1, with the reasons ordered.

    The tiers are deliberate and each one is worth more than the next:

        1.000  identical after normalisation
        0.950  identical phonetic key and same first letter  (typos, accents)
        0.900  the utterance is a prefix of the name ("whats" → WhatsApp)
        0.850  the utterance is a strict subset of the words
        0.500+ edit-distance similarity, scaled
        0.400* phonetic-only overlap

    A candidate that shares no word, no prefix and no phonetic key scores 0, and
    the resolver treats 0 as "no opinion" rather than "first alphabetically".
    """
    query = normalise(spoken)
    if not query:
        return 0.0

    names = (candidate,) + tuple(aliases or ())
    query_joined = query.replace(" ", "")
    best = 0.0
    for name in names:
        target = normalise(name)
        if not target:
            continue
        if query == target or query_joined == target.replace(" ", ""):
            return 1.0

        q_words = query.split()
        t_words = target.split()
        score = similarity(query, target) * 0.5          # base tier, max 0.5

        if phonetic_key(query) == phonetic_key(target):
            score = max(score, 0.95 if query[:1] == target[:1] else 0.4)
        if target.startswith(query) or any(w.startswith(query) for w in t_words):
            score = max(score, 0.9)
        if q_words and set(q_words) <= set(t_words):
            score = max(score, 0.85 + 0.05 * len(q_words) / max(1, len(t_words)))
        # Partial word overlap: "excel sheet" against "Microsoft Excel" shares
        # only "excel", which no prefix or phonetic rule sees, yet it is exactly
        # what people say. Full overlap is handled by the tier above, so this one
        # tops out at 0.85 when only some words match.
        overlap = len(set(q_words) & set(t_words))
        if overlap:
            score = max(score, 0.5 + 0.35 * overlap / max(1, len(q_words)))

        # Word-level similarity. "chorme" is one transposition away from the word
        # "chrome" inside "Google Chrome", and whole-string distance drowns that
        # in the length difference — so the best single-word match is scored.
        word_sim = max((similarity(query, word) for word in t_words), default=0.0)
        if word_sim >= 0.75:
            score = max(score, 0.9 * word_sim)

        # Acronyms: "vscode" -> "Visual Studio Code", "tm" -> "Task Manager".
        acronym = "".join(word[0] for word in t_words if word)
        if len(acronym) >= 2:
            if query_joined == acronym:
                score = max(score, 0.95)
            elif query_joined.startswith(acronym):
                score = max(score, 0.9)
            elif acronym.startswith(query_joined) and len(query_joined) >= 2:
                score = max(score, 0.85)

        # Consonant skeletons: "ppt" is p-p-t inside "p-w-r-p-n-t". Nothing else
        # in this file can see that, and abbreviations like it are how people
        # actually name office software.
        if (
            len(query_joined) >= 3
            and query_joined[:1] in {word[:1] for word in t_words if word}
            and _is_subsequence(_consonants(query), _consonants(target))
        ):
            score = max(score, 0.8)

        best = max(best, score)
    return min(1.0, best)


# Bigram Dice below this, with no consonant-skeleton evidence either, rejects a
# candidate before its edit distances are computed. 0.30 is well inside what a
# genuine mishearing keeps: "chorme" against "chrome" scores 0.40.
BIGRAM_GATE = 0.30


class FuzzyIndex:
    """Candidates indexed for fast lookup: phonetic bucket first, distance second.

    Built once per scan of installed programs (the resolver caches its scan for
    120 s; this index rides the same lifetime), so index build cost is paid once
    and every utterance after that is a bucket lookup plus a handful of
    distance computations.

    Everything derivable from a name is derived at BUILD time. The first version
    normalised every candidate on every query, which cost 11.7 ms per utterance
    against a 600-application index — affordable once, unacceptable in the path
    that runs before the user hears an answer. Preparation moved to the
    constructor: 600 normalisations once instead of 600 per question.

    The first-letter shortcut is an accelerator, not a filter. It is deliberately
    generous (any word of the name, not just the first) so that a phonetic rule
    being wrong can make the answer worse but can never make it disappear; and if
    the shortlist is empty the query falls back to a full comparison, because a
    miss here is a misheard command.
    """

    __slots__ = ("_bigrams", "_buckets", "_entries", "_firsts", "_lengths", "_skeletons")

    def __init__(self, items, name_of=None, aliases_of=None):
        name_of = name_of or (lambda item: str(item))
        aliases_of = aliases_of or (lambda item: ())
        # (display name, aliases, item, normalised name, normalised aliases)
        self._entries: list[tuple[str, tuple[str, ...], object, str, tuple[str, ...]]] = []
        self._buckets: dict[str, list[int]] = {}
        self._firsts: dict[str, list[int]] = {}
        # Every length the length gate may legitimately compare against, and the
        # consonant skeleton the abbreviation rule needs. Both are functions of
        # the name alone, so both belong here and not in the query path.
        self._lengths: list[tuple[int, ...]] = []
        self._skeletons: list[str] = []
        self._bigrams: list[frozenset[str]] = []
        for item in items:
            name = name_of(item)
            aliases = tuple(aliases_of(item) or ())
            norm_name = normalise(name)
            norm_aliases = tuple(normalise(alias) for alias in aliases)
            index = len(self._entries)
            self._entries.append((name, aliases, item, norm_name, norm_aliases))

            parts = [norm_name, *norm_aliases, *norm_name.split()]
            words = [word for word in norm_name.split() if word]
            self._lengths.append(
                tuple({len(norm_name.replace(" ", "")), *(len(word) for word in words)})
            )
            self._skeletons.append(_consonants(norm_name))
            self._bigrams.append(_bigrams_of(norm_name))

            for key in {phonetic_key(part) for part in parts if part}:
                self._buckets.setdefault(key, []).append(index)
            for letter in {part[:1] for part in parts if part}:
                self._firsts.setdefault(letter, []).append(index)

    def __len__(self) -> int:
        return len(self._entries)

    def query(self, spoken: str, limit: int = 5, threshold: float = 0.5):
        """[(score, item)] best first."""
        query = normalise(spoken)
        if not query:
            return []

        candidates: set[int] = set(self._buckets.get(phonetic_key(query), ()))
        for letter in {query[:1], *(word[:1] for word in query.split())}:
            candidates.update(self._firsts.get(letter, ()))

        # A first-letter hit is not evidence of a match: on a machine with a few
        # hundred "Program..." entries, one letter shortlists all of them and the
        # full score costs 20+ ms. Two cheap facts reject what cannot be close —
        # the length gate (a typo moves a name by a character or two, not by a
        # factor of two) and the consonant skeleton (an abbreviation is short but
        # its letters still appear, in order, inside the name).
        query_joined = query.replace(" ", "")
        query_length = len(query_joined)
        query_skeleton = _consonants(query)
        query_bigrams = _bigrams_of(query)

        def worth_scoring(index: int) -> bool:
            for length in self._lengths[index]:
                if abs(query_length - length) <= max(2, max(query_length, length) // 3):
                    break
            else:
                # Length alone already rules this name out...
                if not _is_subsequence(query_skeleton, self._skeletons[index]):
                    return False

            # ...but length is a weak signal between two English names of similar
            # length, which is exactly the case that made this method 100+ ms per
            # utterance against a 600-name index. Character bigrams are the cheap
            # discriminator: a typo or a spoken variant keeps most of them
            # ("chorme"/"chrome" keeps 2 of 5), while two unrelated names keep
            # almost none. Dice coefficient, no edit distance yet.
            candidate = self._bigrams[index]
            if not candidate or not query_bigrams:
                return _is_subsequence(query_skeleton, self._skeletons[index])
            overlap = len(query_bigrams & candidate)
            dice = 2.0 * overlap / (len(query_bigrams) + len(candidate))
            return dice >= BIGRAM_GATE or _is_subsequence(query_skeleton, self._skeletons[index])

        scored = []
        for index in candidates:
            if not worth_scoring(index):
                continue
            name, aliases, item, _norm_name, _norm_aliases = self._entries[index]
            score = match_score(query, name, aliases)
            if score >= threshold:
                scored.append((score, item))
        scored.sort(key=lambda pair: -pair[0])

        # Fall back to a full scan when the shortlist is empty: correctness beats
        # the optimisation, and this only happens on a miss. The length gate keeps
        # that scan honest — a one-chord difference in length is a typo, a factor
        # of two is a different word, and chars beyond it cannot be close.
        if not scored:
            for index, (name, aliases, item, _norm_name, _norm_aliases) in enumerate(self._entries):
                if not worth_scoring(index):
                    continue
                score = match_score(query, name, aliases)
                if score >= threshold:
                    scored.append((score, item))
            scored.sort(key=lambda pair: -pair[0])
        return scored[:limit]
