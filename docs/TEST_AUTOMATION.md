# Test automation and verification lanes

## Purpose

Every branch update needs quick feedback. A complete ULTRON verification run is more expensive because it installs UI and platform dependencies, exercises the full unit suite, performs seeded stress and mutation checks, and evaluates platform-specific proof claims.

The repository now uses two lanes. The fast lane runs on every branch push. The full lane runs on pushes to **main** and pull requests that target **main**.

Latest verified baseline: `077793d7fd846f871f269362759d97c198ec61c5`.

- Fast gate: [run 42832819956](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42832819956), 5/5 groups in 13.12 seconds.
- Full Linux/Windows gate: [run 42832820093](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42832820093), both jobs passed; 2,073 tests per platform, 1,000 seeded stress scenarios and 15 targeted mutations per platform.
- Archive workflow: [run 42832819947](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42832819947), passed; 12 exact-SHA tags verified.


These workflows produce automatic status checks. They do **not** guarantee that GitHub blocks a merge when a check fails. On 2026-11-10, the connected GitHub integration returned HTTP 403 when reading `main` branch protection. Required-check enforcement is therefore **not verified** by this audit.

## Lane 1 — fast branch gate

Workflow: **.github/workflows/fast-checks.yml**
Runner: Ubuntu, Python 3.12
Hard job limit: 8 minutes
Local command: **python scripts/fast_verify.py**

The workflow:
1. Checks out the commit with Git history so it can identify the exact update range.
2. Runs **git diff --check** for whitespace and conflict-marker errors.
3. Runs Ruff on changed Python files. It fails on selected Python correctness errors.
4. Runs the offline fast verification script.
5. Regenerates the module/test map and fails when the committed `docs/MAP.md` is stale.
6. Cancels an older in-progress run for the same branch or pull request when a newer update arrives.

The workflow installs Ruff for the changed-file static check, plus `requests` and `jsonschema` for imports used by the existing stress suite. These packages are not used to make live provider or model requests.

The Python fast verification script:
- reads tracked and untracked, non-ignored paths through Git's NUL-delimited output;
- rejects malformed, duplicate, missing, symlinked, and path-traversing Python paths;
- parses every discovered Python file without importing it;
- verifies that the generated `docs/MAP.md` matches the current source/test tree;
- tests its own path, syntax, timeout, missing-executable, and nonzero-exit handling;
- runs the policy/confirmation regression tests;
- checks README path and claim contracts;
- runs the deterministic repair stress suite.

The existing stress suite covers 1,000 seeded scenarios across input normalization, bounded-output rejection, workspace escape attempts, quarantine after ambiguous failures, abstention on unreviewed inputs, literal filename preservation, cross-workspace abstention, expired reviews, and repeated lifecycle/rollback behavior.

This lane is deliberately offline. It does not call a live model, provider API, or paid service. It does not prove Windows UI behavior or physical hardware behavior.

## Lane 2 — full regression and platform gate

Workflow: **.github/workflows/verify.yml**
Triggers: push to **main**, pull request targeting **main**, or manual dispatch.

It retains the existing deeper checks:
- complete Python syntax and unit/regression suite;
- upstream provider/UI self-tests;
- the seeded stress suite;
- 15 targeted mutation checks;
- module organization checks;
- proof gate on Linux and Windows;
- Windows-native and platform-aware instrument checks;
- machine-dependent skips and limitations recorded in the Actions output and artifacts.

The full suite has not been removed or weakened. It now runs on the integration path, not on every exploratory feature-branch push.

## Local use

Run the quick preflight before committing or pushing:

    python scripts/fast_verify.py

Run the complete offline and regression suite before proposing an integration:

    python scripts/verify.py
    python scripts/proof_gate.py

Run the machine verifier on the actual target computer when the change depends on Windows, display, audio, camera, browser, GPU, or installed applications:

    python scripts/verify_all.py

A fast pass is not a full pass. A skipped hardware check is not a pass. A green CI result proves only the checks that actually ran on that commit and runner.

## Branch and merge policy

- **main** is the only permanent integration branch.
- Main-only work is the default for small, low-risk, non-parallel changes when the owner authorizes it.
- Use a short-lived branch only when isolation, parallel work, or rollback risk provides a clear benefit.
- Every temporary branch must have a narrow scope and target **main**. Never create permanent branches for agents or models.
- A branch push runs the fast gate. A PR to **main** runs both fast and full verification. A push to **main** runs both the fast and full gates.
- Delete temporary branches after successful integration. Preserve protected archive tags and historical project records.

## Merge-blocking status checks

To make the test system a hard merge gate, configure branch protection for `main` to require these exact status checks:

- `fast offline gate`
- `linux — suite and instruments`
- `windows — the machine the claims are about`

The fast gate also runs on every branch push. The full checks run on pull requests to `main` and pushes to `main`. Verify the required-check list in GitHub after changing repository settings. This session could not inspect or change branch protection because the API returned HTTP 403. Do not claim that failed checks block merges until the settings have been read back and verified.

## Failure handling

- A failed fast check fails the workflow. Read the first failing step and reproduce it locally.
- A timeout is a failure, not a skip.
- A missing executable is a failure, not a pass.
- A malformed or unsafe source inventory is a failure, not an empty test run.
- Do not bypass a failure with **continue-on-error**, a false-positive filter, or a weaker assertion.
- Review the exact commit SHA and workflow run. Do not treat an older green run as evidence for a later push.
