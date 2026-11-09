# Branch review: what each branch holds, and what is worth taking

**Status:** Historical recommendations plus dated branch-tip and candidate audits. This is not blanket authorization to merge any branch; follow the owner's reviewed-PR and protected-file constraints.
**Prepared:** 2026-11-07 · **Re-measured:** 2026-11-08
**Audience:** Human owner and coding agents working on this repository.

This document collects recommendations from a review of every branch that exists on the remote, plus product-level ideas for making Ultron more useful, reliable, safe, and powerful.

## Where the branches actually point (measured 2026-11-07)

| Branch | Tip | What it is |
|---|---|---|
| `main` (default) | `44ec6db` | the stable base |
| `arena/4c973188-ultron-agi-like-jarvis` | this session's branch | documentation, then the defect pass: the workspace report, the two red tests, the size budget withdrawn, CI on this branch |
| `chatgpt` | `c98ea0f` | capability routing, a read-only GitHub scout, three doc commits. **Idle since the afternoon.** |
| `antigravity` | `b8e9334` | a repository miner and a 2,438-repo catalog, plugin bridges, an undo pass, and — late in the day — its own attempt at issues #3 and #4. **Moving while this was written.** |

Measured again at 21:30 IST on 7 Nov. `antigravity` moved four times during this session
(`857f3dc` → `ad53e69` → `60c43b5` → `b8e9334`), so any row here is a photograph, not a fact.
`python scripts/branch_report.py` is the live answer.

The branch called `copilot` no longer exists: it was renamed, then folded into one branch.
`opencode`, which an earlier version of this page reviewed, is not on the remote. **Re-run
`python scripts/branch_report.py` before relying on any row here.** It is not a change to the project's governing decisions. Read `DECISIONS.md`, `ARCHITECTURE.md`, `AGENTS.md`, and the relevant tests before acting.

## Executive recommendation

**Do not merge either competing feature branch wholesale.** Keep `main` as the stable base; `opencode` matched `main` at review time. `chatgpt` and `antigravity` contain substantially the same local-model detector/router work. That work has promising pieces, but needs design corrections and owner approval before it is suitable for `main`.

The highest-value product direction is not adding the largest number of tools. It is making a small set of real workflows complete reliably, safely, and verifiably—with a clear plan, user control, evidence of results, and recovery when something fails.

**Important scope constraint:** `DECISIONS.md` currently states a feature freeze and describes local-model consent, size, and cloud-first constraints. These recommendations do not override those decisions. The owner must explicitly revise the governing decision before feature work that conflicts with it.

## Competing branches: review and merge guidance

### `main`

- Continue using `main` as the integration baseline.
- The renamed `copilot` branch was `main` plus one documentation commit; that commit is on the
  session branch, so nothing is stranded by the rename.

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
- Branch comparisons: `main..chatgpt`, `main..antigravity`, `main..` the session branch.
  Two-dot comparisons, because this checkout is shallow and has no merge base.

These recommendations reflect the tree and branch heads available during review on 2026-11-07. Re-check current branch heads and governing decisions before implementation.

## What the two branches actually held (measured 7 Nov, after reading them)

Not opinions. Each line below was produced by running the check named beside it.

| Finding | How it was checked | What it means |
|---|---|---|
| `chatgpt`'s five tests had **never run** | `python -m unittest tests.test_capability_guide` → *Ran 0 tests* under the suite's `unittest discover` | The file was written pytest-style, with a `monkeypatch` fixture. In this repository that is a file the suite skips. Rewritten in unittest shape on `ArenaAi`; all five pass now. |
| `antigravity`'s "context-aware prompt elevation" elevates nothing | `git grep 'describe('` on both branches | The new `priority_categories` argument is never passed by a caller — not on their branch, not on mine. The parameter is real; the feature is not connected. |
| `core/routing.py` is called by nothing in the application | `git grep 'core.routing'` | Only `tests/test_routing.py` imports it. Issue #3 names this. `antigravity`'s `60c43b5` wires it through a `core/intent_router.py` that does not exist here, so the claim cannot be checked from this branch. |
| `main`'s tip is a **revert** | `git show --stat 44ec6db` | 793 lines removed, including `core/local_detector.py`, `core/local_router.py` and `plugins/local_models.py`. The local-model plumbing that remains is the three config keys read by `core/llm_client.py`. |
| A size or "the branch is big" claim is not a reason to refuse it | `chatgpt` is 17 commits over 5 files (+392); `antigravity` is 37 files (+5,108) | Small branches rot too. `chatgpt`'s work went stale for hours while its tests could not run. |

### What was taken, and what was left

**Taken** (`5f576d8`): `actions/capability_guide.py`, `actions/github_repo_scout.py`, the
`core/prompt.txt` line, and the doc `docs/CAPABILITY_AWARENESS.md` — with the tests rewritten
so they execute.

**Left, deliberately:** everything else on both branches. `antigravity` is mid-flight; taking
half of a moving branch is how a merge becomes a second merge.

## 2026-11-08 — live promotion and candidate audit

**Branch/PR topology, rechecked from the repository:** `main`=`44ec6db`, `ArenaAi`=`7dcf2d6`, `chatgpt`=`c98ea0f`, `antigravity`=`b8e9334`, and the arena worktree starts at `d4a57c9`. PR #12 is open from the arena branch to `ArenaAi`; PR #8 is open from `ArenaAi` to `main`. Do not delete `ArenaAi` while either PR depends on it. There are no open PRs from `antigravity`. No branch was deleted in this audit.

The owner wants gradual promotion through reviewed PRs, not a wholesale branch merge or a direct write to `main`. The current PRs are broad, so their green CI is evidence about the tested tree, not approval to merge. Keep the arena changes isolated and reviewed in #12; do not treat #8 as an automatic promotion. Before any future main promotion, choose a narrow, independently reviewable slice and preserve the ordered PR dependency.

**Deletion decision:** neither `chatgpt` nor `antigravity` is safe to delete yet. The endpoint comparison `ArenaAi..chatgpt` still differs in 51 files, including an alternate local detector/router, and also removes newer handover, verification, and workspace files. The endpoint comparison `ArenaAi..antigravity` differs in 98 files. Keep both candidate refs until useful changes have been audited and either carried selectively or deliberately discarded with the owner informed. `chatgpt`'s previously carried capability-guide/scout work does not mean its complete current endpoint is redundant.

**Selective `antigravity` review (no code carried):**

- The OCR candidate adds `core/ocr.py` and an OCR choice to `core/ui_ladder.py`, but `extract_words()` has no application call site in the reviewed branch. The tests mock both OCR backends and also include a live `ocr_available()` test that depends on the test machine. The MiniCPM bridge is a separate optional service path. This is a starting point, not an integrated OCR rung; before carrying it, connect a bounded local OCR operation to the actual UI workflow and add deterministic tests for image size/type, no backend, errors, and the no-upload promise.
- `core/intent_router.py` defines keyword classification and a route logger, but a repository search found no production call to `route_request()`. Its tests exercise classification/routing in isolation; this is not yet application routing. Do not advertise it as a live capability or carry it as a connected feature without call-site and configured-provider tests.
- `actions/plugin_forge.py` is guarded as a tool, but its "sandbox" is a same-user subprocess with a timeout, not an OS security boundary. The AST check does not make arbitrary Python safe. The model-supplied `tier` parameter can register a forged plugin as `observe` or `routine`, affecting future approvals. Do not carry this forge without an actual isolation boundary and a policy design that cannot self-lower a generated tool's risk.
- The wider branch includes protected-adjacent and runtime changes; inspect each exact diff and its tests before selection. In particular, do not touch `core/self_change.py` without explicit owner approval, and preserve the laptop/cloud trust boundary.

**Current session slice (historical):** action/plugin generation staging and reconnect-boundary reload code were pushed as `e763747`; the README count correction is `f5a090b`. The self-updater distinguishes reloadable leaves from core/application code, and the self-change tool explains the boundary behavior. Focused generation tests (134) and updater/self-change tests (16) passed; the full 1,714-test local run had the then-known missing-`libGL.so.1` Qt setup error. Deep scan reported zero high findings. PR #12 run `42464882412` passed Linux and Windows. No live UI session exercised a real generation swap; details are in `OwnerFiles/history/session-log.md`.

### Fresh branch audit and selective fixes (8 Nov 2026)

**Starting snapshot, before these fixes:** active `HEAD=9c41bb1d16051ddbe5f710fc13ca387aec0fe5a8`; refreshed remote tips: `ArenaAi=8f4803b8812e`, `antigravity=b8e9334484bb`, `chatgpt=c98ea0ff81a4`, `code-quality-and-security-improvements-af08a=bc65a2746d5a`, `main=44ec6dbde867`. Evidence: `git fetch origin '+refs/heads/*:refs/remotes/origin/*'`, `python scripts/branch_report.py`, `git rev-list --left-right --count HEAD...<ref>`, and `git diff --shortstat $(git merge-base HEAD <ref>) <ref>`. Relative to that HEAD, ArenaAi and main had no unique commits; antigravity had 10 graph-unique commits (41/10 left/right), chatgpt 20 (38/20), and code-quality 1 (33/1). Three-dot candidate diffs: antigravity 57 files (+7,070/−180), chatgpt 7 files (+427), code-quality 2 files (+197/−2). These are merge-base deltas, not a recommendation to merge.

**After the selective fixes:** local active `HEAD=ddd788ea1ff987e6d384080c7f83cd2fef3437ea`, three commits after the starting snapshot. The remote active ref and PR #12 still point to `9c41bb1` until the local commits are pushed.

**PR state:** #12 is open, non-draft, active → ArenaAi; #8 is open/draft, ArenaAi → main; #13 is closed/unmerged, code-quality → `qwen-coder`; #1 is merged, chatgpt → main. Before the new local commits, `gh pr checks 12` on remote head `9c41bb1` reported Linux and Windows passing (run `42470211234`), Kilo Code Review failing, and CodeRabbit skipped; GitHub reported `mergeStateStatus=UNSTABLE`. Those checks do **not** cover the three local commits. Preserve the #12 → ArenaAi → #8 route; no main write or branch operation was performed.

| Candidate | Evidence and decision |
|---|---|
| `origin/ArenaAi`, `origin/main` | Already ancestors of the active line; no novel commits to port. Keep the active branch and current PR route. |
| `origin/chatgpt` | Do not port the endpoint wholesale. Its capability-guide refactor removes useful helper separation; its scout duplicates the shared GitHub search path; its tests use pytest-style fixtures while this repository's suite is unittest-based. No isolated delta justified changing the active tree in this pass. |
| `origin/antigravity` | No feature ported. The reviewed OCR and intent-router paths lack production call sites; plugin-forge subprocess is not a security boundary and its model-controlled tier can lower future approvals; file-controller diff drops a per-entry sensitive-file check; other diffs regress active memory/history and runtime behavior. Local-model and clipboard paths still need the recorded consent/privacy/provider checks. See the detailed source findings above; no branch was checked out or executed. |
| `origin/code-quality-and-security-improvements-af08a` / PR #13 | The closed branch adds a security test file and README, not implementation fixes. Its SSL test contacts `expired.badssl.com` and was deliberately not run. Three test findings were independently reproduced against active source; their **locally authored fixes**, not branch implementation, are applied below. The README count is stale. |

**Selected and locally implemented (no cherry-picks):**

1. `custom_jarvis/tools.py`: removed the SSL-error retry with `verify=False`; certificate failures now return an explicit failed `ToolResult`. A mocked `requests` module tests the real function offline, asserts exactly one request, and verifies the error path. No internet or dependency installation is involved.
2. `core/crash.py`: redacts `Authorization: Bearer …` while preserving the header label; `tests/test_crash.py` asserts that a representative token is absent.
3. `actions/dev_agent.py`: resolves a real `Code.exe` path and launches its argument list with `shell=False`, rather than passing a project path through `cmd.exe`. `tests/test_policy.py` checks launchers' AST and mocks the direct executable invocation.

**Commits on the active local branch:** `53fc208` TLS verification, `b3bb417` bearer-token redaction, and `ddd788e` safe VS Code launch. Each commit contains one fix and its regression test; no files from the pre-existing dirty worktree were staged. No dependency was added. Before these fixes the worktree had 24 modified tracked paths and one untracked UI test. The three commits removed their six files from the dirty set; the branch-review, handoff, and log updates below are separate documentation work. Backups remain at `/tmp/ultron-preintegration-20261107.patch` and `/tmp/test_dashboard_ui_variants-preintegration-20261107.py`.

**Verification:** `python -m unittest tests.test_crash tests.test_web_platforms tests.test_policy -q` — 93 passed; `python -m compileall -q` on the six code/test files — passed; `git diff --check` — passed. `python scripts/verify.py` parsed 274 Python files, then exited 1: 1,295 tests, 25 errors, 13 skipped, 1 failure. The failure is the README Python-file count (README says 273; the tree has 274); errors include absent `httpx`, `numpy`, `psutil`, Playwright, and Qt/platform modules. Full-suite status is therefore not green on this sandbox. `scripts/proof_gate.py` and `scripts/verify_all.py` were not run: their configured claims can record from the microphone or capture the screen/camera, and this task did not authorize sensor access; the sandbox also is not the target Windows PC. The existing PR checks above are for the old remote head, not these commits. All code commits remain on the active branch; no main write or merge occurred.

### Follow-up — branch carry-forward status (7 Nov 2026)

The earlier “not safe to delete yet” assessment is now superseded by a comparison of the refreshed tips and actual tree deltas. `origin/chatgpt`'s net seven-file change from the common base is capability-guide routing, its read-only GitHub scout, tests, and documentation. Those are present on this active branch: task cues/outcome synonyms and the unavailable-tool behavior are retained; the tests run under `unittest`; the scout reuses `core.github.SEARCH` and remains metadata-only. `git diff origin/chatgpt..HEAD` shows only the helper extraction/shared-endpoint/test-shape differences for those paths, not a missing useful feature. **Recommendation:** `origin/chatgpt` is a branch-deletion candidate after the owner accepts the carried implementation and deliberately declines the divergent work not present in its net tree. No deletion was performed.

`origin/antigravity` remains **not yet a deletion recommendation**. The previously documented OCR, router, and plugin-forge gaps still apply; the 2,438-repository YouTube-derived catalog is redundant with the focused, read-only GitHub scout and is not an update mechanism. Other unique changes either overlap existing undo/tool catalogs, require privacy/policy decisions, or regress existing safeguards. No God’s Eye View content is being carried. Keep the branch until the owner explicitly accepts those deliberate rejections or the remaining changes receive a fresh audit.

The earlier defer choice applies to discovered third-party repositories: keep `actions/github_repo_scout.py` read-only, with no clone, install, synchronization, or code execution. The owner now wants a private owner-development repo for Ultron's self-edits and a public professional upstream; the private-release and supervisor design is recorded in `docs/UPDATE_ARCHITECTURE.md`, but is not implemented yet. Do not conflate Ultron's own reviewed source releases with auto-updating arbitrary discovered repositories.

One additional antigravity finding was worth carrying narrowly: `Ledger.calibration()` excluded an exact confidence of `1.0` from every calibration bucket because the top range used an exclusive upper bound. The bug reproduced with a deterministic test; the local fix rounds bucket boundaries and includes `1.0` in the final bucket only. It does not port the branch's broader weighted-bandit changes. The 87 focused capability, fuzzy/app-resolver, and metacognition tests now pass together.

### Follow-up — bounded fuzzy-distance candidate (7 Nov 2026)

The code-quality branch's useful long-input finding is now carried as a small local fix, not by importing its whole test file. `core/fuzzy.py` caps the full Damerau–Levenshtein matrix at 200,000 cells; an over-budget, non-empty pair returns `max(len(a), len(b))` as a conservative non-match sentinel (and therefore similarity zero). Exact matches and empty-string cases remain exact. The regression uses a 500-character near-match to test the cutoff without risking a huge allocation if the guard is later removed. The branch's external-network test, loopback-only dashboard assertion, and stale README count remain deliberately unadopted.

Verification on the current worktree: `python -m unittest tests.test_fuzzy tests.test_app_resolver -q` — 53 passed; `git diff --check` — passed. These two source/test edits and this note are local and uncommitted; they have not been pushed, so PR #12 checks do not cover them. PR #13 is closed. **Branch recommendation:** `origin/code-quality-and-security-improvements-af08a` is a deletion candidate once the owner is satisfied that the safe fuzziness fix is present and the rejected tests/README are intentionally discarded. No branch was deleted.

## Final consolidation review and branch cleanup (2026-11-09)

This section is the current decision. It supersedes the earlier 7–8 November recommendations that said to keep some development branches open pending review.

### Measured branch graph

| Branch | Ahead of main | Behind main | Three-dot changed files | Result |
|---|---:|---:|---:|---|
| `ArenaAi` | 18 | 0 | 41 | Its commits are ancestors of the integration base. |
| `arena/4c973188-ultron-agi-like-jarvis` | 50 | 0 | 148 | Five commits behind integration; no branch-unique commit remains outside integration. |
| `antigravity` | 10 | 8 | 57 | Ten graph-unique commits reviewed. Selected work was adapted; unsafe or incompatible items are explicitly deferred. |
| `chatgpt` | 20 | 5 | 7 | Capability guide and GitHub scout are present in the integration line; local inventory is retained in safer, read-only form. |
| `code-quality-and-security-improvements-af08a` | 1 | 0 | 2 | Test and README delta only. No distinct implementation change. |
| `integration/best-of-all-2026-11-09` | 55 | 0 | 163 | Chosen consolidation base. |
| `ultron/consolidation-2026-11` | 143 | 0 | 176 | Selected integration plus fixes, tests, and repository workflow updates. |

The comparison confirms that `ArenaAi` and `arena/4c973188-ultron-agi-like-jarvis` are already contained in the integration line. The consolidation branch is 88 commits ahead of the integration base, with 38 files changed against that base. These figures are commit-graph comparisons with `main`, not a claim that every changed line from each divergent branch was copied verbatim.

### Carried work and deliberate exclusions

- **Integration base:** retained as the base. The web reader, capability guide, read-only GitHub scout, MCP bridge, plan checkpoints, health center, bounded fuzzy matching, crash redaction, and related tests remain in the candidate.
- **ChatGPT branch:** the capability lookup and read-only repository scout are retained. The local-model inventory is read-only. The provider-configuration action is not exposed as a status operation.
- **Antigravity branch:** session-summary search was adapted into `memory/memory_manager.py`. The ADHD, Caveman, token-saver, and diff-minimalist skills were already present with identical content. The bandit and metacognition implementation were already present in the integration line. The NTFS alternate-data-stream path guard was adapted into `actions/file_controller.py` with a platform-specific regression test.
- **Antigravity exclusions:** plugin forge, crawler bridge, OCR bridge, clipboard context detection, keyword intent router, and agent monitor bridge were not promoted. Their current designs add policy, SSRF, path/consent, call-site, or observability risks. Its expanded undo API was not copied because its metadata argument and removal helpers do not match the current `core/undo.py` interface.
- **Code-quality branch:** its security test file contains stale imports and a live external-network test; its README count is stale. The useful ideas were reviewed and implemented separately with deterministic tests: bounded fuzzy distance, TLS verification without an insecure retry, bearer-token redaction, and safer executable launch.
- **Self-modification:** the consolidation adds content hashes to proposals. Apply refuses to overwrite a file changed since proposal creation. Revert refuses to overwrite a file changed after apply.

A branch's code was either carried forward as a tested implementation, found already present in the integration base, or explicitly rejected with a recorded reason. No wholesale merge was used.

### Verification and promotion

The earlier consolidation CI runs 112 and 113 passed on commit `f93b8f6cbb55a5baa44fe95f409cf52948f5fbc4` on both Linux and Windows. Later commits add the NTFS path guard, its tests, documentation, all-branch CI, and the archive workflow. Those later commits require a fresh CI result before promotion.

PR #14 (`ultron/consolidation-2026-11` → `main`) is the promotion path. Merge only after Linux and Windows pass on its latest head.

### Archive and deletion decision

After PR #14 merges, `.github/workflows/archive-reviewed-branches.yml` creates immutable tags for the exact reviewed tips, verifies every tag, then removes only the seven named temporary branch refs. It aborts if a source branch moved from its reviewed SHA. `main` is not in the deletion list.

The archive tag names and restore commands are in [BRANCH_ARCHIVE.md](BRANCH_ARCHIVE.md). The intended end state is one working branch, `main`, plus immutable archive tags. New work uses short-lived feature/fix branches and CI runs for every pushed branch.
