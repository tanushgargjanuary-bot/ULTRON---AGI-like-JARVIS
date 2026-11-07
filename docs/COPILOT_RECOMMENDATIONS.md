# Copilot Recommendations: Ultron Improvements and Scope

**Status:** Recommendations only; no implementation is authorized by this document.
**Prepared:** 2026-11-07
**Audience:** Human owner and coding agents working on this repository.

This document collects recommendations from a review of `main`, `chatgpt`, `antigravity`, and `opencode`, plus product-level ideas for making Ultron more useful, reliable, safe, and powerful. It is not a change to the project's governing decisions. Read `DECISIONS.md`, `ARCHITECTURE.md`, `AGENTS.md`, and the relevant tests before acting.

## Executive recommendation

**Do not merge either competing feature branch wholesale.** Keep `main` as the stable base; `opencode` matched `main` at review time. `chatgpt` and `antigravity` contain substantially the same local-model detector/router work. That work has promising pieces, but needs design corrections and owner approval before it is suitable for `main`.

The highest-value product direction is not adding the largest number of tools. It is making a small set of real workflows complete reliably, safely, and verifiably—with a clear plan, user control, evidence of results, and recovery when something fails.

**Important scope constraint:** `DECISIONS.md` currently states a feature freeze and describes local-model consent, size, and cloud-first constraints. These recommendations do not override those decisions. The owner must explicitly revise the governing decision before feature work that conflicts with it.

## Competing branches: review and merge guidance

### `main` and `opencode`

- At review time, `opencode` pointed to the same commit as `main`; no separate changes needed to be brought over.
- Continue using `main` as the integration baseline.

### `chatgpt` and `antigravity`

Both branches add local-model detection/routing, a `local_models` plugin and policy entry, tests, and portability/output-encoding changes. Their substantial feature diffs overlap; they should not be merged as two independent implementations.

**Prefer the `chatgpt` version as a starting point only**, not as merge-ready code:

- Its router honors `running_only=True` and returns `None` when there is no running candidate; the `antigravity` version falls back to an offline model, violating the option's apparent contract.
- It tests the running-only behavior.
- Its process-watcher test still needs correction: closing stdin immediately after detecting the child may not satisfy the existing duration assertion. Use an explicit handshake/synchronization protocol instead of a timing assumption.

**Potentially useful isolated changes, subject to tests:**

- `actions/video_player.py`: coerce model-supplied `action` and `source` to strings before calling string methods; add malformed-input tests.
- Provider tests: use `sys.executable` rather than assuming a `python3` executable exists.
- Text/subprocess tests: specify UTF-8 explicitly where platform-default encodings can break the test.

**Do not take without further evidence or owner approval:**

- Local-model auto-routing/configuration as currently designed.
- README test/file counts copied from one branch without generating and verifying them.
- Claims of fixed token-saving percentages without reproducible measurements.
- Replacing useful log symbols solely to avoid Unicode output issues; fix encoding at the relevant I/O boundary instead.
- Relaxing workspace limits based only on the fact that the project is hosted on GitHub; keep the actual workspace policy and its enforcement consistent.
- Safe-root changes that add subdirectories already covered by the existing home-directory root, unless tests demonstrate a concrete behavior change.

## Blocking design and test issues in the proposed local-model work

Before reconsidering this feature, address all of the following:

1. **Consent and policy:** The plugin's `status` action is observational, but `configure` persists provider settings. A single `OBSERVE` classification for both actions is too permissive. Split/classify actions so configuration uses the appropriate guarded approval flow. Any automatic change in which model receives a request must also honor the user's informed choice.
2. **Existing model-selection decision:** Reconcile the proposal with `DECISIONS.md`: local models are consent-based, quantized 1.5–3B, with vision opt-in and cloud-first heavy reasoning. Do not silently route heavy tasks to large local models unless the owner explicitly changes that decision.
3. **No unrequested fallback:** Preserve strict `running_only` behavior. Never return an offline model when the caller asked for a running model.
4. **Detector safety and robustness:** The code claims loopback-only probes, but ordinary URL openers follow redirects. Enforce loopback-only destinations across redirects, validate response shape and size, handle malformed entries, and place a bound on total scan time as well as each request.
5. **Machine-independent tests:** Unit tests must not inspect the developer's actual model servers, home directory, or model cache. Inject/mock the detector and filesystem. Keep environment-dependent integration checks separate and clearly marked.
6. **Real provider-path coverage:** Test provider ID parsing, correct base URL/model selection, missing configuration, timeouts, fallback ordering, recordings/images, and no-key operation using a local fake provider. Do not claim support merely because discovery returned a model.
7. **Staleness and observability:** Keep cached detection results from being mutated by callers; test expiry/refresh and failures. Report which model was selected and why, with local/cloud status and user-visible controls.
8. **Separate proposal from implementation:** Make the user-facing scope and privacy implications explicit before wiring the feature into the request path.

## Product-level opportunities

These are candidate directions, not an instruction to implement all of them. Rank against the owner's current scope and existing code before starting.

### 1. Verified, recoverable workflows — highest product value

Turn one-off tool calls into bounded workflows: plan the steps, show a preview when material changes are involved, execute through the existing policy/registry, verify each result with evidence, and report partial completion honestly. Add checkpoints and undo/rollback where possible. Keep confirmations tied to the actual risk; do not add redundant prompts for reversible routine actions.

**Good first pilot:** a user-approved Downloads-folder organization task with a dry run, exact proposed moves, approval, execution, evidence that files landed in the intended locations, and undo.

**Measure:** successful completion, wrong-side-effect rate, verification accuracy, recovery/undo success, and human interventions.

### 2. Local document question-answering (opt-in)

Allow the user to select folders, index documents locally, search them, and answer with citations to the source file and page/section. Provide pause, delete, re-index, and scope controls. Make local versus cloud processing explicit; never transmit private document contents to cloud services without clear user consent.

### 3. Transparent, consent-based model selection

If approved by the owner, improve model selection by checking actual provider capabilities and availability rather than guessing from model-name substrings. Display which provider/model will process a request, whether it is local or cloud, and the reason for the choice. Offer explicit opt-in/opt-out and a reliable manual override. Do not use a model outside the user's configured policy.

### 4. Safe, reusable skill workflows

Improve the existing data-only skill-pack model rather than introducing arbitrary generated code. Add a skill editor, validation, dry-run, test cases, explicit tool/permission declarations, enable/disable, and a clear execution history. Preserve the existing allow-list, workspace confinement, and policy gates.

### 5. Opt-in routines and reminders

For scheduled/background tasks, provide quiet hours, pause/stop, deduplication, cooldown, and a readable activity log. No focus theft or unsolicited sensor use. Ask before external, destructive, or account-affecting actions; do not speak over the user.

### 6. Trust and activity dashboard

Expose recent actions, approvals, files changed, undo options, sensors currently active, provider/model used, and verification evidence. Provide straightforward stop/revoke/forget controls. Treat the dashboard as an explanation and control surface, not a bypass around `core/policy.py` or the controlled registry.

## Engineering priorities that strengthen existing capabilities

1. **Test real end-to-end paths, not only component presence.** Use the existing proof-gate principle: distinguish a tool being present from the user's full interaction working. Preserve `PASS`, `PARTIAL`, `SKIP`, and `FAIL` meanings; never round a skip up to a pass.
2. **Strengthen consent and policy at the call site.** Every new or mixed-action tool needs action-specific classification and tests for both allowed and denied paths. Unknown tools should remain fail-closed. No feature or agent instruction may bypass `ControlledRegistry`, `EvidenceEngine`, or policy.
3. **Improve deterministic recovery.** For file changes, updates, and workflow steps, capture pre-state, verify post-state, and make rollback behavior testable. Report partial failures precisely rather than claiming success.
4. **Improve test determinism.** Replace fixed sleeps with events/handshakes or bounded condition polling. Keep tests independent of the host's optional applications, credentials, hardware, and local models.
5. **Measure before optimizing.** The README and project decisions already favor profiling measured bottlenecks. Optimize a demonstrated hot path and re-run the benchmark; don't rewrite languages or claim speedups based on arithmetic microbenchmarks alone.
6. **Keep privacy promises observable.** Make local/cloud routing and sensor state inspectable at the time of use. Keep secrets out of logs, prompts, caches, and commits.
7. **Keep documentation generated facts honest.** Regenerate counts/maps from scripts; do not copy stale numbers from a branch. Update tests and docs with the implementation, not before verification.

## Suggested staged plan

### Stage A — Stabilize and decide

- Keep `main` unchanged while the owner decides whether feature freeze remains in force.
- Run branch CI and relevant tests; inspect failures rather than accepting branch descriptions as proof.
- If local-model routing remains in scope, write/update the governing decision first.

### Stage B — Small, independently verifiable fixes

- Cherry-pick only portability/input-hardening changes with focused tests.
- Replace flaky process tests with explicit child-process synchronization.
- Confirm the complete Windows and Linux test/proof gates pass.

### Stage C — One approved vertical slice

- Pick one workflow or feature with a clear user need.
- Specify permissions, privacy, failure behavior, rollback, and measurable acceptance criteria first.
- Implement through existing architecture and safety gates; add unit, integration, and proof-gate coverage.
- Update generated maps/docs, then run `scripts/verify.py`, `scripts/proof_gate.py`, and `scripts/verify_all.py` on supported machines.

## Merge checklist for agents

- [ ] Read `DECISIONS.md`, `ARCHITECTURE.md`, `AGENTS.md`, and the relevant gatekeeper/test docs.
- [ ] Confirm the owner approved the scope, especially if a feature freeze or privacy/model policy changes.
- [ ] Compare against current `main`; do not merge a whole competing branch merely because its tests pass.
- [ ] Preserve every safety invariant; new capabilities need policy classification and denial-path tests.
- [ ] Add deterministic tests for success, failure, malformed input, missing dependencies, and rollback.
- [ ] Run applicable tests and proof gates; report exactly what ran and what was skipped.
- [ ] Regenerate maps/counts and update truthful docs.
- [ ] Keep commits minimal and explain any intentional deviation from existing decisions.

## Source files reviewed

- `readme.md`
- `ARCHITECTURE.md`
- `DECISIONS.md`
- `core/policy.py`
- `core/gemini.py`
- `providers/registry.py`
- `tests/test_suite_safety.py`
- `tests/test_process_watch.py`
- Branch comparisons: `main...chatgpt`, `main...antigravity`, `main...opencode`

These recommendations reflect the tree and branch heads available during review on 2026-11-07. Re-check current branch heads and governing decisions before implementation.
