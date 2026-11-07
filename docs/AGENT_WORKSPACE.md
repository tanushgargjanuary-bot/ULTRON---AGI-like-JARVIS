# Agent workspace awareness

This guide and `scripts/agent_workspace.py` help an agent establish what changed in its current checkout before it plans or edits. They do not authorize a feature, replace the project rules, fetch from the network, or promise that a change is safe.

## Start each task

1. Read `WORKING-PHILOSOPHY.md`, `AGENTS.md`, `DECISIONS.md`, `ARCHITECTURE.md`, and `GATEKEEPERS.md`. Read `docs/AGENT_PLAYBOOK.md` and `docs/BRANCH_REVIEW.md` when relevant.
2. In PowerShell, update remote-tracking refs only if appropriate: `git fetch origin main`. The report script is deliberately read-only unless `--ack` is supplied.
3. Run `python scripts/agent_workspace.py` from any folder in the repository. Set the comparison base when needed: `python scripts/agent_workspace.py --base origin/main`.
4. Review the report's **new commits**, **changed paths**, **incoming base changes**, and **uncommitted work**. Read the actual diffs and source/tests for relevant paths; the summary is a map, not a substitute for review.
5. Before starting a new task, make a short plan: user goal, current behavior, relevant changed files, safety/decision constraints, tests and acceptance evidence. If there are unrelated or uncommitted changes, preserve them; never overwrite another agent's work.
6. After you have actually reviewed the reported commits, optionally run `python scripts/agent_workspace.py --ack` to record the current commit as reviewed in this local Git worktree's metadata. Do not acknowledge changes you have not read. This state is local and is not committed or shared with other agents.

## What the report means

- **Since last acknowledgement**: commits added to the current branch after this worktree's last explicit `--ack`. On first run, all reachable commits on the current branch are shown (bounded to the newest 30).
- **Branch changes vs base**: committed changes unique to the current branch, compared with the merge base of the selected base and `HEAD`.
- **Base changes not in branch**: commits on the base that are not in the current branch. These may be updates to integrate; do not merge automatically.
- **Working tree**: tracked or untracked local changes. These are never included in the committed branch diff unless separately staged/committed.
- **Patch view**: `--patch` prints a bounded diff for branch-specific committed changes. Use `--max-lines N` to adjust the cap (maximum 2,000 lines). Open individual files for complete context.

The script does **not** run `git fetch`, change branches, merge, edit source, run tests, or stage/commit files. If the selected base is not available locally, fetch it yourself or pass a valid local ref. The report is only as current as the local refs.

## Next-step planning rule

Use the report to decide what to inspect next, not to let an agent invent scope. Preserve owner decisions and feature-freeze rules. Prefer the smallest defect fix or approved task that has a reproducible failure and a deterministic test. For each change, state the expected behavior and verification command before editing; after editing, run the focused test and repository gates required by `WORKING-PHILOSOPHY.md`. Report exactly what was tested and what remains unverified.

No tool can guarantee a bug-free system. Claims must stay within the evidence actually collected.
