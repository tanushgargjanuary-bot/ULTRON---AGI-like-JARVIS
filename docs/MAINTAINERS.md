# Owner notes

This file is yours. Nothing here is generated. Write in it as you like: short
lines, rough notes, questions to the next assistant.

It is published, so keep keys and other people's personal details out of it.

---

## What I want Ultron to be

A voice assistant that lives on my own computer, that I can trust, that thinks
like the analytical characters rather than sounding like them, and that gets
better without me babysitting it.

## Things I never want it to do

- Remember anything without asking me first. *("Only remember what I approve.")*
- Send a message and call it sent without reading it back.
- Change its own safety rules, or the files that decide what needs approval.
- Hardcode a provider, a model or a feature list and pretend it is a choice.
- Add launcher files. The installer already has `run.ps1`.
- ~~Grow the folder past 100 MB.~~ **Superseded 2026-11-07.** The owner withdrew the 100 MB / 5,000-file ceiling. Keep generated artifacts, caches, and machine state out of Git, but do not enforce a repository size cap. See `../docs/SPACE.md` and `../docs/AGENT_MAINTENANCE.md`.
- Claim something works when it has not been run. No fabricated claims in the
  readme, ever.
- Interrupt me mid-sentence, or ask me about trivial actions.
- Rewrite the project. I considered it, and I dropped it.

## Preferences about how work is done

- **Answer first.** A yes or no question gets Yes or No as the first word, then
  the evidence.
- **Plain words before any table.** Simplified English. Short sentences. One
  instruction per sentence. I have asked for this three times.
- **Fast.** "Please do this fast." Do the work, then explain it.
- **PowerShell syntax** for anything I have to type.
- **No voice acting.** I do not want the fictional voices. I want the *thinking*:
  analytical, calculative, scientific.
- **The syllabus must run, not sit on a shelf.** Topics implemented as logic of
  Ultron, not stored as text.
- **One commit per improvement**, pushed to GitHub, and tell me honestly whether
  it is pushed.
- **Prove it.** "Make sure there are no bugs in this. Work rigorously on fixing
  bugs." "You should make a PROOF GATE."
- **Keep the code simple, optimised and the best quality** I can get.

## Open questions I keep coming back to

- Which provider I actually use day to day.
- Whether the Agentic OS (Debian, dual-boot) gets a live bridge to Ultron later,
  or stays a shared memory format and an export bundle.
- What to build next from `docs/CAPABILITIES.md`, which is a menu, not a plan.

## My own journey with this project

<!-- Write this part yourself when you have a quiet hour. It is the one thing no
     build record can carry: what made you start, what you want it for, and what
     you have learned while building it. The next assistant reads this before it
     touches a line of code. -->
