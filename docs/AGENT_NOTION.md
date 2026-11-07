# How agents write in Notion

Ultron is worked on by several agents, on several branches, at the same time. Notion is
where they hand work to each other. This page is the format, so a page written by one
agent is readable by the next one in ten seconds.

The owner's rule first: **plain words, no blobs.** A person with little time must get the
conclusion in the first line.

## The eight rules

1. **One page per project.** Not a second page for the same thing, and not a new page per
   session. If the page exists, edit it.
2. **A fixed section order.** Where it stands → Read first → What changed → Next moves →
   Traps → Proof. An agent that lands in the middle still knows where it is.
3. **Dates on headings. Numbers, not adjectives.** `Where it stands (7 Nov 2026)` and
   `1,577 tests, 15 skipped`. Never "much faster" or "mostly done".
4. **Update, do not append.** A diary of forty entries is not a handover. Replace the
   state; keep the history in `log.txt`, which is built for it.
5. **One checkbox per task**, and the person who finishes it ticks it and adds the commit
   SHA. An unticked box with no owner is a wish.
6. **Say what you did not check.** "Not run on Windows", "no real key", "no microphone
   here". A gap named is worth more than a claim rounded up.
7. **Link the file, do not summarise the file.** `docs/SELF-CHANGE.md` stays true when it
   changes; a summary of it does not.
8. **Delete nothing another agent wrote.** Correct it, and say why in one line. Two agents
   overwriting each other's work is the same defect as two branches doing it.

## The rule underneath all eight

> A claim needs evidence. A claim without evidence must say so.

That is the rule the code runs on. It applies to a page too. If the page says the build is
green, the run number goes next to it.

## Where the pages live

- **One hub page per project**, with the handover as its child page.
- The hub holds the state and the index. The child page holds the detail.
- Nothing private. No keys, no tokens, no personal data about other people. The same rule
  as `OwnerFiles/README.md`, for the same reason: this page may be shared.
