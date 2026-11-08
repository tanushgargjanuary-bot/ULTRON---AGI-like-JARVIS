# ULTIMATE Context ZIP

`ULTIMATE_Context.zip` is the handoff bundle for an agent that needs both the project snapshot and the current session context.

## Current artifact

- File: `OwnerFiles/ULTIMATE_Context.zip`
- ZIP SHA-256: `bf614e08b993f47963ee5e413a80ec1658cd4770be6d7766ca81dc246bde8fee`
- Contains the 386-file tracked project source snapshot at commit `da01db7bf66c682af79c5b945ba55325545d3bfe`, plus the OpenMausBot handoff docs, validation notes, backlog, user preferences, GitHub state, and collaboration tips.
- `.git`, credentials, local runtime state, and private owner-development repositories are excluded.
- This ZIP is a snapshot, so its embedded project tree intentionally predates this archive's addition to the branch. It does not embed itself recursively.

## Get it on Windows

The repository is public. In PowerShell, this downloads the committed file to Downloads and prints its hash:

```powershell
$uri = 'https://raw.githubusercontent.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/arena/4c973188-ultron-agi-like-jarvis/OwnerFiles/ULTIMATE_Context.zip'
$out = Join-Path $HOME 'Downloads\ULTIMATE_Context.zip'
Invoke-WebRequest -UseBasicParsing -Uri $uri -OutFile $out
Get-FileHash -LiteralPath $out -Algorithm SHA256
```

The expected SHA-256 is printed above. This uses no local Python installation. The raw URL points at the branch tip, so this download is available after the commit is pushed.

## Updating this archive later

Regenerate only when the handoff itself changes materially. Update the handoff documents first, create the new bundle from the exact tracked source commit, validate the ZIP with `unzip -t`, record the source commit and SHA-256 here, then commit/push both archive and metadata. Keep secrets and private owner-repo material out.
