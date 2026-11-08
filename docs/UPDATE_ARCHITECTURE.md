# Self-update and rolling-release design

**Status:** Approved direction; implementation not complete. This document describes the selected rollout model and the safe path from the current updater to it.

## Owner's choices

- Keep the existing public repository as the **professional/upstream project**.
- Use a separate **private owner-development repository** for personal experiments, self-edits, and the owner's canary releases. Only the owner's machine should hold credentials for it.
- The owner's Ultron follows the private `owner-canary` channel. Other installations use the public repository's curated stable releases and never receive the private remote URL or credentials.
- For core-code updates, use a **supervisor and worker handoff**: keep the visible app/control process alive, let active work finish, start and health-check a candidate worker, switch new work to it, then drain the old worker.

This split gives the owner's installation exclusive access to the **private** development repo, subject to any collaborators explicitly invited to it. Keep its Git credential in Windows Credential Manager or an SSH agent; never embed it in Ultron, source, prompts, logs, or release artifacts. The public repo remains readable by everyone and is not the place for private experiments.

## Separate private development, public promotion, and installed updates

Treat these as three different operations:

1. **Private source change:** Ultron may prepare a bounded code change in its private checkout. It must use the existing self-change rehearsal, two independent confirmations, tests, secret scan, and a reviewed change/PR path. It must not alter protected referee files. It should work on a private feature branch, not directly rewrite the private default branch.
2. **Public promotion:** Only changes deliberately selected for professional use are proposed from the private repo to the public upstream through a reviewed PR. Personal configuration, credentials, logs, and unpromoted experiments stay private.
3. **Release and installation update:** CI builds immutable, versioned Windows artifacts from approved source revisions. The private pipeline may publish owner-canary releases; the public pipeline publishes curated stable releases. Each release records its source commit and hashes and is signed or carries verifiable build provenance. An installation downloads an artifact, verifies provenance and hashes, tests it in an inactive slot, and only then switches to it.

This is how the public project can improve without changing every running installation at once: merge source, publish a release, then let each installation follow its own channel. The owner's machine may auto-follow private `owner-canary`; public installations use curated `stable` releases and remain manual unless their owners opt in. The private repo URL and credentials are never distributed.

## Channels and local configuration

- `owner-canary`: the owner's installation explicitly selects the private development release channel. Keep the channel choice in per-user state outside the Git checkout (on Windows, under the user's local application-data directory). The private Git credential remains in the OS credential store/SSH agent, not in this file.
- `stable`: curated public releases for professional/public installations. Default to notification/manual approval until those owners explicitly choose another policy.
- A channel is not an access-control boundary. Private-repository access comes from the private remote's GitHub ACL and the owner's locally stored credential, not a secret branch name or machine ID.
- Never put GitHub credentials in the updater command line, source, logs, or release metadata. Public release downloads should need no repository write credential.

## No-shutdown handoff for core changes

Python cannot safely replace arbitrary imported modules or existing objects in place. Keep the current safe action/plugin generation reload for leaf updates; do not try to `reload()` the whole application.

For core releases, split the running application into:

- a **stable supervisor/control process** that owns the window, local status, update coordinator, and worker lifecycle; and
- a **versioned runtime worker** that owns provider sessions and tool execution.

The update transaction should:

1. Stage the new version beside the active one; never overwrite the active version in place.
2. Verify release provenance, file hashes, supported platform, dependencies, and migrations.
3. Start a candidate worker with a private health-check channel. Do not route user requests to it yet.
4. Require startup, tool-catalog, policy-identity, and readiness checks to pass. Keep the old worker serving while the candidate is checked.
5. At a safe boundary, route new work to the candidate. Let in-flight work finish on the old worker; do not kill it to meet an update timer.
6. Retain the previous version and state backup until the candidate has completed a health window. If startup or health checks fail, route back to the old worker and report the reason.

The window/control process stays open. There can still be a short wait or provider reconnect while work drains. If the owner requires an active conversation never to be interrupted, defer the switch until that conversation is idle. User data and settings remain outside version directories; migrations must be reversible or refuse the update.

## Current implementation and gaps

The current `custom_jarvis/selfupdate.py` pulls the current Git branch fast-forward-only into the live checkout, refuses a dirty tree, checks Python syntax, and rolls back to the prior commit if verification fails. It marks non-leaf Python changes as restart-required. `core/leaf_generations.py` can stage action/plugin generations at a safe reconnect boundary. These are useful safeguards, but they are **not** a signed release system, A/B install, update channel, or full no-shutdown core updater.

`main.py` currently owns the GUI and live runtime together. A safe core handoff therefore needs a deliberate supervisor/worker boundary and IPC contract; adding a background `git pull` or reloading `main.py` would not satisfy the requirement. The existing update tool remains approval-gated. No automatic code update should be enabled before the release verifier, rollback path, and supervisor health checks exist.

## Implementation stages

1. **Model and contracts — first slice implemented:** `custom_jarvis/update_releases.py` now validates the local `stable` / `owner-canary` preference, verifies a strict manifest with an Ed25519 key supplied by a trusted local caller, and hashes a staged artifact before extraction. Its 11 tests use an ephemeral key and temporary files. There is not yet a production public key, release manifest publisher, network fetcher, or integration with `Updater`; without a trusted key it fails closed. Update checks remain read-only.
2. **Release pipeline:** build a Windows artifact from an approved commit; attach source commit, hashes, and verifiable provenance. No installer runs repo-supplied post-install scripts outside the approved package process.
3. **A/B updater:** stage immutable version directories, verify before activation, keep user state separate, atomically switch the active-version pointer, and test rollback with injected failures.
4. **Supervisor boundary:** move provider/runtime work behind a worker process while keeping the GUI/control process stable. Specify bounded IPC, cancellation, draining, health checks, and stale-worker recovery.
5. **Owner canary:** enable auto-apply only for the owner's local `owner-canary` setting after Windows tests and proof-gate claims demonstrate the full update-and-rollback path. Keep other installations on stable/manual by default.

## Acceptance checks

- A public source update never gives an installed app a repository write credential.
- A bad signature, hash, platform, dependency check, migration, or health check leaves the active version untouched.
- A failed candidate returns to the prior worker/version without losing user data.
- An in-flight tool call is never killed by an update; updates wait or drain at the documented boundary.
- Only the owner's installation is configured for owner-canary by default; stable users do not silently receive canary code.
- Core safety gates, policy, confirmation, self-change, and proof-gate identity remain protected from model-authored updates.
- Tests cover successful activation, refusal, interrupted download, failed startup, failed health check, rollback, dirty user state, and Windows process cleanup.
