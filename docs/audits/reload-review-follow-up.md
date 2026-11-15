# Action/plugin generation reload review follow-up

## Status

- PR #12 is the review path; do not merge or push directly to `main`.
- Review-driven follow-up commit `983a9f6` is pushed to `arena/4c973188-ultron-agi-like-jarvis`; PR #12 remains open.
- CI run `42469609070` passed on Linux and Windows for `983a9f6`.
- CodeRabbit completed its manual review against the PR diff ending at `657b73b` (base `8f4803b`): 23 actionable comments (10 major, 7 minor, 4 nitpicks), plus failed pre-merge checks. It did not review `ae838e2` or `983a9f6`; the current PR check skips automatic review for this non-default target. Do not claim a CodeRabbit review of the follow-up.
- Kilo review cannot run because the account lacks credits. Preserve approval, rehearsal, and protected-referee boundaries.

## Findings addressed in the requested reload scope

1. **Manual reproduction — stale package attributes and split sibling identities.** Forced reload removed leaf names from `sys.modules` but could leave the old parent-package attribute; modules imported as candidate siblings could then be executed a second time. `ae838e2` detaches/reattaches parent attributes during clear/load/restore and reuses modules imported within the candidate. Regression tests cover both behaviors.
2. **CodeRabbit major — initial leaf signature scan could stop startup.** `LeafGenerations` now retains the discovered registries with an unknown signature after an `OSError`; the next safe `refresh()` retries the scan. Added a transient-scan-failure regression.
3. **CodeRabbit minor — mixed updater commits could reload leaves against old core code.** Mixed updates now persist `leaf_reload_deferred`; `main.py` skips leaf reload until a fresh process starts, then consumes the flag after loading the updated tree. Leaf-only updates still activate at reconnect. Added assertions for mixed, leaf-only, and restart-only updates.
4. **CodeRabbit nitpicks — protected policy identity and signature test baseline.** Forced action/plugin discovery now asserts the same `core.policy` module and `Tier` class objects remain loaded. The helper signature test separately verifies both creation and a subsequent edit.

## Broader review comments not addressed here

Other comments concern plan-state validation/resume and workspace binding, preview persistence, local fallback behavior, MCP robustness, memory-write atomicity, and other files outside this reload follow-up. CodeRabbit also reported PR-level scope, linked-issue, and docstring-coverage checks. These remain visible for owner triage; they are not described as fixed, and no broad PR reshuffle was made here.

## Verification

- Reload/generation/self-change focused tests: **52 passed**.
- Updater tests: **8 passed** (using a temporary dependency target for `requests`; no repository dependency files changed).
- `compileall` and `git diff --check` passed.
- The bare system-Python full `unittest discover` attempt was incomplete: 1,277 ran, 13 skipped, 25 setup/import errors due missing optional/environment dependencies. Do not treat it as a clean full-suite run.
- README discovered-test count is **1,732**. The prior configured broad run remains the historical result: 1,714 ran, 15 skipped, one Qt setup error from missing `libGL.so.1`.

## Next steps

1. Wait for run `42469609070`; report its actual Linux/Windows result before claiming the latest head is green.
2. If another CodeRabbit review becomes available, request it for the newest head; otherwise state that the findings above are from the review ending at `657b73b`.
3. Preserve open PR dependencies and candidate branches. `ArenaAi` remains needed while PR #8 or #12 depends on it.
