# Health notices and background repair proposals

Ultron's health center is a persistent local inbox for failures it actually detects. It is not an omniscient monitor: availability gaps found during action/plugin startup or an explicit local scan, and runtime errors reported through `core.failures`, can become notices. A feature that never reports its failure cannot yet be surfaced here.

## What a notice contains

Each notice has a stable short ID, source/component, a bounded redacted explanation, first/last-seen times, occurrence count, and status. The local ledger lives under Ultron's user state directory, not in the repository. Runtime stack traces are not copied into the health ledger. Credential-shaped text is redacted before saving.

- `health_center` with `action=status` lists active notices.
- `action=scan` checks local action/plugin availability without probing external bridges.
- `action=ignore` mutes an issue persistently until `action=restore`.
- `action=dismiss` hides the current occurrence; a later detection can reopen it.
- `action=jobs` or `action=job` reports background repair status.

New detected issues are announced once in the activity log with their ID and available actions. Repeated reports for the same active issue update its occurrence count rather than flooding the log. Configured bridge services are not probed automatically. `health_center action=scan_bridges` explicitly checks configured readiness endpoints/CLI presence; it does not invoke their tools. A local `scan` never contacts configured remote services.

## Background fix workflow

A `fix` request includes an issue ID and a candidate patch (`path`, `reason`, plus whole-file `text` or one exact `find`/`replace`). The job runs on a daemon worker so ordinary conversation continues. It stages the candidate through `core.self_change`, then runs the full verification harness in a temporary copy. Jobs report `ready_for_review`, `verification_failed`, `failed`, or `interrupted` after restart.

A successful job only creates a rehearsed proposal. It does **not** write source files, confirm, or apply. The owner reviews the diff with `self_modify show`, confirms in two separate channels, and then explicitly applies. There is one background self-change rehearsal at a time to avoid conflicting proposals. Failed, timed-out, or missing verification blocks application.

There is no dedicated dashboard button in this first slice; the health action and activity-log instructions provide the controls. A model can suggest a candidate patch, but its confidence is not a gate and the full test harness remains mandatory.
