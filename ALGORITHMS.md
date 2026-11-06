# Algorithms for Ultron — mapped to the AKTU 3rd-year DAA and AIML syllabus

> **STATUS (PHASE 17): Tier A is implemented and wired.** These are no longer
> recommendations. `core/fuzzy.py`, `core/knapsack.py`, `core/branchbound.py`,
> `core/bandit.py`, `core/reputation.py`, `core/audio_features.py`,
> `core/numerics.py` and `core/trie.py` exist in this repo, written from the
> standard library, tested offline, and two of them are now on the live path
> (`core/app_resolver.py` and `providers/engine_pipeline.py`). Measurements are
> in `scripts/bench_algorithms.py`; the reasoning and the four bugs the tests
> caught are in `log.txt` PHASE 17. Tier B below is still a plan. Everything
> Tier C still says "does not apply", and the reasons still hold.
>
> ```powershell
> python scripts\bench_algorithms.py
> python -m unittest tests.test_fuzzy tests.test_knapsack tests.test_branchbound tests.test_bandit tests.test_reputation tests.test_audio_features
> ```

> **Phase 18 (build 1.2.15).** Four more now sit on live paths, chosen for the
> same reason as before — each replaces a guess: `core/bandit.py`'s UCB1 now
> drives strategy choice in `custom_jarvis/metacog.py`; `custom_jarvis/shortlist.py`
> (BM25) ranks lesson recall; `custom_jarvis/decision.py` scores candidate actions
> as chance x value - cost - risk and is exposed as the `decide` tool; and
> `custom_jarvis/telemetry.py` (EWMA + z-score) reports the pace of a session in
> `AutonomyGovernor.status`. Evidence: `tests/test_decision_layers.py`,
> `python scripts\proof_gate.py --only decisions`.

Written for a B.Tech 3rd-year AKTU student who is being taught these topics right now and wants
them pointed at a real codebase instead of a lab file. Every row below names the **file and function
it would replace or extend in this repo**, so it can be read as a work plan and as revision notes.

Two honesty rules apply throughout:

1. **A row that says "does not apply" is worth more than a row that invents a use for it.** Half of
   a DAA syllabus exists to solve problems Ultron does not have. Knowing which half is the actual
   skill, and it is examinable too — "why is this algorithm inappropriate here?" is a better answer
   than a recital.
2. **Nothing here is claimed to help until it has a number.** Each item says what to measure. The
   harness pattern already exists in this repo: `scripts/bench_startup.py` for timing, and a fixture
   table for correctness.

Syllabus basis: AKTU **Design and Analysis of Algorithm** (BCS503 / KCS503 / RCS502 — the unit split
is the same across all three) and the AKTU CSE (AI & ML) **Artificial Intelligence and Machine
Learning** paper, whose units run roughly: AI and search → advanced search and knowledge
representation → supervised learning → software agents → unsupervised learning and RL. If your
paper numbers those units differently, the mapping still holds — it keys on the topic, not the unit.

---


## Implementation status, module by module

| # | Algorithm | Module | Tested | On a live path |
|---|---|---|---|---|
| A1 | Damerau-Levenshtein, Soundex, Metaphone, acronym/skeleton tiers, bigram-gated index | `core/fuzzy.py` | 33 tests, 15/15 top-1 on misheard names | **Yes** — `core/app_resolver.py` fallback tier |
| A2 | 0/1 knapsack, exact DP under a cell budget + greedy half-bound | `core/knapsack.py` | 25 tests incl. brute-force cross-check | No — written, next wiring target (`format_memory_for_prompt`, `_trimmed`) |
| A3 | Branch and bound with optimism bounds, ambiguity margin, node budget | `core/branchbound.py` | 14 tests | No — next wiring target (confidence gate before asking) |
| A4 | UCB1 + Thompson + contextual bandit | `core/bandit.py` | 18 tests, seeded simulations | No — next wiring target (`core/routing.py`) |
| A5 | Hann-windowed FFT, spectral flatness, ZCR, percentile noise floor, turn-end state machine | `core/audio_features.py` | 23 tests incl. engine wiring with real PCM | **Yes** — `providers/engine_pipeline.py::_watch_for_turn_end` |
| A6 | Beta reputation with half-life decay | `core/reputation.py` | 17 tests | No — next wiring target (`custom_jarvis/failure_memory.py`) |
| — | Regularised incomplete beta, Beta quantile, Wilson bound | `core/numerics.py` | 11 tests | Supports A3/A6; removes any temptation to import scipy |
| B* | Trie with iterative traversal and completion | `core/trie.py` | 8 tests | No — written, unused |

Measured on this machine (offline, `scripts/bench_algorithms.py`): fuzzy 279 µs/query against
590 names; knapsack greedy at 0.968 of the optimum (proven bound 0.5) with exact at 1.8 ms;
branch-and-bound prunes 42% of nodes; reputation's lower bound clears 0.70 after 8 clean
results; Thompson regret 7.2 vs 666.7 for uniform choice over 2,000 rounds; audio 70 µs per
30 ms frame (0.24% of realtime).

## Tier A — the detail, for revision

### A1. Fuzzy app-name matching — *DAA Unit IV (DP: edit distance) + Unit V (string matching)*

| | |
| --- | --- |
| Where | `core/app_resolver.py::_score` and `_candidates` |
| Today | token overlap: `len(query_tokens & name_tokens)`, no credit for prefixes |
| Build | **Damerau–Levenshtein** over normalised names (DP, O(mn) time / O(min(m,n)) space with one row), plus **Boyer–Moore**-style fast scan for the long installed-app list, plus **Soundex / Double Metaphone** bucketing so "viber" and "Viber" and "vyber" collide before scoring |
| Why | this is the class of bug behind "open whatsapp opened a folder": a mispronounced or STT-mangled name scores 0 and falls through to a path matcher |
| Cost | < 1 ms for a few hundred apps if the phonetic bucket is checked first (that is the whole point of bucketing — it turns an O(n·mn) scan into O(mn) over one bucket) |
| Test | a fixture table of 60 real mangled names → expected app, scored as top-1 accuracy, not vibes |

This is also the single best exam-to-code exercise in the list: edit distance, why DP beats
backtracking here, and why you use one row of the table instead of the full matrix.

---

### A2. Context assembly as a 0/1 knapsack — *DAA Unit IV (DP: knapsack, resource allocation)*

| | |
| --- | --- |
| Where | `memory/memory_manager.py::format_memory_for_prompt` and `providers/engine_pipeline.py::_trimmed` |
| Today | recency order until a character budget runs out |
| Build | treat every candidate block (memory entries, tool results, recent turns) as an item with **value = relevance score** and **weight = tokens**, fill a budget with 0/1 DP. Since exact knapsack is O(n·W) and W is a token budget in the thousands, use the **greedy ratio approximation** (value/weight) with a **fraction-free bound** — and know *why*: the problem is weakly NP-hard, greedy is a 2-approximation for this shape, and 2 % off optimal is invisible in a prompt |
| Why | today a 12 KB tool result can evict six memories that mattered. This makes eviction a decision instead of an accident |
| Test | replay 50 recorded sessions; compare "was the fact needed later in the conversation present in the prompt" against the current policy |

This row is *exactly* the AKTU Unit IV "resource allocation problem", with tokens as the resource.

---

### A3. Branch-and-bound over interpretations — *DAA Unit IV (backtracking, B&B) + AIML Unit I (CSP)*

| | |
| --- | --- |
| Where | new, next to `core/app_resolver.py`; consumed by `core/custom_gate.py` before it asks |
| Today | either a guess or a question |
| Build | search the tree of candidate interpretations (which app, which file, which contact). Score each node with an **optimistic upper bound**; prune when the bound drops below your **lower confidence bound (0.70)**; if no branch beats it after pruning, ask. That is textbook B&B, and it is also precisely the "calibrated ≥ 0.70" rule you already specified |
| Why | turns "ask or guess" into "search, then ask only when the search cannot decide" — fewer prompts, and the prompts that remain are the ones that need a human |
| Test | a labelled set of ambiguous utterances; measure ask-rate at fixed precision. Target: fewer asks, same precision |

The B&B framing is worth writing up in a project report: your confidence threshold is a *pruning
bound*, and the ask is the fallback when the bound never clears.

---

### A4. Cheapest-capable provider as a bandit — *AIML Unit V (RL) + DAA Unit I (amortized analysis)*

| | |
| --- | --- |
| Where | `core/routing.py::RoutingTable` + `QuotaLedger` (both exist, neither learns) |
| Today | static routing by purpose; quota tracking with no feedback |
| Build | **UCB1 / Thompson sampling** over (purpose, provider) with reward = −(latency + cost + failure penalty), hard constraints from the quota ledger. Keep it a *contextual* bandit with purpose as the context — a plain multi-armed bandit would average "explain this" with "open chrome" and learn nothing useful |
| Why | you asked for no hardcoded model policy; a bandit chooses by measured behaviour, which is the only honest way to pick |
| Caveat | this needs ~200 episodes to separate providers. Until then, priors matter more than the algorithm — start with an informed prior per provider class and let it move |
| Test | offline replay of logged turns with simulated latencies; report regret against an oracle that picks the best provider in hindsight |

---

### A5. Turn-end detection with spectral features — *DAA Unit V (FFT)*

| | |
| --- | --- |
| Where | `providers/engine_pipeline.py::_watch_for_turn_end` |
| Today | RMS against a single-pole adaptive noise floor |
| Build | windowed **FFT** (numpy `rfft`, 20–30 ms Hann windows) → **spectral flatness** and **zero-crossing rate**. Speech is harmonic and spectrally peaky; keyboard clatter, fans and TV hiss are flat. Replace the single-pole floor with a **p10 percentile over 2 s** |
| Why | this is the difference between "it cut me off" and "it waited two seconds" — the two most-complained-about behaviours in every voice assistant |
| Cost | ~1 ms per 30 ms frame, no model, no download, fully offline |
| Test | record 20 real turns including typing and TV noise; measure false-cut rate and stop-latency |

This is the one place in the DAA syllabus where **FFT is not a formality**: audio features are what
FFT is actually for, and `core/wake_word.py` + `core/viseme.py` (lip-sync) can reuse the same
spectral pipeline.

---

### A6. Trust and reputation for tools and sub-agents — *AIML Unit IV (software agents)*

| | |
| --- | --- |
| Where | new `core/reputation.py`; consumed by `custom_jarvis/failure_memory.py` and the sub-agent scheduler |
| Today | per-tool success is logged; nothing aggregates it into a decision |
| Build | a per-tool **Beta(α, β) reputation** updated on every outcome (success adds to α, failure to β), so expected success = α/(α+β) with an honest confidence interval from the Beta quantiles. Choose the tool with the best **lower** bound, not the best mean — same rule as your 0.70 threshold, and it automatically prefers a proven-but-boring tool over a shiny unproven one |
| Why | your AIML agents unit covers exactly this: agent communication, negotiation, **trust and reputation**. This is the cheapest place to make it real rather than theoretical |
| Test | replay failure logs; check the reputation ranking would have avoided the known-bad path |

---

## Tier B — worth it once Tier A is measured

| Syllabus topic | Where in Ultron | What it buys |
| --- | --- | --- |
| **Trie** (DAA II) | HUD command box, wake-word vocabulary, `core/app_resolver` prefix index | prefix autocomplete in O(len) instead of scanning; also the natural index for "apps starting with *what*" |
| **Viterbi / HMM** (AIML, probabilistic sequence) | `_watch_for_turn_end`, `main.py` turn assembly | segment a stream of frames into speech/pause states with a transition model instead of fixed thresholds — the *principled* version of A5 |
| **MinHash / shingles** (DAA V, randomized) | `_trimmed`, web-search results, `custom_jarvis/knowledge.py` | near-duplicate detection in O(1) per document; kills the "five copies of the same Stack Overflow answer" token waste |
| **Reservoir sampling** (DAA V, randomized) | `main.py` `_session_log`, `actions/proactive.py` | a fixed-size, unbiased sample of a long session for the digest, instead of "last 8 turns" (which is *recency bias*, not sampling) |
| **Greedy set cover** (DAA V, approximation) | tool declaration building, `providers/schema.py` | pick the smallest set of tool schemas that still covers the intent — MARK already halved the tool count by hand; this does it per turn, with the ln(n) guarantee written down |
| **Interval scheduling / graph coloring** (DAA III, IV) | sub-agent scheduler (5 roles, max 2 concurrent) | two lanes cannot both drive the mouse or the clipboard. Build the conflict graph, colour it, and let the greedy interval scheduler order the rest. This is the "why can't both run?" question answered properly |
| **Topological sort + Warshall closure** (DAA III, IV) | `custom_jarvis/planner.py` (810 lines, currently no dependency model) | a plan is a DAG of tool steps; topo order gives the execution order, transitive closure gives "which steps must be re-run if step 3 fails" |
| **Dijkstra / Bellman-Ford** (DAA III) | planner step selection under cost | cheapest path through a plan graph where edges carry latency and failure cost; Bellman-Ford only if you ever allow negative edges (a rollback "credit"), which you probably should not |
| **Logistic regression + calibration** (AIML III) | the ≥ 0.70 predictor | a *calibrated* probability, not a score. Reliability diagram and Brier score in the test harness; a model that says 0.7 must be right 70 % of the time or the threshold means nothing |
| **k-NN / k-means / k-d tree** (AIML V) | command similarity, app clustering, memory grouping | nearest-neighbour over command embeddings; k-d tree only if you go above ~1 k vectors in 2–8 dims — above that dim, tree pruning dies and brute force wins (classic exam point, and true here) |
| **Naïve Bayes** (AIML III) | local intent pre-classifier | a 2 ms local guess at "is this a command or a question", so the tool list can be trimmed before the model call |
| **SQLite FTS5 / B+ tree** (DAA II) | `custom_jarvis/knowledge.py` | the store is already a B+ tree — add an FTS5 virtual table and get BM25 ranking for free instead of writing a ranker |

---

## Tier C — syllabus topics that genuinely do not apply

Being able to say this is the point of the section.

| Topic | Why not |
| --- | --- |
| **Minimax / alpha–beta** (AIML II) | Ultron has no adversary. There is no opponent whose moves you model. Inventing a "game" to use it would be a worse assistant, not a smarter one. (Only applies if you add an actual game-playing tool) |
| **AO\*** (AIML II) | for AND/OR graphs with decomposable subgoals. Your planner's steps are mostly linear; the complexity would not earn its keep |
| **Fibonacci heaps** (DAA II) | the only real win is Dijkstra from O(E log V) to O(E + V log V), on graphs you do not have. Python's constant factors would swamp it. Know the result for the exam; do not build it |
| **Red-Black / AVL trees** (DAA II) | Python's `dict` and `sortedcontainers` already give you ordered maps with better constants. Building one here is a lab exercise, not an optimisation |
| **B-Trees / B+ trees** (DAA II) | SQLite *is* a B+ tree. The useful outcome is *understanding* index design in `knowledge.sqlite3`, not reimplementing it |
| **Strassen's matrix multiplication, convex hull, optimal BST** (DAA III) | no matrix algebra, no geometry, no static key distribution in this application |
| **Floyd–Warshall all-pairs** (DAA IV) | O(V³) on a graph of 20 tools is 8 000 operations — fine, but you do not need all pairs. Transitive closure (Warshall alone) is the only piece you would actually use |
| **Matrix-chain multiplication** (DAA IV) | the "ordering" analogue in prompts is not associative in the way matrix multiplication is; there is no cost model that makes DP correct here |
| **N-Queens / sum of subsets** (DAA IV) | no board, no subset-sum. The *technique* (backtracking with pruning) is already covered by A3, which is the honest reuse |
| **Deep RL** (AIML V) | RL needs episodes. A personal assistant generates maybe 20–50 a day, non-stationary, with no cheap simulator. Deep RL would not converge. Bandits with priors (A4) are the correct subset to use, and saying why is a better answer than shipping a Q-network |

---

## The part you actually asked about: the syllabus as *manner*, not just as code

You said the whole syllabus could shape how Ultron works, not only its algorithms. The AIML papers
are mostly about **how an agent reasons and what it is allowed to believe**, which is closer to
Ultron's behaviour than any sorting algorithm.

**Unit II (KR&R) → make the memory a knowledge base, not a hash map.** Today
`memory/long_term.json` is flat key → value with a category. Propositional/predicate structure means
facts get *types and relations* (`ayse —sister_of→ user`), and then **backward chaining** answers
"who is my sister?" by proving it from facts instead of substring-matching a key. `custom_jarvis/
goal_verifier.py` already wants to be a backward-chaining prover: a goal is proved from evidence
facts, or it is not done. That is a real upgrade in behaviour, and it is Unit II in code.

**Unit II (resolution, default reasoning) → contradictions and exceptions.** Two paths: **resolution
refutation** to detect when a new fact contradicts an old one (so Ultron *asks* instead of silently
overwriting — currently it overwrites), and **default reasoning** for preferences with exceptions
("speaks Turkish, except when discussing code"), which is exactly the shape real preferences have
and flat JSON cannot express.

**Unit IV (agents, negotiation, argumentation) → the repair loop.** Your self-repair currently asks
a human twice. Multi-agent argumentation says the *proposal* should be attacked before it reaches
the human: proposer → critic (cheaper model, looking for the failure mode) → adjudicator. That
reduces the review burden without removing the human, which is the constraint you set. Trust and
reputation (A6) is the same unit, applied to tools instead of people.

**Unit III (model evaluation) → the discipline Ultron lacks most.** Precision/recall, calibration,
train/test split, cross-validation. Right now the predictor is described as "calibrated ≥ 0.70"
without a harness that could prove it. Building that harness is worth more than any single
algorithm in this document, because it is what lets you say "this change helped" instead of "this
change feels better". If you build one thing from this file for your own learning, build this.

---

## Suggested order, with the honest reason

1. **A1** — visible, cheap, and it fixes a bug users hit daily.
2. **A6 + Unit III eval harness** — small, and it creates the measuring stick everything else needs.
3. **A2** — the clearest money win (tokens are your cost per turn).
4. **A3** — the one that makes Ultron *feel* deliberate about ambiguity.
5. **A5** — the one that makes conversation feel natural.
6. **A4** — last, because it needs data before it can beat a sensible default.

Every item ships with a fixture or replay harness, a before/after number in `log.txt`, and tests that
do not weaken any existing assertion. That is the same standard the last four phases were held to.

---

## If you want to use this for your course as well

Revise, in order of how often this codebase needs them:

**DAA:** dynamic programming (edit distance, knapsack, matrix-chain reasoning), greedy vs DP
(why greedy is 2-approximate here and exact there), Dijkstra with a binary heap, transitive closure,
master theorem for the recursive summariser, and approximation ratios — because you will write
"ln n approximation" in a code comment and someone will ask why.

**AIML:** search with admissible heuristics (A\*), branch and bound, Bayesian updating and Beta
distributions, calibration and evaluation metrics, and the agents unit — communication, negotiation,
trust. Skip minimax for this project; keep it for the exam.

A project report that says "the risk threshold is a B&B pruning bound", "context assembly is a
0/1 knapsack solved greedily with a bound", and "provider selection is a contextual bandit" is
describing a real system with real theory behind it. That is a much stronger report than one that
lists a syllabus and a screenshot.
