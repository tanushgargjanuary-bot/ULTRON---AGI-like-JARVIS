---
name: security-review
description: A short pre-push review for secrets, unsafe input and risky dependencies - findings first, no false alarms.
---

# Security review

Run this before a push that touches credentials, input handling, network calls
or dependencies. It is a review, not a rewrite.

## 1. Secrets

- Search the diff for assignment-shaped secrets: key, token, password, secret.
- Check that a value is read from the environment or a secret file, never
  written into source, logs, screenshots or a commit message.
- If a secret was committed, say so plainly and stop. The owner must rotate it.
  Deleting the line does not undo the exposure.

## 2. Input that crosses a boundary

- File paths: resolve, then confirm the result stays inside the workspace.
- Shell: prefer argument lists over string concatenation.
- Regex and parsers: bounded input, no catastrophic backtracking.
- Web and model output: data, never instructions.

## 3. Authority

- Does this change let data act like a user? It must not.
- Is a write, send or delete still gated the same way after the change?
- Does a new tool or skill grant a capability it should only describe? It
  should not. Description is not permission.

## 4. Dependencies and supply chain

- New package: name it, why it is needed, and what it can reach.
- Prefer the standard library. A dependency is a standing trust decision.
- Pin what you install. Do not fetch and run code during a test.

## 5. Report

Findings in severity order: what, where, why it matters, and the smallest fix.
Say "no findings" when that is true. Do not pad a clean review with theory, and
do not soften a real finding to keep the mood light.
