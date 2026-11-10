# ULTRON — “Maybe complete?” checkpoint

**Checkpoint:** Curated consolidation candidate  
**Promotion review:** [#15 — Curated ULTRON promotion candidate — fast-forward only](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/pull/15)  
**Candidate branch:** `ultron/curated-promotion-2026-11`  
**Promoted commit on `main`:** `bd4b43d16fdf27b495209678ed72b41f21408d7c`  
**Target:** `main`  
**State:** Promoted to `main` by direct non-forced fast-forward. PR #15 is closed; GitHub reports it as merged because its head became reachable from `main`. No merge commit was created.

This checkpoint means the curated implementation has passed its current automated verification and is ready for the owner to review for promotion. It does **not** mean every planned ULTRON capability is complete, every hardware path has been tested, or the product is defect-free.

## What is included

- Curated integration from reviewed development branches. No wholesale branch merge.
- Lazy provider import fix for the default Gemini path.
- Memory search over saved session summaries.
- Stale self-change proposal protection: apply and revert compare content hashes before overwriting. State updates use unique exclusive temporary files and recheck hashes immediately before atomic replacement.
- Windows NTFS alternate-data-stream path rejection.
- MCP client with recursive bounded input schemas, strict rejection of unsupported schema shapes, collision rejection across MCP/native tools, guarded unknown-tool policy, 1 MB JSON-RPC line limits, and bounded stderr diagnostics.
- Local fallback restricted to explicit consent, quantized 1.5B–3B chat models, loopback-only HTTP, no redirects, and bounded JSON responses.
- Non-streaming Ollama warm-up response so the code receives one JSON object.
- Weighted bandit evidence for decayed strategy history, with tests for fractional UCB1 and Thompson updates.
- System-voice TTS fallback when the primary speech engine fails, with fallback and lifecycle tests.
- Loopback-only dashboard by default; LAN exposure requires an explicit setting and HTTPS.
- Public web reader with URL, DNS, redirect, robots, content-type, and response-size checks.
- Reviewdog + Ruff advisory PR checks.
- **ULTRON Web first slice:** Next.js web client, Supabase Google OAuth, cookie-based sessions, protected workspace, sign-out, and a disabled composer until the Python agent service is connected. This is a separate web client, not a replacement for the Windows desktop app.
- Web CI workflow for TypeScript checking and production build.
- Guarded manual branch archive workflow. It records ten non-`main` branch tips, creates and verifies exact-SHA tags after promotion, skips branches used by open PRs, and only deletes when an explicit manual input and confirmation phrase are supplied.

## Verification evidence

Post-promotion verification for the application commit `bd4b43d16fdf27b495209678ed72b41f21408d7c` completed successfully. Linux and Windows suites passed in run `42699779342`; the Web type-check and production build passed in run `42699779160`; Reviewdog/Ruff completed successfully in run `42699779015`. The archive-only workflow completed successfully in run `42760721739`. These results were recorded in follow-up documentation commits on `main`.

| Check | Run | Result |
|---|---:|---|
| Linux `verify` suite and proof gate | [42699779342](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42699779342) | Passed |
| Windows `verify` suite and proof gate | [42699779342](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42699779342) | Passed |
| ULTRON Web typecheck and production build | [42699779160](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42699779160) | Passed |
| Reviewdog / Ruff | [42699779015](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42699779015) | Completed successfully; 101 advisory warnings triaged |

### Proof-gate results

| Runner | PROVEN | PARTIAL |
|---|---:|---:|
| Linux | 24 | 13 |
| Windows | 28 | 9 |

PARTIAL is not a pass. It records claims that the hosted runner cannot fully verify. The two reports are saved as workflow artifacts named `verification-linux` and `verification-windows`.

### Instrument-scan results

These scans are separate from the main suite and are configured as non-blocking environment reports.

| Runner | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Linux | 17 | 2 | 15 |
| Windows | 24 | 0 | 12 |

The Linux failures are environmental: screen capture cannot connect to a display, and PortAudio cannot connect to PulseAudio. Linux also skips camera capture because OpenCV is absent and browser checks because Playwright is absent.

The Windows scan has no audio devices. It skips camera/browser checks because OpenCV and Playwright are absent. These skipped hardware checks are not tested successfully; test them on the target machine before claiming those paths work.

### Reviewdog warning triage

Reviewdog reported 101 advisory warnings on changed lines:

| Rule | Count | Assessment |
|---|---:|---|
| BLE001 — broad exception catches | 50 | Needs targeted cleanup; many are fail-soft boundaries, but not all are automatically safe |
| E402 — imports after setup | 15 | Test modules often set environment or stubs before importing the target module |
| S603 — subprocess without shell | 6 | Calls use argument arrays and no shell; MCP commands are owner-configured and run with owner privileges |
| F401 — unused imports | 5 | Low-risk cleanup debt |
| S310 — URL opening | 4 | Audited guards use a fixed GitHub HTTPS endpoint or literal loopback addresses, disable proxies/redirects, and bound responses |
| S607 — partial executable paths | 4 | Local utilities are resolved or intentionally invoked by name; keep PATH trust in mind |
| S110 — exception/pass | 3 | File rollback attempts are best-effort; failures must not replace the original write error |
| S311 — pseudo-random values | 3 | Used for avatar/visual animation, not credentials or cryptographic tokens |
| S104 — bind to all interfaces | 2 | Dashboard binds to 0.0.0.0 only when the owner enables LAN access and HTTPS is enabled; the other warning is a test |
| Other style/reliability rules | 9 | Includes unused variables, test import order, test fixture secrets, and formatting |

The security-pattern warnings were inspected in context. No shell execution was found in the flagged subprocess calls. The GitHub scout uses a fixed HTTPS API URL; local model probes use literal loopback addresses, no proxy, no redirect, and bounded response bodies. The dashboard's LAN bind has an explicit owner setting and TLS guard. The hardcoded token warning is a fake test fixture.

This is a warning triage, not a full security audit. Do not bulk-suppress Ruff rules. Review remaining broad exception handling and unused imports in separate small tasks.

## Fast-forward status

`main` is now `bd4b43d16fdf27b495209678ed72b41f21408d7c`. Before promotion, the candidate was 173 commits ahead and 0 behind. The update used `force=false` with expected old SHA `44ec6dbde86746a5a2ff1ff201ed646e54068cb9`. The promoted commit's parent is the existing candidate commit `1205550828025d7505389043818fe584a92be5cf`. No merge commit was created.

PR #15 is closed. GitHub marks it as merged because the exact PR head is now contained in `main`; the branch update itself was a direct fast-forward.


## Code-review status

A risk-focused review inspected the main security and integration paths and the full PR file inventory. It was not a line-by-line review of all changed lines across all 180+ files.

Four security defects were found and fixed in the focused MCP/self-change review:

1. Nested MCP object and array schemas were being flattened. The converter preserves supported nested properties and rejects malformed, over-deep, or unsupported schemas rather than mapping them to a different type.
2. Distinct MCP names could normalize to the same tool name and silently overwrite one another. Registration now rejects collisions, including collisions with native action/plugin names.
3. MCP servers could emit oversized protocol lines. The reader now caps a line at 1 MB, kills a server that exceeds the limit, bounds stderr reads, and rejects oversized client messages.
4. A self-change path could reach a protected referee file through a symlink alias, or be redirected after approval by retargeting the link. The path guard now refuses symlink and junction paths, checks protected resolved targets, and stores canonical project-relative paths. Regression tests cover file links, directory links, and post-approval link replacement.

Other targeted fixes include stale self-change proposal protection, the planner callback binding, local-fallback URL/body limits, the Ollama warm-up stream setting, atomic self-change file replacement, and observable temporary-file cleanup. Regression tests were added.

## Known limits — not complete

### Provider routing

The routing library supports route selection, quota groups, and privacy/cost restrictions. The live application wires primary conversation/evolution/critic routes and explicit conversation switching. It does **not** yet configure a general live fallback ladder or quota-limit handling in the application request path.

Do not advertise automatic multi-provider failover as complete. Do not add paid or data-sharing fallback without a separate user-controlled setting and tests. The local fallback is a separate, explicit-consent path.

### ULTRON Web

The current web client is an authentication and workspace shell. It does not yet execute the ULTRON Python agent, store chat messages, or provide cross-device memory. Its composer remains disabled.

Before enabling chat:
- Host the Python worker as a separate service.
- Verify the Supabase session server-side for every request.
- Derive the account identity from verified claims; never trust a browser-supplied user ID.
- Add per-user database policies, retention, export, and deletion controls before storing messages.
- Keep provider keys server-side. A later BYOK feature must not expose keys to browser JavaScript.

No Vercel project has been confirmed or deployed yet. Team authorization is still required before project discovery and setup. Supabase and Google OAuth provider configuration is also required before sign-in can work.

Do not collect or sell raw user conversations, personal details, or user memories. Use explicit, minimal, opt-in analytics only.

### Self-modification and health repair

A rehearsal runs in a temporary copy, but this is **not an OS security sandbox**. The Python subprocess runs with the same operating-system permissions as ULTRON. Candidate code can access files and network resources that the current user can access.

The tool has path restrictions, protected files (including symlink aliases to resolved protected targets), a guarded action, two apply confirmations, and stale-file checks. Those controls do not contain hostile code during rehearsal. Only rehearse code from a trusted source. A real restricted worker or VM is still required before treating self-repair as safe against adversarial code.

### MCP process trust

The app starts the commands listed in `config/mcp_servers.json`. Each process runs with the current user's permissions and inherits the app's process environment, which may contain credentials. The shared tool-policy gate asks before an unknown MCP tool is invoked, but it does not sandbox the MCP server process itself or restrict its environment.

Only configure MCP commands and arguments from servers you trust. Do not configure untrusted MCP servers in a process that holds credentials in environment variables.

### Updates

The signed release verifier is a utility, not a complete release system. There is no production keyring, release publisher, downloader, A/B installation, or supervisor/worker handoff wired into the application. The current updater is not a safe unattended core-update pipeline. Keep unattended code updates disabled.

### Hardware and platform behaviour

GitHub Actions tests the configured Linux and Windows suite. It cannot prove that every microphone, camera, GPU, accessibility tree, driver, browser, or user's local application works on their machine. Read the platform proof-gate output. A PARTIAL claim is not a passed claim.

### AI review

Reviewdog + Ruff is deterministic static analysis, not semantic review. PR-Agent is optional and is not installed or run by GitHub Actions in this repository. The documented local Ollama route requires a local model and a GitHub token. The manual review in this checkpoint is AI-assisted and risk-focused; it is not a substitute for an independent human review.

## Branch cleanup

The repository currently has **11 branch refs**: `main` plus ten historical source/staging refs. The archive workflow ran successfully and created **10 exact-SHA tags**:

[Archive workflow run 42760721739](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42760721739).

All ten tags were read back from GitHub and matched their reviewed full commit SHAs. **No branch refs have been deleted.**

The repository currently has **no tag rulesets**. Before deletion:
- Create an Active tag ruleset for tag names matching `archive/**/*`.
- Enable **Restrict updates** and **Restrict deletions**.
- Leave **Restrict creations** off.
- Add no bypass actors.

Then manually run `.github/workflows/archive-reviewed-branches.yml` from `main` with:
- `delete_branches=true`
- `confirm_delete=DELETE ARCHIVED BRANCHES`
- `confirm_archive_tags=ARCHIVE TAGS PROTECTED`

The workflow skips branches used by open PRs, checks each branch SHA and tag target, and never deletes `main`. The final phrase is an owner attestation; the workflow does not query repository rulesets.


## Promotion checklist

- [x] Latest Linux verification passes.
- [x] Latest Windows verification passes.
- [x] Latest web typecheck and production build pass.
- [x] Latest Reviewdog run completed and warnings were triaged in context.
- [x] Latest Linux and Windows proof-gate reports were inspected.
- [ ] Complete a final review of all Critical/High-risk changed code paths; this checkpoint's manual review was risk-focused, not line-by-line.
- [ ] Medium findings are fixed or explicitly deferred.
- [ ] Vercel team access and preview deployment are configured, or explicitly deferred from this promotion.
- [ ] The owner reviews PR #15 and approves the exact candidate SHA.
- [x] Re-check fast-forward ancestry before promotion.
- [x] Fast-forward `main` with a non-forced expected-SHA update.
- [x] PR #15 closed after its head became part of `main`; no merge commit was created.
- [x] Archive-only workflow created and verified all ten exact-SHA tags.
- [ ] Configure and verify the Active `archive/**/*` tag ruleset.
- [ ] Manually dispatch deletion mode with both exact confirmation phrases.
- [ ] Verify only `main` remains and all ten recovery tags remain.

## Meaning of this checkpoint

When the checklist is complete, ULTRON is at a **curated, tested consolidation checkpoint**. That is a reasonable “maybe complete?” milestone for this release. It is not a claim that every planned capability, security boundary, update mechanism, web-agent integration, or autonomous behaviour is finished.
