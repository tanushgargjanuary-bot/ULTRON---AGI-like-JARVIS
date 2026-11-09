# Branch archive and cleanup

**Review date:** 2026-11-10  
**Target end state:** `main` is the only permanent branch. Historical tips remain recoverable through exact-SHA archive tags.

## Current repository state

The review found 11 branches: `main` plus 10 development or staging branches. The active release candidate is `ultron/curated-promotion-2026-11`. PR #15 uses that branch and must remain open for review until the owner fast-forwards `main` to the reviewed candidate and closes the PR without a native merge.

PR #16 was closed without merging. Its final Git tree was confirmed byte-for-byte identical to the web-app tree copied into the curated candidate. Its branch remains available for recovery.

## Reviewed branch tips

| Branch | Exact reviewed tip | Treatment |
|---|---|---|
| `main` | `44ec6dbde86746a5a2ff1ff201ed646e54068cb9` at audit time | Keep; never delete |
| `ArenaAi` | `8f4803b8812e4cae1e79755381eda69f5b76ee81` | Archive, then eligible for deletion |
| `antigravity` | `b8e9334484bb214fd1f18021eade35c62ba5329b` | Archive, then eligible for deletion |
| `arena/4c973188-ultron-agi-like-jarvis` | `8b20ceff3421add70b65cc4eacca1dac1f3b5b36` | Archive, then eligible for deletion |
| `chatgpt` | `c98ea0ff81a440ba4b2f56b1aef0f726384f521d` | Archive, then eligible for deletion |
| `code-quality-and-security-improvements-af08a` | `bc65a2746d5a75232ff3ecb9a7ac6b57b87f8420` | Archive, then eligible for deletion |
| `feature/web-companion-mvp` | `309529147821728554896f84141333dd9fb512e8` | Older duplicate web scaffold; archive, then eligible for deletion |
| `feature/web-mvp-auth` | `a862f7650ddc36ac04d1178884d6802e2b3cb4c1` | Web source; PR #16 closed without merge; archive, then eligible for deletion |
| `integration/best-of-all-2026-11-09` | `5118dede0ca4c29206a24a08ec9f9ae6699011f5` | Ancestor of consolidation; archive, then eligible for deletion |
| `ultron/consolidation-2026-11` | `e058f26d4eff7f54ba896a3b8c307f5bc1e0aa7a` | Superseded consolidation; archive, then eligible for deletion |
| `ultron/curated-promotion-2026-11` | Current branch tip is captured by the workflow at run time | Keep until main contains it and PR #15 is closed; then eligible for deletion |

These values were refreshed from GitHub immediately before the cleanup workflow was prepared. The workflow refuses to archive or delete a source branch if its current SHA differs from the reviewed SHA. The curated candidate is captured dynamically, but only after GitHub confirms that the exact current candidate SHA is already reachable from `main`.

## How the guarded cleanup works

Workflow: `.github/workflows/archive-reviewed-branches.yml`.

1. It runs manually on `main` only.
2. It first confirms that `main` contains the current curated-promotion branch tip.
3. It checks every reviewed source branch against its expected SHA. A moved branch stops the workflow before any archive tags are created.
4. It creates a deterministic `archive/2026-11-10/<branch>-<sha>` tag for every reviewed tip and verifies each tag.
5. The default run is **archive only**. It does not delete branches.
6. Deletion requires `delete_branches=true` and the exact confirmation phrase `DELETE ARCHIVED BRANCHES`.
7. Branches used by open PRs are skipped. The workflow checks this before each deletion.
8. It rechecks the branch SHA and archive tag immediately before deleting the branch ref.
9. `main` is never in the deletion list.

GitHub's ref API does not provide an atomic compare-and-delete operation. The workflow performs an immediate SHA recheck before each deletion, and exact recovery tags are created first. Do not push to reviewed branches while cleanup is running.

## Safe operating sequence

1. Finish PR #15 review.
2. Fast-forward `main` to the exact approved candidate SHA. Do not use GitHub's merge button and do not create a merge commit.
3. Close PR #15 after the fast-forward. It is not a native merge.
4. Manually run `Archive reviewed branch tips` from `main` with the default `delete_branches=false`.
5. Inspect the workflow summary and verify all ten archive tags.
6. Run it again with `delete_branches=true` and `confirm_delete=DELETE ARCHIVED BRANCHES`.
7. Verify the report. Any branch with an open PR, changed SHA, or tag mismatch is preserved.

## Restore a branch tip

```bash
git fetch origin --tags
git switch -c antigravity archive/2026-11-10/antigravity-b8e93344
```

Use the matching branch name and archive tag from the Actions summary. The tag points to the exact reviewed commit.

## What was carried forward

- **ArenaAi and arena:** their commits are already in the integration/consolidation history.
- **integration:** used as the curated base. Its capability guide, read-only GitHub scout, guarded MCP bridge, plan checkpoints, health center, web reader, bounded fuzzy matching and other reviewed work remain in the candidate.
- **chatgpt:** the capability guide and repository scout are retained. The local-model inventory was carried as a read-only status tool. The provider-configuration action was not carried.
- **antigravity:** saved-session recall was adapted into memory search; skill files and metacognition work were already present. Fractional evidence weights, system-voice TTS fallback and NTFS alternate-data-stream path rejection were adapted with tests.
- **code-quality branch:** no distinct implementation fix was found. Useful fuzzy-distance and TLS/redaction ideas were implemented in the integration line. Its live-network test and stale README were not copied.
- **web branches:** PR #16's final tree was integrated into the curated branch in one commit (`29038b14305c6d0140a3c017ccf3e54dba30ce5e`). The candidate's web tree SHA was verified equal to the PR #16 tree. The earlier `feature/web-companion-mvp` branch is an older snapshot.

## Deliberately not promoted

- Plugin Forge: generated code ran with current-user privileges and model-supplied policy tiers could lower approval requirements.
- Crawler bridge: the fallback URL fetch lacked equivalent SSRF and response-size protections.
- OCR bridge: no active production call site was found; file-path and size controls need work.
- Context detector: clipboard access had no clear consent gate.
- Intent router: keyword routing had no verified production caller.
- Agent monitor bridge: thread introspection and an external localhost dashboard probe add an optional observability surface without a demonstrated requirement.
- Broad semantic undo: it depended on a different undo-stack metadata API and needs a separate compatible change with tests.

Rejected code was reviewed, not silently discarded from the audit.

## Branch policy after cleanup

- Keep `main` as the only permanent branch after promotion and cleanup.
- Use short-lived `feature/<topic>` and `fix/<topic>` branches for future work.
- Open PRs to `main`; do not keep permanent branches per agent or coding model.
- Archive reviewed tips before branch deletion. Never delete `main`.
- If a source branch moves, re-review it. Do not force it back to an earlier SHA.
