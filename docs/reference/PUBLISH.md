# Publishing Ultron to GitHub

**Done.** The repository is live and it has the full history, not a snapshot.

    https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS
    branch main · 7 commits · pushed 2026-11-06

Ultron now ships its own next changes through `custom_jarvis/ship.py`. This page
keeps the parts a person needs: which token settings work, what is excluded, and
what to do when a push is refused.

## The token, measured on 2026-11-06

Two tokens were tried and the answers are recorded because the failure message
does not name the missing permission.

| Token | Settings | Result |
|---|---|---|
| Fine-grained, `Contents: Read` | repository access: this one repo | `GET` works, `PUT contents` → **403 "Resource not accessible by personal access token"** |
| Fine-grained, `Contents: Read and write` | same | writes work, but `git push` → **refused: "…workflow `.github/workflows/verify.yml` without `workflow` scope"** |
| **Classic, scopes `repo` and `workflow`** | — | **push accepted** |

**The lesson.** `.github/workflows/verify.yml` has been in this history since the
first commit, and GitHub checks the *whole push*, so one workflow file gates every
commit. A fine-grained token therefore needs **two** permissions: `Contents` and
`Workflows`, both Read and write. A classic token needs the `repo` and `workflow`
scopes. A token without `Workflows` is refused no matter how correct the code is.

Where it goes: `config/api_keys.json` as `github_token`, or the `GITHUB_TOKEN`
environment variable. Never in `.git/config`, never in a commit, never in a shell
history. `ship.py` reads it from the environment first, then from the config file,
then from `<state>/github_token`.

## Pushing by hand (PowerShell)

```powershell
cd path\to\mark-jarvis
git remote -v                     # origin must point at the repository above
git status -sb                    # expect: ## main...origin/main
git push
```

If `git push` asks for a password, it wants the token, not the account password.
GitHub has not accepted account passwords for pushes since 2021.

## What is published, and what is not

| Excluded | Reason |
| --- | --- |
| `config/api_keys.json` | every provider key lives in it. A public repository full of keys is a bill, not a project. |
| `memory/long_term.json` | what the assistant learned about the owner. Personal by definition. |
| `restart-required.json`, `ship_pending.json`, ship logs | machine state. They live beside the state folder, and `.gitignore` names them twice. |

`log.txt`, `verification-results.txt` and the whole of `OwnerFiles/` **are**
published on purpose: the owner wants the record of how this was built to be
readable by anyone, including another AI. `OwnerFiles/owner/owner-notes.md` is his own
file and holds nothing private.

## The licence line, which is the only legal boundary here

Ultron is a derivative of **FatihMakes/Mark-LVI**, licensed **CC BY-NC 4.0**.
That licence allows publishing this work non-commercially **with attribution**.
It does not allow selling it. Keep `LICENSE` and the attribution paragraph in
`readme.md`; deleting them is the one change that makes the repository unlawful,
not the publication itself.
