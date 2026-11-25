# Test automation and verification lanes

## Purpose

Every branch update needs quick feedback. A complete ULTRON verification run is more expensive because it installs UI and platform dependencies, exercises the full unit suite, performs seeded stress and mutation checks, and evaluates platform-specific proof claims.

The repository uses three lanes. The fast lane runs on every branch push. The full lane runs on pushes to **main** and pull requests that target **main**. The third, the fresh-install lane, is not a required check: it runs when a requirements or launcher file changes, once a month, and by hand.

Latest verified main commit: `e1237d2e82ad7b981362f009baf568f7873415ea` (2026-11-10; documentation-only commits after the application/test baseline).

- Fast gate: [run 42876494264](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42876494264), success; 5/5 groups. It parsed 309 Python files, passed 19 runner edge tests, 30 policy/confirmation tests, 8 README contract tests, and 1,000 seeded stress scenarios. Ruff, diff checks, and generated-map validation passed.
- Full Linux/Windows gate: [run 42876494213](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42876494213), both jobs succeeded on `e1237d2e82ad7b981362f009baf568f7873415ea`. The application/test baseline `b80919314f391e15ddd86e2860c2e4d66057b15b` recorded 2,073 tests per platform, 1,000 seeded stress scenarios, and 15 targeted mutations per platform; the current workflow re-ran the same verification scripts successfully.
- Archive workflow: [run 42876494242](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42876494242), success; 12 exact-SHA recovery tags re-verified in archive-only mode. Branch refs were preserved.


These workflows produce automatic status checks, and `main` requires them: `GET /repos/<owner>/<repo>/branches/main`, read on 2026-11-20, reports `main` as protected with the three required status checks `fast offline gate`, `linux — suite and instruments` and `windows — the machine the claims are about`, at `enforcement_level: non_admins`. A pull request whose checks fail is therefore blocked for everyone who is not an administrator. Administrators are not bound (`enforce_admins` was read back as false on 2026-11-12, see `docs/specifications/SYSTEM_OVERVIEW.md`), so an administrator can push straight to `main` and the checks then only report. That has happened: every `verify` run on `main` from 2026-11-15 to 2026-11-20 (14 failed, 8 cancelled by the next push) is a push event, and GitHub lets a commit reach a branch that requires checks by direct push only when the pusher is exempt from the rule. The audit of 2026-11-11 could not read branch protection (HTTP 403) and recorded the enforcement as unverified; the full protection record (`/branches/main/protection`) still returns 403 to the integration used on 2026-11-20, so `enforce_admins` was not re-read then.

## Lane 1 — fast branch gate

Workflow: **.github/workflows/fast-checks.yml**
Runner: Ubuntu, Python 3.12
Hard job limit: 8 minutes
Local command: **python scripts/fast_verify.py**

The workflow:
1. Checks out the commit with Git history so it can identify the exact update range.
2. Runs **git diff --check** for whitespace and conflict-marker errors.
3. Runs the lint ratchet (`scripts/lint_ratchet.py`): Ruff with rules `E4,E7,E9,F` on every changed Python file, compared with the same file at the base of the change. A file may not have more findings of a rule than it had, and a new file starts at zero; findings a file already had do not fail a change that did not make them. The comparison is a count per file and rule, so a change that fixes one finding and adds another of the same rule passes. It exits 2, and the step fails, if Ruff or Git cannot be run. Before this, every finding in a touched file failed the gate (`ui.py` has 97), so a one-line change there could not pass without cleaning the whole file. Locally: `python scripts/lint_ratchet.py --base origin/main`.
4. Runs the offline fast verification script.
5. Regenerates the module/test map and fails when the committed `docs/MAP.md` is stale.
6. Cancels an older in-progress run for the same branch or pull request when a newer update arrives.

The workflow installs Ruff (the version pinned in `requirements-dev.txt`) for the lint ratchet, plus `requests` and `jsonschema` for imports used by the existing stress suite. These packages are not used to make live provider or model requests.

The Python fast verification script:
- reads tracked and untracked, non-ignored paths through Git's NUL-delimited output;
- rejects malformed, duplicate, missing, symlinked, and path-traversing Python paths;
- parses every discovered Python file without importing it;
- verifies that the generated `docs/MAP.md` matches the current source/test tree;
- tests its own path, syntax, timeout, missing-executable, and nonzero-exit handling;
- runs the policy/confirmation regression tests;
- checks README path and claim contracts;
- runs the tool dispatch smoke test (`tests/test_dispatch_smoke.py`): every plugin in `plugins/` called
  through the real dispatcher with the arguments a model would send, so a fault on the path every tool
  takes fails here and not only on Windows;
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

## Lane 3 — fresh install (not a required check)

Workflow: **.github/workflows/install-check.yml**
Triggers: a push to **main** or a pull request that changes `requirements.txt`, `requirements-dev.txt`, `setup.py`, `scripts/bootstrap.py`, `scripts/check_install.py`, `run.bat`, `run.ps1` or the workflow itself; the 15th of every month; manual dispatch.

Why it exists: lanes 1 and 2 install a short list written into the workflow, never `requirements.txt`. A change to that file, or a dependency that shipped a bad release inside its allowed range, was never installed by anything, so a green run said nothing about whether a fresh clone installs. Dependabot's #34 showed it: on Python 3.11 its file could not be installed at all, and every check was green.

- `install`: a clean Windows machine for each Python the launcher accepts (read from `MIN_PY` and `MAX_PY` in `scripts/bootstrap.py`, which a test keeps in step). It runs `scripts/bootstrap.py` exactly as `run.bat` does, then `scripts/check_install.py`, because the launcher lets an optional package fail to install and still exits 0. The job summary lists what a fresh install gets today.
- `suite`: Linux with every package installed (`requirements.txt` and `requirements-dev.txt`), running the whole suite. The short list has no `fastapi`, so the phone dashboard's tests skip in lanes 1 and 2; here they run.

Neither job is a required check, on purpose: a slow or failing install must not block an unrelated merge. Read them on any pull request that touches a requirements file, and before merging one.

## Local use

Run the quick preflight before committing or pushing:

    python scripts/fast_verify.py

Run the complete offline and regression suite before proposing an integration:

    python scripts/verify.py
    python scripts/proof_gate.py

Run the machine verifier on the actual target computer when the change depends on Windows, display, audio, camera, browser, GPU, or installed applications:

    python scripts/verify_all.py

To see whether `requirements.txt` really installed in the environment you are in (it installs nothing):

    python scripts/check_install.py

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

The fast gate also runs on every branch push. The full checks run on pull requests to `main` and pushes to `main`. Verify the required-check list in GitHub after changing repository settings; it was read back on 2026-11-12 and on 2026-11-20 (above). It does not stop an administrator pushing a failing commit to `main`, and the red streak of 2026-11-15 shows it happening: turning on "do not allow bypassing the above settings" is the owner's decision.

## Failure handling

- A failed fast check fails the workflow. Read the first failing step and reproduce it locally.
- A timeout is a failure, not a skip.
- A missing executable is a failure, not a pass.
- A malformed or unsafe source inventory is a failure, not an empty test run.
- Do not bypass a failure with **continue-on-error**, a false-positive filter, or a weaker assertion.
- Review the exact commit SHA and workflow run. Do not treat an older green run as evidence for a later push.
