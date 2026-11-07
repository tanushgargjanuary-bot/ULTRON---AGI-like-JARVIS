# Keeping the repository clean

## There is no size budget

The owner withdrew it on **2026-11-07**. The ceiling was 100 MB and 5,000 files, and it
stopped real work for a limit this repository does not have: it lives on GitHub, where a
few hundred megabytes of source is not a problem.

So the check is gone, not silenced. `scripts/workspace_budget.py`, its test, its step in
`scripts/verify.py` and its row in `docs/INDEX.md` were deleted in the same change. Nothing
fails on size now, and nothing on this page claims a number that something else enforces.

## What still holds — habits, not ceilings

- **A file that can be generated belongs outside the repository.** A build artifact in Git
  is a file nobody can audit. `sidecar/bin/watchd-windows.exe` is the one exception,
  because the owner's machine has no Go toolchain to build it.
- **Install packages outside the project.** `pip install --target "$env:TEMP\deps"` with
  `PIP_CACHE_DIR` set outside the folder keeps `git status` readable. That is the reason now
  — not a number.
- **`logs/`, `config/api_keys.json` and `memory/long_term.json` stay ignored.** That is
  privacy, and it has nothing to do with size.

## If you want the size anyway

`du -sh .` answers it in one line. It is information, not a gate.

The habit in one sentence is unchanged: **a file that can be generated belongs outside the
project; a file that records something that happened belongs inside it.**
