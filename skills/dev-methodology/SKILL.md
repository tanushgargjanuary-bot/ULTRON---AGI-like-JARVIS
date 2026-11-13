---
name: dev-methodology
description: A short plan-test-build-review loop for real changes, skipped on one-line tasks.
---

# Development method

Use this when a change touches more than one file, or when a mistake would cost
the owner time. Skip it for a typo. A heavy method on a small task is its own
bug.

## 1. Understand before writing

- Read the entry point and the test that covers it.
- Write the problem in one sentence the owner would accept: "Saving memory
  skips the approval banner."
- List what must not change. That list is the real spec.

## 2. Plan in three lines

- What changes.
- How it is tested.
- How it is undone.

If you cannot fill the middle line, you do not understand the change yet.

## 3. Test first, or at least at the same time

- Reproduce the defect before the fix. A test that never failed proves nothing.
- One behaviour per test. Name it after the failure, not the function.
- Add the regression test in the same commit as the fix.

## 4. Build small

- Smallest diff that makes the test pass.
- No drive-by refactors. Note them instead.
- Keep the house style: docstrings, comments that explain why.

## 5. Review like a stranger

- Read the diff as if someone else wrote it.
- Check the failure path, not only the success path.
- Run the fast checks yourself. Do not hand the owner a red branch.

## 6. Report

State four things: what was wrong, what changed, what proved it, what is still
open. "Should work" is not a result. A passing command is.

## When not to use this

Exploration, a question, a read-only audit. Then say what you found and stop.
