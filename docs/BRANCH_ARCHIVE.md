# Branch archive and cleanup

**Review date:** 2026-11-10  
**Target end state:** `main` is the only permanent branch. Historical tips remain recoverable through exact-SHA archive tags protected by a GitHub ruleset.

## Current repository state

**Promoted application commit:** `bd4b43d16fdf27b495209678ed72b41f21408d7c`  
**`main` head before this documentation follow-up:** `516b772db218ff2afc934ba943b9204a9abb2eb7` (workflow safety hardening).  
**Promotion:** The curated candidate was pushed to `main` with a non-forced fast-forward update and an expected old-SHA lease. PR #15 closed after its head became reachable from `main`. No merge commit was created.

**Archive run:** [42760721739](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42760721739) completed successfully.

### Live pre-deletion audit — 2026-11-10

- Branches: **11** (`main` plus ten reviewed source/staging branches).
- Recovery tags: **10**.
- Branch-to-tag SHA checks: **10/10 match**.
- Open pull requests: **0**.
- Default branch: **main**.
- Curated candidate ancestry: `main` is 8 commits ahead and 0 behind the candidate; the candidate tip is contained in `main`.
- Branches deleted: **0**.
- Repository tag rulesets: **0**.

The ten exact matching tags preserve these branch tips: `ArenaAi`, `antigravity`, `arena/4c973188-ultron-agi-like-jarvis`, `chatgpt`, `code-quality-and-security-improvements-af08a`, `feature/web-companion-mvp`, `feature/web-mvp-auth`, `integration/best-of-all-2026-11-09`, `ultron/consolidation-2026-11`, and `ultron/curated-promotion-2026-11`.

PR #16 remains closed without merging. Its final web-app tree is included in the promoted candidate. Its source branch tip remains recoverable from its exact-SHA tag.

**Deletion is not approved by this audit.** The archive tags are not protected because no tag ruleset exists. Do not delete branch refs until an Active ruleset protects `archive/**/*` against updates and deletions. The manual workflow's confirmation phrase is an owner attestation; the workflow itself does not verify that the ruleset exists.


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

Workflow: `.github/workflows/archive-reviewed-branches.yml`. A push to `main` runs archive-only mode automatically. Manual dispatch is reserved for the separate deletion operation.

1. It runs manually on `main` only.
2. It confirms that `main` contains the current curated candidate.
3. It reads workflow dispatch fields from the event payload.
4. It checks all reviewed branches against exact SHAs before creating tags.
5. It creates and verifies ten deterministic exact-SHA tags.
6. The default mode is archive-only and deletes nothing.
7. Before deletion, the owner must enable a GitHub tag ruleset targeting tag names matching `archive/**/*`. Set enforcement to **Active**. Enable **Restrict updates** and **Restrict deletions**. Leave **Restrict creations** off so the workflow can create archive tags. Do not add bypass actors.
8. Deletion requires `delete_branches=true`, `confirm_delete=DELETE ARCHIVED BRANCHES`, and `confirm_archive_tags=ARCHIVE TAGS PROTECTED`.
9. The last phrase is an additional owner confirmation, not proof of protection. Before it reads or changes refs in deletion mode, the workflow queries repository tag rulesets and fetches their full definitions.
10. It requires an **Active** tag ruleset that includes `refs/tags/archive/**/*`, has no exclusions, blocks updates and deletions, does not block tag creation, and has no bypass actors. Otherwise it stops before deletion.
11. Branches used by open PRs are skipped. The workflow rechecks the PR list before deletion.
12. It rechecks the branch SHA and archive tag target immediately before deleting the branch.
13. `main` is never in the deletion list.

Git tags are not immutable by default. They can be moved or deleted until the owner protects `archive/**/*` with a ruleset. Do not enable branch deletion before that ruleset is active.

GitHub's ref API does not provide an atomic compare-and-delete operation. The workflow performs an immediate SHA recheck before each deletion. Do not push to reviewed branches while cleanup is running.

## Safe operating sequence

### Completed

1. Fast-forward `main` to the exact reviewed candidate SHA. No native merge or merge commit.
2. PR #15 closed automatically after its head became part of `main`.
3. The push to `main` triggered archive-only mode.
4. Workflow run `42760721739` created and verified all ten exact-SHA recovery tags.

### Remaining

1. In Settings → Rules → Rulesets, create an Active tag ruleset for `archive/**/*`.
2. Enable **Restrict updates** and **Restrict deletions**. Leave **Restrict creations** off. Add no bypass actors.
3. In Actions → Archive reviewed branch tips, select `main` and run with `delete_branches=true`.
4. Enter `DELETE ARCHIVED BRANCHES` and `ARCHIVE TAGS PROTECTED`.
5. Inspect the summary. It must preserve `main`, retain all ten tags, and delete only eligible non-`main` refs.

The repository currently has no tag ruleset. The workflow now checks the live ruleset configuration itself and fails closed if the protection is absent or incomplete. Do not run deletion until the owner creates and verifies the rule. Git tags are mutable until protected.


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
