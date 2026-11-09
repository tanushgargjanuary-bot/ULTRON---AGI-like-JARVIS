# ULTRON — “Maybe complete?” checkpoint

**Checkpoint:** Branch consolidation candidate  
**Promotion PR:** [#14 — Consolidate reviewed branches and archive development refs](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/pull/14)  
**Target:** `main`  
**State:** Not merged. The owner must review and merge PR #14 after the final checks pass.

This checkpoint means the current consolidation work is ready for a final promotion decision. It does **not** mean every planned ULTRON capability is complete, every hardware path has been tested, or the product is defect-free.

## What is included

- Curated integration from the reviewed development branches. No wholesale branch merge.
- Lazy provider import fix for the default Gemini path.
- Memory search over saved session summaries.
- Stale self-change proposal protection: apply and revert compare content hashes before overwriting.
- Windows NTFS alternate-data-stream path rejection.
- MCP client with recursive bounded input-schema conversion, collision rejection across MCP servers and native tools, and guarded unknown-tool policy.
- Local fallback restricted to explicit consent, quantized 1.5B–3B chat models, loopback-only HTTP, no redirects, and bounded JSON responses.
- Non-streaming Ollama warm-up response so the code receives one JSON object.
- Loopback-only dashboard by default; LAN exposure requires an explicit setting and HTTPS.
- Public web reader with URL, DNS, redirect, robots, content-type, and response-size checks.
- Reviewdog + Ruff advisory PR checks.
- Branch archive tags and a guarded post-merge cleanup workflow.

## Verification evidence

The current PR head must have all of the following before merge:

- Linux `verify` job: success.
- Windows `verify` job: success.
- Reviewdog job: completed. Reviewdog warnings are advisory; review them rather than treating a successful job as proof of clean code.
- Proof-gate reports from both operating systems: inspect the PROVEN, PARTIAL, and FAILED counts and the claim-level output.
- No unresolved Critical or High findings. Medium findings must be fixed or explicitly deferred with a reason.

The CI result must belong to the **latest PR head**, not an earlier commit. See the checks and artifacts attached to PR #14. Older green runs do not verify later edits.

## Code-review status

A risk-focused review inspected the main security and integration paths and the full PR file inventory. It was not a line-by-line review of all changed lines across all 177 files.

Two Medium MCP defects were found and fixed:

1. Nested MCP object and array schemas were being flattened. The converter now preserves supported nested properties and rejects malformed or over-deep schemas.
2. Distinct MCP names could normalize to the same tool name and silently overwrite one another. Registration now rejects collisions, including collisions with native action/plugin names.

Other targeted fixes include stale self-change protection, the planner callback binding, local-fallback URL/body limits, and the Ollama warm-up stream setting. Regression tests were added.

Reviewdog reports static-analysis warnings. Several are expected patterns or false positives, for example fail-closed exception handling, explicit local subprocess launches, loopback probes, and avatar animation randomness. Each warning still requires context. Do not bulk-apply lint fixes or suppress the entire security ruleset.

## Known limits — not complete

### Provider routing

The routing library supports route selection, quota groups, and privacy/cost restrictions. The live application wires primary conversation/evolution/critic routes and explicit conversation switching. It does **not** yet configure a general live fallback ladder or quota-limit handling in the application request path.

Do not advertise automatic multi-provider failover as complete. Do not add paid or data-sharing fallback without a separate user-controlled setting and tests. The local fallback is a separate, explicit-consent path.

### Self-modification and health repair

A rehearsal runs in a temporary copy, but this is **not an OS security sandbox**. The Python subprocess runs with the same operating-system permissions as ULTRON. Candidate code can access files and network resources that the current user can access.

The tool has path restrictions, protected files, a guarded action, two apply confirmations, and stale-file checks. Those controls do not contain hostile code during rehearsal. Only rehearse code from a trusted source. A real restricted worker or VM is still required before treating self-repair as safe against adversarial code.

### MCP process trust

The app starts the commands listed in `config/mcp_servers.json`. Each process runs with the current user's permissions and inherits ULTRON's process environment, which may contain credentials. The shared tool-policy gate asks before an unknown MCP tool is invoked, but it does not sandbox the MCP server process itself or restrict its environment.

Only configure MCP commands and arguments from servers you trust. Do not configure untrusted MCP servers in a process that holds credentials in environment variables.

### Updates

The signed release verifier is a utility, not a complete release system. There is no production keyring, release publisher, downloader, A/B installation, or supervisor/worker handoff wired into the application. The current updater is not a safe unattended core-update pipeline. Keep unattended code updates disabled.

### Hardware and platform behaviour

GitHub Actions tests the configured Linux and Windows suite. It cannot prove that every microphone, camera, GPU, accessibility tree, driver, browser, or user's local application works on their machine. Read the platform proof-gate output. A PARTIAL claim is not a passed claim.

### AI review

Reviewdog + Ruff is deterministic static analysis, not semantic review. PR-Agent is optional and is not installed or run by GitHub Actions in this repository. The documented local Ollama route requires a local model and a GitHub token. The manual review in this checkpoint is AI-assisted and risk-focused; it is not a substitute for an independent human review.

## Branch cleanup

The original development branches remain present until PR #14 merges. The post-merge workflow first creates and verifies archive tags at the reviewed branch tips. It then deletes only the named temporary branches if their SHAs still match the reviewed values. A moved branch stops cleanup. `main` is not in the deletion list.

After merge, verify the archive workflow run and the branch list. Do not assume cleanup happened merely because PR #14 merged.

## Promotion checklist

- [ ] Latest Linux verification passes.
- [ ] Latest Windows verification passes.
- [ ] Latest Reviewdog run completes and the remaining warnings have been triaged.
- [ ] Latest Linux and Windows proof-gate reports have been inspected.
- [ ] No unresolved Critical or High review findings remain.
- [ ] Medium findings are fixed or explicitly deferred.
- [ ] The owner has reviewed PR #14 and approves the change to `main`.
- [ ] After merge, the archive workflow succeeds and the branch list is checked.

## Meaning of this checkpoint

When the checklist is complete, ULTRON is at a **curated, tested consolidation checkpoint**. That is a reasonable “maybe complete?” milestone for this release. It is not a claim that every planned capability, security boundary, update mechanism, or autonomous behaviour is finished.
