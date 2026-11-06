"""core/mental — the syllabus as machinery, not as notes.

The owner said it plainly: "I didn't want the syllabus as stored, but I wanted the
topics implemented as logic of ULTRON. This syllabus is meant to improve the working
of ULTRON."

So the course is not a book Ultron can read out. It is the set of algorithms Ultron
runs. Each function in this package carries the unit it comes from:

    @implements("DAA", 4, "Branch and bound")

and `registry.py` checks that citation against the syllabus file and against the code
itself, so the map cannot drift from the machinery.

    logic.py     DSTL unit 3, AI unit 3   rules, chaining, proof, what follows from what
    plan.py      AI unit 2, DS unit 5     best-first, topological order, shortest path
    choose.py    DAA units 1, 4, 5        exact or approximate or refuse, by size and time
    context.py   COA unit 4, DBMS unit 4  a memory hierarchy with eviction and a log
    records.py   DBMS units 2, 3, DS 3    integrity, normal forms, a hash index

The rest of the course reaches the same kernel through citations on code that already
existed: the trie, the knapsack, the branch-and-bound cut, the self-change ledger.

WHAT THIS IS NOT
    A second copy of the syllabus. `curriculum/aktu_aiml.json` still holds the whole
    course, because a student needs the topics that are not implemented. What changed
    is the priority: this package is the part that runs, and the file is the part that
    waits.
"""

from core.mental.registry import catalogue, implements, verify   # noqa: F401

__all__ = ["catalogue", "implements", "verify"]
