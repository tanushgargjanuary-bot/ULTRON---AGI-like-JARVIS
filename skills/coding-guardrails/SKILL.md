---
name: coding-guardrails
description: Three habits that stop the common coding failures - wrong assumptions, overcomplicated code, and edits nobody asked for.
---

# Coding guardrails

Most bad agent changes are not hard bugs. They are one of three habits.

## 1. Do not assume - check

- Read the file before you edit it. Read the schema before you call a tool.
- If a name, path or flag is a guess, say it is a guess, then verify.
- Prefer one real check over three confident sentences.
- A check that could not run is not a check that passed.

## 2. Do not overcomplicate

- Write the version you would explain in one sentence.
- No abstraction for a single caller. No option nobody asked for.
- No clever fallback chain. One clear failure beats three silent ones.
- If the simple version is wrong, fix it. Do not wrap it.

## 3. Do not edit what you were not asked to change

- Touch the lines the task needs.
- No reformatting, renaming or reordering next to a fix.
- A comment that explains why stays. A comment that repeats the code goes.
- If a nearby bug is real but out of scope, report it. Do not fix it quietly.

## Before you say done

- Does the diff contain only the change?
- Did the failing case actually fail before, and pass now?
- Would the owner recognise the code as theirs?
- Is every claim in the report backed by a command you ran?

## The one-line test

If the owner asks "why did you change that?", you should have an answer about
their request, not about your taste.
