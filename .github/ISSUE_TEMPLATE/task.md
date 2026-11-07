---
name: Task an agent can claim
about: One unit of work. Assign it to claim it. Tick nothing until the evidence exists.
title: ""
labels: agent
assignees: ""
---

<!--
How to use this template. Delete this block before you post.

  Assign yourself  = you claim it. Nobody else starts it.
  Comment "taken"  = softer claim, if assign is already set.
  Close with a commit SHA in the body.

Two agents on one task is the same defect as two agents editing one file.
-->

## What

<!-- One sentence. A verb, a thing, and the result. -->

## Where

<!-- The files. Link them, do not describe them. -->

## Proof

<!-- What a machine can check when this is done. A test name, a command, a number. -->

## Not checked

<!-- What you cannot check from here. Name it before someone assumes it. -->

## Done when

- [ ] Tests pass: `python scripts/verify.py`
- [ ] The claim is in `scripts/proof_gate.py`, or it says why it cannot be.
- [ ] `log.txt` has one line with the build number.
