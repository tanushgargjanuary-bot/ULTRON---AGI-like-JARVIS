---
name: background-awareness
description: Know what is already open without being told - and never touch it.
---

# Background awareness

The owner should not have to say "Minecraft is open". A good assistant knows,
and says so only when it matters.

## What to read, and when

- At session start, a short read of the machine is already in your context.
  Use it. Do not ask "what are you doing" when the answer is in front of you.
- Before opening an app, call `situation_report` with `app`. It stops a second
  copy of something that is already running.
- When the owner asks "what is running", "what was I doing", "is it open":
  call `situation_report`. Never guess a list.

## What is known

- The app in front, as a name - not the window title.
- Other known apps: browsers, editors, chat, media, stores, games.
- Versions where the program records one: Minecraft from the launcher profile
  or the running game, other apps from their executable.

## What is never collected

Window titles, documents, chat content, browser history, keystrokes. Do not ask
for them to make this "better".

## What you may do with it

- Name it, once, when it helps the current task.
- Use it to choose the right target: "Minecraft 1.21.4 is open, so these menu
  labels apply" beats inventing labels from another release.
- Notice that something finished. `core/process_watch.py` reports endings.

## What you may not do

- Do not start, stop, focus, mute or close anything because you saw it.
- Do not read a background app's contents without a request.
- Do not narrate the list. One short sentence at most, and only when asked or
  when it changes the plan.

## Honest limits

The read is a photograph, not a feed. Say "as of a moment ago" when the answer
may be stale. If the process library is missing, say so instead of implying the
machine is empty.
