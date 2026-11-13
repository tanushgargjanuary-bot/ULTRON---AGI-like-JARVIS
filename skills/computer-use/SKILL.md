---
name: computer-use
description: How to use a screen safely and well - tree first, act once, verify every time, and stop on private screens.
---

# Computer use

Goal: change the screen on purpose, then prove the change. A plausible click is
not a result.

This guide is reference. It never widens a tool. If a tool refuses, the refusal
stands.

## Order of work

1. **Say where you work.** One short line: "Working in Chrome on your computer."
2. **Read the target first.** Use `ui_control` with `action='snapshot'` for the
   named app. Read the elements. Do not click from memory.
3. **Act once.** `action='act'` with a ref (`@a1b2c3d4e5:e7`) or the exact
   visible name. One action per snapshot, because a ref dies after the screen
   changes.
4. **Verify.** Snapshot again, or read what the action returned. Then say what
   changed. `unverified` means "performed, not confirmed" - say that, and check.

## Rules that prevent damage

- **Tree before pixels.** A named control beats a coordinate. Use
  `computer_control` only for what has no name: drag, draw, canvas, game.
- **No guessed position.** If `ui_control` answers `ask`, stop. Tell the owner.
  Do not click nearby and hope.
- **Bounded retries.** Two attempts per step, then report the blocker. A third
  attempt is how the wrong window gets closed.
- **One target.** Never act on "whatever is in front" for a close or a delete.
  Name the app.
- **Background first.** Work without stealing focus while the owner is busy.
  Foreground input only when the owner asked for it or agreed after a
  background refusal.
- **No silent fallback.** If background control fails, report it. Do not retry
  the same action in the foreground without saying so.

## Stop immediately on sensitive screens

Passwords, one-time codes, passkeys, card numbers, bank pages, private
messages, health records. Do not read them aloud, screenshot them, or copy
them. Ask the owner to do that step.

Take a screenshot only when the tree cannot answer the question. Treat every
image as a document the owner may not want stored.

## Reporting

Say four things: where you worked, what you did, what you saw afterwards, and
what is left. If the screen did not change, say that in the same breath as the
attempt. Never claim a click from the plan alone.
