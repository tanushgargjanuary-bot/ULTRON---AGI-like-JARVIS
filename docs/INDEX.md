# Document index

Every document in the repository, one line each, and who it is for.

## Start here

| Document | Who it is for | What it answers |
|---|---|---|
| [`readme.md`](../readme.md) | everyone | what Ultron is, how to install it, and what changed in the last build |
| [`ARCHITECTURE.md`](../ARCHITECTURE.md) | anyone changing code | the six layers, one turn end to end, where a change belongs |
| [`docs/MAP.md`](MAP.md) | anyone changing code | every module with its one-line purpose, line count and test — **generated** by `python scripts/map.py --write` |
| [`DECISIONS.md`](../DECISIONS.md) | anyone proposing a change | what the owner decided, in his words, and where it is enforced |
| [`GATEKEEPERS.md`](../GATEKEEPERS.md) | anyone making a claim | which claims are proven, which need his machine, and why |

## The owner's folder

| Document | What it holds |
|---|---|
| [`OwnerFiles/README.md`](../OwnerFiles/README.md) | what the folder is for, what must never be in it, and the one sentence that defines it: another AI, given only this repository, must understand the intent well enough to continue the work without undoing it |
| [`OwnerFiles/journey.md`](../OwnerFiles/journey.md) | the build history in plain language, including the defects the assistant caused |
| [`OwnerFiles/session-log.md`](../OwnerFiles/session-log.md) | dated entries: what was asked, what was built, what is left |
| [`OwnerFiles/owner-notes.md`](../OwnerFiles/owner-notes.md) | the owner's own words, and the prompts for them |

## How it was built

| Document | What it holds |
|---|---|
| [`docs/CURRICULUM.md`](CURRICULUM.md) | the eight AKTU subjects it holds, where each syllabus came from, and the reading at three levels |
- [The syllabus as logic](MENTAL.md) — which course topics run as Ultron's own algorithms, and where.
- [How a skill gets used](TRIGGERS.md) — the condition that triggers each tool, and the count that shows a dead one.
| [`docs/SELF-CHANGE.md`](SELF-CHANGE.md) | the five stages of changing its own source, the rehearsal copy, and the referee that is off limits |
| [`docs/PHILOSOPHY.md`](PHILOSOPHY.md) | the seven minds Ultron blends, their methods, and why a voice can never add a permission |
| [`docs/SPACE.md`](SPACE.md) | how big the folder may get, what is counted, and why a save once lost 6,352 files |
| [`HANDOFF.md`](../HANDOFF.md) | the build log by phase: what each pass fixed, what it cost, what is left |
| [`log.txt`](../log.txt) | the same, as plain append-only text, newest last |
| [`verification-results.txt`](../verification-results.txt) | the last full `scripts/verify.py` output |
| [`ALGORITHMS.md`](../ALGORITHMS.md) | which algorithms are on a live path, mapped to the AKTU DAA/AIML syllabus, and which are refused and why |
| [`AGENTS.md`](../AGENTS.md) | hard rules for any AI editing this repository |
| [`CUSTOM_ULTRON.md`](../CUSTOM_ULTRON.md) | what was changed from upstream MARK, and how to use it |
| [`PUBLISH.md`](../PUBLISH.md) | the two commands that publish, and the licence rules |

## Capability documents

| Document | What it holds |
|---|---|
| [`docs/SKILLS.md`](SKILLS.md) | every skill family, why meta-learning and meta-cognition are built this way, the next tier in value order, and the four things that must never become a skill |
| [`docs/TOOL_SUGGESTIONS.md`](TOOL_SUGGESTIONS.md) | which tools were considered, which shipped, and which were refused with a reason |
| [`docs/LANGUAGE_DECISION.md`](LANGUAGE_DECISION.md) | should this be rewritten in another language — no, with numbers |
| [`docs/SIDECAR.md`](SIDECAR.md) | anyone building or auditing the Go component | why one part is Go, what it measures, and the rule that it only watches |
| [`docs/PERFORMANCE.md`](PERFORMANCE.md) | the owner, and anyone asking “why is this not faster” | every measured stage of a turn, a launch and an audio frame, and what would actually move them |
| [`docs/PROMPT.md`](PROMPT.md) | the owner, and anyone who wants to know what the assistant was told | the system prompt: where it lives, how to read it, how to change it, and why a change needs two confirmations |
| [`docs/LANGUAGE_MATRIX.md`](LANGUAGE_MATRIX.md) | the owner, and anyone tempted by a rewrite | all 46 candidate languages, filtered: seven keepers, four laters, and the reason each of the rest lost |
| [`docs/CAPABILITIES.md`](CAPABILITIES.md) | the menu of capabilities that were designed but not built |

## Shipping and updating

| Document | What it answers |
|---|---|
| `custom_jarvis/ship.py` | the order: scan, guard, syntax, gate, commit, push — and the sentence each refusal returns |
| `custom_jarvis/selfupdate.py` | how a pull is verified, why a bad version is reset, and when a restart is asked for |
| `custom_jarvis/ship_tools.py` | the four tools a person reaches: two to look, two to act |
| gate claims `shipping`, `self_update` | the whole chain against a real bare remote, with no mocks |

## Scripts that produce a document or a verdict

| Script | Produces |
|---|---|
| `scripts/verify.py` | the full suite, the self-checks, the migration checks (`verification-results.txt`) |
| `scripts/proof_gate.py` | the claim table: `PROVEN`, `PARTIAL`, `FAILED`, `NOT PRESENT` |
| `scripts/verify_all.py` | the same questions on the target machine, where Windows, a microphone and a display exist |
| `scripts/map.py` | `docs/MAP.md`, and exit code 1 when a new module has no docstring or no test |
| `scripts/bench_algorithms.py` | timings for the algorithm modules |

## The rule for this folder

A document that is not linked here is a document nobody will read. When you add
one, add its line.
