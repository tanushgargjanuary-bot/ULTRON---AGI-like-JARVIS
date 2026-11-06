"""The DBMS units, applied to what Ultron remembers.

Memory here is a list of records in a JSON file, and it has the problems every
un-normalised table has. The same fact arrives twice with a different spelling. A
record points at a person who no longer exists in the list. Two records claim the same
key. A field holds a number where a date belongs.

The syllabus already has the tests for all four, and this file is those tests running
on the memory the assistant actually keeps:

    unit 2   entity, referential, key and domain integrity
    unit 3   functional dependencies, and why 1NF, 2NF and 3NF exist
    unit 3   hashing, for looking a record up without reading the file
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from core.mental.registry import implements


@dataclass(frozen=True)
class Fault:
    """One thing wrong with one record, in the words a person would use."""

    kind: str
    key: str
    detail: str


@implements("DBMS", 2, "Integrity constraints: entity, referential, key, domain")
def integrity(records, identifier: str = "id", links: dict | None = None,
              domains: dict | None = None) -> dict:
    """Check the four constraints the syllabus names, and name every violation.

    `links` maps a field to the field its value must appear in, which is referential
    integrity. `domains` maps a field to a type or a set of allowed values. A record
    set that passes all four is one a later reader can trust without reading the code
    that wrote it.
    """
    faults = []
    seen = set()
    known = {str(record.get(identifier)) for record in records}
    for record in records:
        key = str(record.get(identifier, ""))
        if not key:
            faults.append(Fault("entity", "?", f"a record has no {identifier}"))
            continue
        if key in seen:
            faults.append(Fault("key", key, f"{identifier} '{key}' appears twice"))
        seen.add(key)
    for record in records:
        key = str(record.get(identifier, ""))
        for field, target in (links or {}).items():
            value = record.get(field)
            if value is not None and str(value) not in known:
                faults.append(Fault("referential", key,
                                    f"{field} points at '{value}', which is not a "
                                    f"{target}"))
        for field, allowed in (domains or {}).items():
            if field in record and not _fits(record[field], allowed):
                faults.append(Fault("domain", key,
                                    f"{field} is {record[field]!r}, which is not "
                                    f"{_allowed(allowed)}"))
    return {"ok": not faults, "faults": faults,
            "why": ("every record passes entity, key, referential and domain integrity"
                    if not faults else f"{len(faults)} violation(s)")}


def _fits(value, allowed) -> bool:
    if isinstance(allowed, type):
        return isinstance(value, allowed)
    if isinstance(allowed, (set, frozenset, tuple, list)):
        return value in allowed
    return True


def _allowed(allowed) -> str:
    if isinstance(allowed, type):
        return f"a {allowed.__name__}"
    return "one of " + ", ".join(sorted(str(item) for item in allowed))


@implements("DBMS", 3, "Functional dependencies")
def dependencies(records, determinant: str, dependent: str) -> dict:
    """Does `determinant` decide `dependent` in this data, and where does it fail?

    A functional dependency is a claim about the world, and data can only contradict
    it. That asymmetry is said out loud in the answer: agreement is evidence, not
    proof.
    """
    seen = {}
    clashes = []
    for record in records:
        left, right = record.get(determinant), record.get(dependent)
        if left is None or right is None:
            continue
        if str(left) in seen and seen[str(left)] != right:
            clashes.append(f"{determinant}={left} gives both {seen[str(left)]!r} and "
                           f"{right!r}")
            continue
        seen.setdefault(str(left), right)
    return {"holds": not clashes, "clashes": clashes,
            "why": ("no record contradicts it — agreement is evidence, not proof"
                    if not clashes else f"{len(clashes)} record pair(s) contradict it")}


@implements("DBMS", 3, "First, second and third normal forms")
def redundancy(records, fields) -> dict:
    """Where the same fact is repeated, which is what normalisation removes.

    A group that repeats a fixed combination of values is the classic 2NF problem: the
    fact belongs in its own table. The answer names the repeating groups and the count,
    because "normalise your data" without a number is advice, not a finding.
    """
    fields = list(fields)
    groups = {}
    for record in records:
        signature = tuple(str(record.get(field)) for field in fields)
        groups[signature] = groups.get(signature, 0) + 1
    repeated = {signature: count for signature, count in groups.items() if count > 1}
    wasted = sum(count - 1 for count in repeated.values())
    return {"repeated": len(repeated), "wasted_rows": wasted,
            "examples": [dict(zip(fields, signature)) for signature in
                         list(repeated)[:5]],
            "why": (f"{wasted} row(s) repeat a fact that belongs in its own table"
                    if repeated else "no repeating group in these fields")}


@implements("DS", 3, "Hash functions")
def hash_index(records, field: str = "id") -> dict:
    """An index from a key to its record, built with a stable hash of the key.

    The hash is used to bucket, never to identify: two different keys may share a
    bucket, so the bucket is checked. That is the difference between an index and a
    guess.
    """
    buckets = {}
    for record in records:
        key = str(record.get(field, ""))
        if not key:
            continue
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]
        buckets.setdefault(digest, []).append(record)
    return {"buckets": buckets, "keys": sum(len(rows) for rows in buckets.values()),
            "why": f"{len(buckets)} bucket(s) for "
                   f"{sum(len(rows) for rows in buckets.values())} record(s)"}
