# OwnerFiles

This folder is the owner's, not the code's.

It holds the things that make this repository useful to a person and to another
AI: how the project was built, what was decided and why, and what the owner was
thinking while it happened. `Ultron` reads it. The owner writes it. The
assistant only adds what it can prove.

## Why it exists

A repository of source code tells a new AI **what** the program does. It does not
tell it **why** any of it is the way it is — which requirement created which
module, which defect taught which lesson, which option was rejected. Without that
context, the next assistant changes something carefully and breaks a decision it
never saw.

So the rule for this folder is one sentence:

> Another AI, given only this repository, should understand the intent well
> enough to continue the work without undoing it.

## What is here

| File | What it holds | Who writes it |
|---|---|---|
| `journey.md` | the build history in plain language: what was asked, what was built, what broke | the assistant, from the build record |
| `session-log.md` | short dated entries, newest last: what each session did | the assistant, and the owner can append |
| `owner-notes.md` | the owner's own words: goals, preferences, things he does not want | the owner |

## What must never be here

This folder is published. It is safe for anyone to read, and it must stay that
way. So:

- **No keys, tokens, passwords or account details.** Ever. They live in
  `config/api_keys.json`, which is ignored by git for exactly this reason.
- **No personal data about other people.** A name and an opinion is fine. A phone
  number, an address, a message thread is not.
- **Nothing that is only true of one machine.** A path with a username in it, a
  drive letter, a company laptop name.

The owner reviewed this paragraph and asked for this folder, knowing it is
public.

## How to use it with another AI

Give the other assistant the repository and say:

> Read `OwnerFiles/` first, then `ARCHITECTURE.md`, then `DECISIONS.md`, then
> `GATEKEEPERS.md`. Do not weaken a test to make a change pass. If a decision in
> `DECISIONS.md` blocks your change, say so instead of working around it.

That order matters. The journey explains the intent, the architecture explains
the shape, the decisions explain the limits, and the gatekeepers say which claims
already have proof.
