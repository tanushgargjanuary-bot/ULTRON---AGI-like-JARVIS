# Branch archive and cleanup

**Review date:** 2026-11-10  
**Target end state:** `main` is the only permanent branch. Historical tips remain recoverable through exact-SHA archive tags protected by a GitHub ruleset.

## Current repository state

**Promoted application commit:** `bd4b43d16fdf27b495209678ed72b41f21408d7c`  
**Main head at the start of the documentation audit:** `a7be7daed4aa8457d138299a4e527ea131f9979e`.  
**Promotion:** The curated candidate was pushed to `main` with a non-forced fast-forward update and an expected old-SHA lease. PR #15 closed after its head became reachable from `main`. No merge commit was created.

**Initial ten-branch archive cleanup:** [run 42779866199](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42779866199) completed successfully.

### Historical cleanup verification — 2026-11-10 (initial ten branches)

- Branches: **1** — `main` only.
- Historical recovery tags: **10**, all expected full commit SHAs verified.
- Obsolete branch refs deleted: **10**.
- Open pull requests: **0**.
- Default branch: **main**.
- Curated candidate ancestry: `main` contained the promoted candidate at `bd4b43d16fdf27b495209678ed72b41f21408d7c`.
- Archive ruleset: **Active**, ID `26923169`.
- The ruleset targets `refs/tags/archive/**/*`, blocks updates and deletions, allows tag creation, and has no bypass actors.

The live post-cleanup audit confirmed that every reviewed historical commit remains reachable through its protected archive tag.
### Current follow-up state — 2026-11-10

- Main baseline at this review: `4934d605fb1f3dbc332393191af083022162214b`.
- PR #17 and PR #18 are merged. PR #18 merged as `eeacaf2ae2224edd91074a3853ae0ecff47c41a7`.
- Current refs: **three branches** (`main` and two merged temporary refs); **zero open PRs**.
- Verified archive tags: **12**, protected by Active ruleset `26923169`.
- Archive run [42830329517](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42830329517) archived and read back both new tips: `docs/repository-doc-audit-2026-11-10` at `9074b986c9379ff2b2f320916616763a735df972` and `ci/fast-branch-gate` at `e0072889ca333f5b8193f7d85b4ef912bf4aa10d`.
- The two branch refs remain present. Delete them only through the guarded manual workflow after archive tags exist and no PR uses them.

## Reviewed branch tips

| Branch | Exact reviewed tip | Treatment |
|---|---|---|
| `main` | `44ec6dbde86746a5a2ff1ff201ed646e54068cb9` at audit time | Keep; never delete |
| `docs/repository-doc-audit-2026-11-10` | `9074b986c9379ff2b2f320916616763a735df972` | PR #17 merged; exact tip archived; branch ref pending guarded deletion |
| `ci/fast-branch-gate` | `e0072889ca333f5b8193f7d85b4ef912bf4aa10d` | PR #18 merged; exact tip archived; branch ref pending guarded deletion |
| `ArenaAi` | `8f4803b8812e4cae1e79755381eda69f5b76ee81` | Deleted; exact tip retained by protected archive tag |
| `antigravity` | `b8e9334484bb214fd1f18021eade35c62ba5329b` | Deleted; exact tip retained by protected archive tag |
| `arena/4c973188-ultron-agi-like-jarvis` | `8b20ceff3421add70b65cc4eacca1dac1f3b5b36` | Deleted; exact tip retained by protected archive tag |
| `chatgpt` | `c98ea0ff81a440ba4b2f56b1aef0f726384f521d` | Deleted; exact tip retained by protected archive tag |
| `code-quality-and-security-improvements-af08a` | `bc65a2746d5a75232ff3ecb9a7ac6b57b87f8420` | Deleted; exact tip retained by protected archive tag |
| `feature/web-companion-mvp` | `309529147821728554896f84141333dd9fb512e8` | Older duplicate web scaffold; deleted; exact tip retained by protected archive tag |
| `feature/web-mvp-auth` | `a862f7650ddc36ac04d1178884d6802e2b3cb4c1` | Web source; PR #16 closed without merge; deleted; exact tip retained by protected archive tag |
| `integration/best-of-all-2026-11-09` | `5118dede0ca4c29206a24a08ec9f9ae6699011f5` | Ancestor of consolidation; deleted; exact tip retained by protected archive tag |
| `ultron/consolidation-2026-11` | `e058f26d4eff7f54ba896a3b8c307f5bc1e0aa7a` | Superseded consolidation; deleted; exact tip retained by protected archive tag |
| `ultron/curated-promotion-2026-11` | `bd4b43d16fdf27b495209678ed72b41f21408d7c` | Deleted after promotion; exact tip retained by protected archive tag |

These values were refreshed from GitHub immediately before the cleanup workflow was prepared. The workflow refuses to archive or delete a source branch if its current SHA differs from the reviewed SHA. The curated candidate is captured dynamically, but only after GitHub confirms that the exact current candidate SHA is already reachable from `main`.

## How the guarded cleanup works

Workflow: `.github/workflows/archive-reviewed-branches.yml`. A push to `main` runs archive-only mode automatically. Manual dispatch is reserved for the separate deletion operation.

1. It runs manually on `main` only.
2. It confirms that `main` contains the reviewed curated candidate. While the candidate branch exists, it reads that branch. After deletion, it reads the protected candidate archive tag and checks its exact reviewed SHA.
3. It reads workflow dispatch fields from the event payload.
4. It checks all reviewed branches against exact SHAs before creating tags.
5. It creates and verifies every reviewed exact-SHA tag. The current reviewed set has twelve tags: ten from the initial cleanup and two later merged PR tips.
6. The default mode is archive-only and deletes nothing.
7. The required Active archive ruleset is repository ruleset `26923169`. The workflow verifies its live definition on every deletion run. Keep enforcement Active, block updates and deletions, allow tag creation, and add no bypass actors.
8. Deletion requires `delete_branches=true`, `confirm_delete=DELETE ARCHIVED BRANCHES`, and `confirm_archive_tags=ARCHIVE TAGS PROTECTED`.
9. The last phrase is an additional owner confirmation, not proof of protection. Before it reads or changes refs in deletion mode, the workflow queries repository tag rulesets and fetches their full definitions.
10. It requires an **Active** tag ruleset that includes `refs/tags/archive/**/*`, has no exclusions, blocks updates and deletions, does not block tag creation, and has no bypass actors. Otherwise it stops before deletion.
11. Branches used by open PRs are skipped. The workflow rechecks the PR list before deletion.
12. It rechecks the branch SHA and archive tag target immediately before deleting the branch.
13. `main` is never in the deletion list.

The Active repository ruleset `26923169` currently protects `refs/tags/archive/**/*` against updates and deletions. No bypass actors are configured. Keep this rule Active and do not delete the ten recovery tags. The workflow stops if the live ruleset is removed or its required settings change.

GitHub's ref API does not provide an atomic compare-and-delete operation. The workflow performs an immediate SHA recheck before each deletion. Do not push to reviewed branches while cleanup is running.

## Safe operating sequence

### Completed

1. Fast-forwarded `main` to the reviewed candidate without a merge commit.
2. Created and verified ten exact-SHA recovery tags.
3. Created Active archive ruleset `26923169`, with update/deletion restrictions, tag creation allowed, and no bypass actors.
4. Dispatched the guarded deletion workflow from `main`. It checked the live ruleset and rechecked reviewed refs, tag targets, and open PRs.
5. Workflow run [42779866199](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42779866199) completed successfully.
6. Re-read GitHub refs: only `main` remains; all ten recovery tags remain; zero open PRs.

**Two branch refs still need deletion.** Use the GitHub Actions UI: open `Archive reviewed branch tips`, select branch `main`, and run with `delete_branches=true`, `confirm_delete=DELETE ARCHIVED BRANCHES`, and `confirm_archive_tags=ARCHIVE TAGS PROTECTED`. The workflow checks the live ruleset, exact branch/tag SHA matches, and open PRs before deleting. It skips already absent branches, retains moved refs, and never deletes `main`. Re-read the branch list after the run.

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
