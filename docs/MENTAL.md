# The syllabus, as logic

This page is about one correction. The owner said:

> I didn't want the syllabus as stored, but I wanted the topics implemented as logic of
> the ULTRON. This syllabus is meant to improve the working of ULTRON.

So the course is not a shelf here. Parts of it are the machinery.

## What changed

The subjects are still listed, because a plan is useful. But each topic that Ultron
can really do now carries a line in the code that says which course unit it comes
from. That line is attached to the function itself, so it cannot drift from the code
it describes. A check reads both the code and the syllabus file and fails if the
function is gone or the topic is not in that unit.

```
@implements("DAA", 4, "Branch and bound")
def decide(...):
```

## What Ultron now does because of it

| It is asked | It uses | From |
|---|---|---|
| May I run this tool? | the tier becomes a fact, the verdict is derived from it, and the chain is kept | AI unit 3, DSTL unit 3 |
| In what order do these steps go? | topological order, and a refusal when the steps wait on each other | DS unit 5 |
| Which is the cheapest route? | shortest path, Dijkstra's answer | DAA unit 3 |
| Is this worth doing exactly? | growth of functions against a budget, and a plain statement when it is not | DAA unit 1 and 5 |
| Are these records sound? | the four integrity constraints, then repeating groups | DBMS unit 2 and 3 |
| What fits in the prompt? | a three-tier store with least-recently-used eviction and a log | COA unit 4, DBMS unit 4 |
| Is this word a typo or a name? | edit distance, Soundex, Metaphone (already there) | DAA unit 4 |
| Which of these many things matter? | heaps, tries, the branch and bound cut (already there) | DS unit 4, DAA unit 2 and 4 |

## How to see it

Say **"which of the syllabus is inside you"**. Ultron answers per subject, with the
count of topics that run as code and the function behind each one.

Say **"why are you asking me"**. Ultron answers with the tier, the derived rule, and
the chain that produced the answer.

## What is honest about it

Eighteen topics out of 284 run as code today. The rest are listed and waiting, and
the tool shows them as waiting. Nothing here claims more than it does, and the proof
gate fails if a citation points at code that is not there.

## Why this matters more than a bigger list

A list can be quoted. A rule can be checked. When Ultron says it may not write a file
without asking, the answer now comes from a derivation over the same tier table the
policy uses, and the derivation is shown. That is a claim the owner can audit, which is
the only kind worth making.
