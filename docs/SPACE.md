# Keeping the workspace small

The workspace is the folder this project lives in. It is saved as a whole after every
message. That save has a hard ceiling: about **128 MB** and **10,000 files**. Anything
past the ceiling is **not saved, and no message says so**.

This has already cost us files. One session installed the whole dependency set inside
the workspace instead of in a temporary folder. For a while the workspace held
**375 MB across 6,711 files**. The next save kept 128 MB and quietly dropped **6,352
files**.

Nothing in the project was wrong. The habit was.

## The rule

**Keep the project under 100 MB and under 5,000 files.** Both numbers are checked, not
remembered.

```powershell
python scripts\workspace_budget.py            # report; exit 1 if over budget
python scripts\workspace_budget.py --json     # the same, for a tool
python scripts\workspace_budget.py --clean    # delete the caches it names
```

`scripts\verify.py` runs this check first, and the test suite runs it again. A
workspace that has grown is a red build, not a surprise before a lost save.

## Install packages outside the project

This is the mistake that caused the loss. Two lines prevent it.

```powershell
$env:PIP_CACHE_DIR = "$env:TEMP\pipcache"
python -m pip install --target "$env:TEMP\deps" <package>
```

`--target` writes the packages to a temporary folder. `PIP_CACHE_DIR` keeps pip's own
cache out of the project too. Then run with that folder on the path:

```powershell
$env:PYTHONPATH = "$env:TEMP\deps"
```

The same idea applies to `npm` (`--prefix`), to `cargo` (`CARGO_TARGET_DIR`), and to
any tool that keeps a cache. If a command's default is "write it next to me", change
the default.

## What is counted, and what is not

| Counted against the budget | Not counted |
|---|---|
| every source file, document and test | `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache` |
| the sidecar binary that ships with the build | `.venv` and `.venv.old` — a virtual environment belongs to the owner and is 600 MB |
| `config/`, `memory/`, `verification/` | `node_modules`, `build/`, `dist/` |

A generated folder is still **reported** on its own line, so the number stays visible.
It is simply not held against the project, because a check that fails on the owner's
machine for a reason the owner cannot fix is a check that gets switched off.

## Where the size goes

Measured on 2026-11-06:

| Folder | Size | Files |
|---|---|---|
| `sidecar/` (the Windows helper that ships) | 2.1 MB | 6 |
| `.git/` (the history) | 2.1 MB | 49 |
| everything else, all text | 4.7 MB | 282 |

**The code is text and it is already small.** There is no honest way to compress it
much further: the remaining levers all remove something. So the ceiling is kept by
not adding weight in the first place.

## What was removed, and what was kept

Removed, because a build can make it again:

- `sidecar/bin/watchd-linux` — the Linux background helper, built from Go source in
  this repository. About 1 MB.

Kept, and why:

- `sidecar/bin/watchd-windows.exe` — 2.1 MB, and the largest file in the tree. The
  owner's machine has no Go toolchain, so if this file is not here the Windows build
  has nothing to ship. It is the payload, not build litter, and
  `tests/test_workspace_budget.py` names it as the one allowed heavy file.
- `log.txt`, `verification-results.txt`, `HANDOFF.md` — long, and required. History is
  not overhead. Removing a record to make a number smaller is the wrong trade.

## The habit, in one sentence

**A file that can be generated belongs outside the project; a file that records
something that happened belongs inside it.**
