# Action/plugin generation reload review follow-up

## Status

- PR #12 is the review path; do not merge or push directly to `main`.
- The follow-up fix is pushed as `ae838e2` on `arena/4c973188-ultron-agi-like-jarvis`; PR #12 remains open.
- The last confirmed green CI run is `42465596629` on `657b73b` (Linux and Windows). Run `42467967280` for `ae838e2` is queued.
- A manual `@coderabbitai review` request was accepted on PR #12 while the head was `657b73b`, but CodeRabbit remains pending and has returned no completed findings. Do not trigger a duplicate while this request is unresolved. Kilo review cannot run because the account has no credits.
- Keep approval, rehearsal, and protected-referee boundaries unchanged; this follow-up is limited to action/plugin import identity during generation reload.

## Reproduced manual finding

The force-reload path removed `actions.<leaf>` or `plugins.<leaf>` from `sys.modules` but did not remove the old child-module attribute from the parent package. A qualified import could consequently resolve the stale generation even though the registry used a fresh module. A second related issue could occur when one candidate leaf imported a sibling: the later file scan re-executed that sibling and replaced `sys.modules` with a new object while the importer retained the first object. That split a single candidate generation across module identities.

## Follow-up implementation and verification

- Detach leaf attributes from parent packages when clearing or replacing a generation; reattach modules when loading and restoring a generation.
- Reuse modules imported as dependencies within the freshly cleared candidate, so the registry and sibling importers keep one candidate module identity.
- Added regression tests for stale parent attributes and sibling-generation identity.
- Focused leaf-generation and self-change tests: **51 passed**; `compileall` passed; `git diff --check` passed.
- A full `unittest discover` run under the bare system interpreter was not a meaningful clean suite run: 1,277 tests executed, 13 skipped, 25 setup/import errors caused by missing environment dependencies (NumPy, psutil, requests, Playwright, plus other environment-only setup). Do not replace the prior configured broad-run result with this incomplete run.
- README discovered-test count updated to 1,731 to include the two added regressions.

## Next steps

1. Check the current branch head and CI after the follow-up push; do not assume the earlier green run covers this fix.
2. Check whether the accepted CodeRabbit invocation has completed. If it has, read the actual review comments and report them separately from the manual finding above. If it is still pending, state that explicitly; do not label it a CodeRabbit finding.
3. Preserve the open PR dependencies and candidate branches. `ArenaAi` remains needed while PR #8 or #12 depends on it.
