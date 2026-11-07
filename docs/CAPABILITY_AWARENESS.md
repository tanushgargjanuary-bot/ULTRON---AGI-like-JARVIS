# Capability awareness

> **Verification status: NOT TESTED.** The capability guide and repository scout have not been run in Jarvis or through the project's test suite. The checks in `tests/test_capability_guide.py` are present but unexecuted in the current environment.

## What this change adds

- `actions/capability_guide.py` maps a user's stated goal to the live tool catalog and installed skill recipes. It uses small editable synonym and task-cue tables, and reports when a tool is unavailable.
- `actions/github_repo_scout.py` searches public GitHub repository metadata for leads when no ready tool matches. It does not inspect source code, clone, download, or install projects.
- `core/prompt.txt` tells Jarvis to consult its capability guide when a user is unsure or stuck, and to use the repository scout for a capability gap. Self-changes remain behind the existing `self_modify` review and rehearsal process.

## Limits and next checks

This is a first routing layer, not a self-improving autonomous system. Its cue tables can miss unfamiliar wording or suggest a broad tool family; repository stars and update dates do not establish source quality, license compatibility, or safety. Check the tool's actual availability and description before acting.

When a runnable checkout is available:

1. Run `python -m pytest tests/test_capability_guide.py`.
2. Run the project's standard verification command, `python scripts/verify.py`.
3. Manually confirm compression, workspace-review, unavailable-tool, and unsupported-task requests in Jarvis.
4. Compare those same requests against the pre-change behavior; fix false matches before calling the feature ready.

## Read-only branch review

The `antigravity` branch contains a context detector and a large repository-candidate catalog. The `arena/4c973188-ultron-agi-like-jarvis` branch contains an agent workspace report and a test-first change playbook. These were inspected read-only; no files on those branches were changed. Their useful design ideas are to add context only when it helps routing, and to keep verification status explicit. They were not copied because this change cannot yet be exercised against the full app.
