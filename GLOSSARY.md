# Glossary

These are the words we use in chat, in issues and in documents about Ultron. Each word has one meaning.

If you meet a word that is not here, say "wait what". We will explain it in plain words. Then we add it here.

This page follows the format of the domain-modeling skill by Matt Pocock. A test keeps it in step with the words the program prints.

## Language

### The project and where it came from

**Ultron**:
The voice assistant in this repository. You speak to it. It listens, thinks, and does things on your computer.

**Owner**:
The person who decides what Ultron is for. When the owner decides something, it is written in the decisions list.

**Coding agent**:
An AI program that changes the code of Ultron. One is built into Ultron. Others, like the one in this chat, work from outside.
_Avoid_: bot

**Mark**:
The older project that Ultron grew from. Its author is FatihMakes. Its newest version is called Mark LVII.
Its licence lets us share the work but not sell it. We keep the credit to its author.

**Upstream**:
The project we take ideas from. For Ultron, upstream is Mark.

**Follow-up watch**:
A program that checks Mark's repository on a schedule and writes a report. It only reads. It never changes Ultron.

**Slice**:
One small change that takes one idea from Mark, with its test, and nothing else.

**Collision**:
A place where Mark and Ultron both changed the same lines in different ways. A person must decide how to combine them.

**Decision word**:
The word we write beside a change from Mark to say what we decided.
Ours means we keep Ultron's version. Take means we apply Mark's change after a test. Merge means we combine both versions by hand.
Later means we want it, in a planned slice. Parked means we set it aside on purpose. Rejected means we do not want it.

**Held**:
A change from Mark that nobody has decided about yet. It is reported and never copied. It waits for a decision word.

**Excluded feature**:
A Mark feature the owner does not want. There are four.
E1 is news when Ultron opens. E2 is a news watch every 30 minutes. E3 is a routine that runs tools by itself when Ultron opens. E4 is the phone and web remote dashboard.
The follow-up watch looks for them and says if one appears.

### GitHub and changes

**Branch**:
A separate copy of the work on GitHub. A change is made on a branch first. Then it is added to main.

**Main**:
The branch that holds the accepted version of Ultron. Only checked changes reach it.

**Pull request**:
A request to add the changes of one branch to main. It shows the changes and the results of the checks. Short form: PR.
_Avoid_: merge request

**Merge**:
To add the changes of a pull request to main. After a merge, the change is part of Ultron. Another change can undo it.

**Dependabot**:
GitHub's robot. It proposes updates to the libraries Ultron uses, as pull requests. A person decides.

### Checks and tests

**Check**:
A run that GitHub starts by itself on a change. It passes or it fails. It can run many tests and other programs.
_Avoid_: pipeline

**Required check**:
A check that must pass before GitHub allows a merge into main.

**Fast gate**:
The quick check. It runs on every push. A fast pass is not a full pass.

**Full check**:
The long check. It runs all the tests on Windows and on Linux. It must pass before a merge.

**Install check**:
A check that installs Ultron from nothing on a clean Windows machine. It shows that a new install works. It is not a required check.

**Test**:
A small program that checks one thing Ultron should do. The checks run the tests.
_Avoid_: spec

**Red and green**:
Red means a test or a check fails. Green means it passes. A new test must be red before the fix and green after it.

**Planted fault**:
A mistake we add on purpose to see if the tests catch it. If the tests stay green, they are too weak.

**Not verified**:
Our words for a claim that has no evidence yet. We write them instead of guessing.

### The proof gate

**Proof gate**:
A program that checks whether Ultron really does what it claims. It runs each claim step by step on one computer. Then it gives the claim one verdict.

**PROVEN**:
Every step of the claim ran on this computer and gave the right result.

**PARTIAL**:
Some steps ran. A later step could not run here. So the claim is not proven. We never count it as a pass.

**SKIPPED**:
This computer cannot run the claim. For example, it has no microphone. Run it on the right computer to find out.

**FAILED**:
A step ran and gave a wrong result.

**NOT PRESENT**:
There is no code behind the claim. It is a missing feature, not a broken one.

### Safety inside Ultron

**Referee file**:
A file that decides what Ultron may do, or that checks Ultron. The coding agent built into Ultron may never change it. Anyone else who changes one must say so.

**HUD**:
The overlay that Ultron draws on your screen. It shows what Ultron is doing. It asks you to confirm risky actions.

**Confirm button**:
The button on the HUD that you press to allow a risky action. The assistant cannot press it for you.

**Tool**:
One thing Ultron can do when you ask, such as set the volume. Each tool says when it should be used.
_Avoid_: command

**Plugin**:
An extra tool in its own file, which the owner can add. It must answer briefly and never crash Ultron.

**Provider**:
The company and model that supply Ultron's thinking and voice. Gemini is one provider.

**Key**:
A secret code that lets Ultron use a provider. It stays on the owner's computer.

### Libraries and updates

**Library**:
A program written by other people that Ultron uses. The libraries are listed in one place.

**Pin**:
A rule that fixes which versions of a library are allowed.
_Avoid_: lock

**Ceiling**:
The newest version of a library that we allow. It stops a new and untested release from reaching a fresh install.

## Relationships

- A slice reaches main through a pull request.
- A pull request needs every required check green before a merge.
- The proof gate gives each claim one verdict: PROVEN, PARTIAL, SKIPPED, FAILED or NOT PRESENT.
- The follow-up watch reads Mark and reports. A change stays held until someone gives it a decision word.
- A referee file is changed only by a person or an outside coding agent. The coding agent built into Ultron never changes it.

## Flagged ambiguities

- "Ready". "100 per cent ready to use" cannot be promised. Since 2026-11-25 we have used a working meaning. Everything that can run here is green. A fresh install is proven. The records are true. What only the owner's computer or keys can show is listed by name. The owner has not yet confirmed this meaning.
- "Merge". In reports about Mark, the decision word merge means to combine two versions by hand. On GitHub, merge means to add a pull request to main. When both could apply, we write "combine by hand" for the first.
- "Check" and "test". A test checks one thing about Ultron. A check is a whole run on GitHub. We do not use the two words for each other.
- "Gate". A gate is a check that must pass before work moves on. The fast gate and the proof gate are different. Always say which one.
- "Mark". A few places in the code still show the old name MARK LVI. It is an older version of Mark. It is not a second project.
