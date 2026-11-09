# Branch archive and cleanup

**Review date:** 2026-11-09  
**Target end state:** `main` is the only permanent branch. Historical branch tips remain recoverable through immutable Git tags.

## Why this cleanup exists

The repository accumulated branches for separate agent sessions and competing implementations. That makes it hard to tell which code is current. It also makes CI branch filters stale.

The consolidation pull request is the only candidate for promotion. It uses the integration snapshot as its base, then applies selected fixes and regression tests. It does not merge every branch wholesale.

## Reviewed branch tips

The archive workflow creates and verifies a tag for each exact reviewed branch tip. It runs only after a manual workflow dispatch on `main` and only after PR #14 is merged. It preserves every branch ref. If a source branch moved after this review, the workflow stops before it creates any tags.

| Source branch | Reviewed tip | Archive tag |
|---|---|---|
| `ArenaAi` | `8f4803b8812e4cae1e79755381eda69f5b76ee81` | `archive/2026-11-09/ArenaAi-8f4803b8` |
| `antigravity` | `b8e9334484bb214fd1f18021eade35c62ba5329b` | `archive/2026-11-09/antigravity-b8e93344` |
| `arena/4c973188-ultron-agi-like-jarvis` | `8b20ceff3421add70b65cc4eacca1dac1f3b5b36` | `archive/2026-11-09/arena-4c973188-ultron-agi-like-jarvis-8b20ceff` |
| `chatgpt` | `c98ea0ff81a440ba4b2f56b1aef0f726384f521d` | `archive/2026-11-09/chatgpt-c98ea0ff` |
| `code-quality-and-security-improvements-af08a` | `bc65a2746d5a75232ff3ecb9a7ac6b57b87f8420` | `archive/2026-11-09/code-quality-and-security-improvements-af08a-bc65a274` |
| `integration/best-of-all-2026-11-09` | `5118dede0ca4c29206a24a08ec9f9ae6699011f5` | `archive/2026-11-09/integration-best-of-all-2026-11-09-5118dede` |
| `ultron/consolidation-2026-11` | The head SHA of merged PR #14, read at cleanup time | `archive/2026-11-09/ultron-consolidation-<head-sha>` |

## What was carried forward

- **ArenaAi and arena:** both are ancestors of the integration snapshot. Their commits are already in the consolidation history.
- **integration:** used as the base. Its capability guide, read-only GitHub scout, guarded MCP bridge, plan checkpoints, health center, web reader, bounded fuzzy matching, crash redaction, and other reviewed work remain in the candidate tree.
- **chatgpt:** the capability guide and repository scout are retained in the integration line. The local-model inventory was carried as a read-only status tool. Its probe is loopback-only, rejects redirects, and bounds the response. The provider-configuration action was not carried.
- **antigravity:** saved-session recall was adapted into `memory/memory_manager.py`; its skill files, metacognition work, and bandit implementation were already present in the integration line. The file controller now also rejects Windows NTFS alternate data stream names. The branch's incompatible undo metadata API was not copied.
- **code-quality branch:** it contains tests and a README, not a distinct implementation fix. The useful bounded fuzzy-distance and TLS/redaction ideas were implemented with tests in the integration line. Its live-network test and stale documentation were not copied.

## Deliberately not promoted

The following items remain excluded until their design defects are fixed and their use is justified:

- Plugin Forge: generated code ran with the current user's privileges, and model-supplied policy tiers could lower approval requirements.
- Crawler bridge: the fallback URL fetch lacked equivalent SSRF and response-size protections.
- OCR bridge: no active production call site was found; file-path and size controls need work.
- Context detector: clipboard access had no clear consent gate.
- Intent router: keyword routing had no verified production caller.
- Agent monitor bridge: thread introspection and an external localhost dashboard probe add an optional observability surface without a demonstrated requirement.
- The broad semantic-undo implementation: it depended on a different undo-stack metadata API and needs a separate, compatible change with tests.

Rejected code was reviewed, not silently discarded from the audit.

## Restore a branch tip

After the archive tags exist, restore any old branch from its tag:

```bash
git fetch origin --tags
git switch -c antigravity archive/2026-11-09/antigravity-b8e93344
```

Replace the branch and tag with the row you need. The tag points to the exact reviewed commit, not to a later or rewritten version.

## Branch policy after cleanup

- Keep `main` as the stable branch.
- Use short-lived `feature/<topic>` and `fix/<topic>` branches for work.
- Open a pull request to `main`; do not use permanent branches per agent or coding model.
- CI runs on every pushed branch and every pull request.
- Archive reviewed branch tips with the manual workflow. Delete a temporary branch only as a separate manual owner action.
- Never delete a branch if its current SHA differs from the reviewed SHA. Re-review it first.

The workflow `.github/workflows/archive-reviewed-branches.yml` performs a guarded, manual archive operation after PR #14 merges into `main`. It creates and verifies the seven tags. It never deletes a branch. Branch deletion is a separate manual owner decision after the archived tags have been checked.
