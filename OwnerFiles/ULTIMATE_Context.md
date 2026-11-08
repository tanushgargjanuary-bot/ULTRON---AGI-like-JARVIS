# ULTIMATE Context

This is the current entry point for a new agent. It replaces the old top-level handover; older handovers remain under `history/` for provenance.

## Live state

- Repository: `tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS`
- Working branch: `arena/4c973188-ultron-agi-like-jarvis` (lowercase suffix)
- PR #12 is open to `ArenaAi`. Do not merge it or modify `main` without the owner's explicit instruction.
- OwnerFiles organization commit: `aa2f1b0`; PR #12 remains open. Check `git log` for the current final tip because the ZIP refresh may add a follow-up artifact commit.
- Latest completed CI observed before this metadata update: `42530446726`. Linux suite/self-checks and Windows native checks failed. Exact causes are not available from the sandbox's log summary. Do not say the branch is green; check the live PR for any newer run triggered by this docs update.
- Focused tests at `da01db7`: 102 passed, 1 skipped. This is not a full suite result. The skipped test needs real local OCR dependencies.
- The handoff bundle now includes the organized OwnerFiles tree. Its embedded source snapshot is `d7abf40`; a later artifact/metadata commit updates this archive without embedding itself.

## Immediate next steps

1. Read the latest GitHub Actions logs for run `42529553481`; diagnose the actual failures before adding features.
2. Complete the plan restart/hard-kill proof and review findings for issue #11.
3. Audit each mutating action for tested undo or an explicit irreversible/refusal path; current undo only covers generated text outputs in `file_processor`.
4. Run real Tesseract OCR and verify on the owner's Windows screen. The Linux sandbox cannot prove physical desktop, microphone, camera, or DPI behavior.
5. Finish updater rollback/release acceptance and review/scope PR #12 with the owner.

## Owner's active constraints and preferences

- Keep Ultron/Nova/Cipher/Vanta/Luna as presentation personas with the same tools, capabilities, permissions, and approval rules.
- Persona, theme, and voice remain mix-and-match. Preserve transcript/context through switches; give each persona distinct face animation.
- Local OCR must not upload screenshots or operate controls. Do not duplicate private `antigravity` OCR work.
- Do not edit `core/confirm.py` without explicit owner approval.
- Preserve unrelated work. Do not overstate tests, CI, hardware, or Windows desktop evidence.
- Use Python unless measured end-to-end performance justifies another language. The fuzzy benchmark is synthetic and does not justify Rust.
- The owner wants parallel agents when available. Delegate bounded independent audits; avoid simultaneous edits to shared files. Issue #7 has a branch claim/release convention.
- Private owner-development repository work is out of scope.

## Implemented in the current feature slice

- Persona switching, independent theme/voice persistence, face animation selection, and conversation-context carry-over.
- Optional local OCR rung and sensor-policy classification; real Tesseract recognition is still unverified here.
- Routing purpose adapter for conversation/evolution/critic, live engine wiring, usage accounting, and local spoken conversation-provider switching.
- Pipeline integration test that checks provider switch acknowledgement, persisted setting, preserved old/current history, and no LLM request for the switch turn.
- Conflict-aware undo for generated text outputs in `file_processor`; not universal writer coverage.

## Download the ZIP on Windows

The repository is public. This avoids the broken Arena sandbox preview and does not require local Python:

```powershell
$uri = 'https://raw.githubusercontent.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/arena/4c973188-ultron-agi-like-jarvis/OwnerFiles/ULTIMATE_Context.zip'
$out = Join-Path $HOME 'Downloads\ULTIMATE_Context.zip'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
New-Item -ItemType Directory -Path (Split-Path $out) -Force | Out-Null
Invoke-WebRequest -UseBasicParsing -Uri $uri -OutFile $out
Get-FileHash -LiteralPath $out -Algorithm SHA256
```

- Archive source revision: `d7abf40` (387 project files; `.git` and the ZIP itself excluded).
- ZIP size: `2,181,523` bytes.
- ZIP SHA-256: `a8148157085c7155ace212f68dc0980151845e0d73da9d7f4745a86f38c6ef1b`.
- The embedded project snapshot omits the final archive hash to avoid a self-referential ZIP.

## Bundle contents and maintenance

The ZIP contains the project source snapshot, the OpenMausBot handoff/decision/architecture/backlog/validation notes, and original project documentation. It excludes `.git`, credentials, local runtime state, private repositories, and itself. It is safe to share only to the extent the public repository's `OwnerFiles` policy allows; recheck before adding anything sensitive.

Update this page and the dated evidence in `history/session-log.md` when material facts change. Keep old records in `history/`; do not create another root handover file. Rebuild the ZIP only after reviewing what belongs in it, then verify the archive and checksum before committing it.
