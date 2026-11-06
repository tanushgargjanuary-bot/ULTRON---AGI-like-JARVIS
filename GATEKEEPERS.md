# GATEKEEPERS — what is actually between us and a working Ultron

Rewritten 2026-11-06, build 1.2.9, after you pushed back on the first version.
Updated 2026-11-07, build 1.2.36: the two things this page used to call gates are
closed. **There is CI now**, on `ubuntu-latest` and `windows-latest`, green on the last
push, and the product **has** run on Windows — the window renders at three sizes, the
claim that was PARTIAL for weeks because no Windows machine had ever run it. What
remains open is hardware this repository cannot reach: your microphone, your speaker,
your camera, your display and your account. The corrected sections are marked below;
nothing else here was rewritten to look better than it is.

The original objections, still standing:

- **Legality is not a gate here.** CC BY-NC 4.0 restricts *distribution*, and a
  private Ultron on your own machine is not distribution. Zero exposure, not a
  factor, removed from this document.
- **Decision gates are not gates.** They are choices. Removed. (Two of them still
  show up below as findings, because the *code* is what is missing, not a decision.)
- **Build gates are not a wall.** You are right that a key is not a wall. There is
  exactly **one** build gate now — the key — and it is a one-liner.

Which left the thing that actually stood in the way, and it was not a gate you could
buy your way through: **nothing in this product had ever run on Windows.** Not the
window, not the microphone, not the tree, not the browser, not one real model call with
your account. That was not a build problem, it was an evidence problem, and
`scripts/proof_gate.py` was the instrument built for it.

**Since then:** the window, the tree, the browser library, CI and the tool list have all
run on Windows. What has still never run there is the part only you own - your microphone
at your device's real rate, your speaker, your camera, your display at your scaling, and
one real model call with your account. That list is what the remaining 13 PARTIAL claims
are about, item by item, lower on this page.

---

## BUILD — one gate, one line

**A provider on first run.** Paste a key in the first-run panel, or point it at
Ollama/LM Studio on `http://127.0.0.1:11434/v1`. Without it the HUD opens, the
avatar idles, and nothing else happens — every feature is downstream of the model.
That is the whole of the build gate.

Everything else I listed as a build gate last time is **setup**, not a gate: it
happens once, mechanically, and none of it can silently change product behaviour.

| setup item | one-time cost | if it goes wrong |
| --- | --- | --- |
| 64-bit Python 3.11–3.13 | `run.bat` offers to install 3.12 via winget | launcher stops and says so; 3.14 is refused on purpose |
| Playwright browsers | ~400 MB, fetched by setup unless `ULTRON_SKIP_BROWSERS=1` | `browser_control` is absent from the session, and the activity log says so |
| Audio device at 16 kHz | none — Windows resamples | some Bluetooth headsets open and deliver silence; `verify_audio.py` names the rate it got |
| Elevation | none — runs at your integrity level | UIA cannot see into elevated windows (Task Manager, installers). That is Windows, not a bug |

---

## PROOF — the actual gatekeeper, and the instrument for it

```powershell
.\.venv\Scripts\Activate.ps1
python scripts\proof_gate.py
python scripts\proof_gate.py --live           # with your real key / local model
python scripts\proof_gate.py --json proof.json
```

Thirty-five **claims**, each a chain rather than a checklist, because a microphone that
records and a model that answers have not, together, heard and answered anything
until the sentence has come out of the speaker. The last count on Linux, with no display
and no hardware attached: **22 PROVEN, 13 PARTIAL, 0 FAILED**. Four verdicts:

| verdict | means | what to do |
| --- | --- | --- |
| `PROVEN` | every step ran and fed the next one | nothing |
| `PARTIAL` | some steps proved, a later one needs hardware/OS/key | re-run on the machine that has it |
| `FAILED` | a step ran and produced the wrong thing | send me the line — that is a defect |
| `NOT PRESENT` | **there is no code behind the claim** | a missing feature, not a broken one |

`NOT PRESENT` is the verdict I care most about, because it is the one an
enthusiastic report would quietly round up to "works".

### What the gate already says on this Linux container

| claim | verdict | because |
| --- | --- | --- |
| consent | **PROVEN** | a capture is withheld, a banner is requested, CANCEL clears it, and `policy.classify` files screen capture under `Tier.SENSOR` |
| persona | **PROVEN** | name `Ultron`, aliases Ultron/Jarvis/J.A.R.V.I.S/Mark, 2,612-word prompt, `{assistant_name}` interpolated |
| acts | **PARTIAL** | a tool call wrote and read back a real file in `~/Documents`; a write to `/tmp` was **refused**; an SSH key path was refused **as credentials**; the model's chosen tool was declared and callable. Only "does a real model choose well" is unproven |
| brain | **PARTIAL** | transport, timeouts, tool-call parsing proven against a local fake; quality needs `--live` |
| budgets | **PARTIAL** | in-process reply latency 8 ms and 55 MB measured; `import main` could not run here (no PortAudio), so the real startup number needs your machine |
| sees_screen, voice_in, voice_out, focus_safe, browser, console, sees_camera, ui, provider_switch | **PARTIAL** | each prints the exact step that could not run: no display, no PortAudio, no Playwright, not Windows |
| **memory_approval** | **PROVEN** (1.2.10) | the write parks behind the HUD confirmation; the banner shows the fact verbatim; nothing is stored until CONFIRM; a second pending write is refused aloud instead of replacing the first |
| **digest** | **PROVEN** (1.2.11) | built on request: reports today's facts, older count, watched topics and reminder names; proven inert — no socket, no process, no file touched while it builds — and it runs once a day at the configured hour |
| **tool_catalog** | **PROVEN** (1.2.12) | 45 tools from inline/action/plugin/bridge; every unavailable tool carries its blocker; `tools_status` is declared and handled |
| **plugins** | **PROVEN** (1.2.12) | 12 plugins load, validate, and each returns a sentence when called with no arguments; the five tool bridges are among them |
| **tool_tabs** | **PROVEN** (1.2.12) | the TOOLS panel renders nine tabs, the count matches the catalog, and Ctrl+T opens it without a mouse |
| **github** | **PROVEN** (1.2.16) | six steps: a search for recently created repositories sorted by stars, built from the documented API; the answer says GitHub has no trending API; the token is sent as a bearer header and is **absent from the cache file**; no network and no token are two different useful sentences; and the plugin answers in a sentence when GitHub is unreachable |
| **self_extension** | **PROVEN** (1.2.16) | six steps: a JSON pack becomes a live skill and one file on disk; a writing tool, a built-in id, a path outside the workspace and a nine-step pack are all **refused**; a pack is removable in one call while a built-in refuses; a saved pack is loaded again at the next start; and `add_skill` reaches the pack layer through the tool registry |
| **reminders** | **PROVEN** (1.2.16) | five steps: a failing build (+1.15) outranks a trending repository (+0.12) by the same arithmetic that chooses an action; a cooldown stops repetition; a card worth less than its interruption is dropped; at 03:00 only an emergency is spoken; and a watched repository becomes cards |
| **shipping** | **PROVEN** (1.2.17) | seven steps against a real bare git remote: an assignment-shaped key stops the run at `scan` and **no commit reaches the remote**; a `github_pat_` string of the real length is caught while four placeholder fixtures are not; a ship lands on the remote with `Why:`, `Evidence:` and a secret-scan line in the message; a remote that moved is refused at `push` with "will not force"; with no token the answer is a sentence, not a git error; and every attempt is written to a ship log |
| **self_update** | **PROVEN** (1.2.17) | six steps against a real remote: an up-to-date copy applies nothing; a documentation change is taken with **no restart** (data is read on demand); a changed `.py` writes a restart marker naming the file and says why; a version that does not parse is **reverted to the previous commit** with the broken file gone; a dirty tree is refused rather than overwritten; and the marker lives beside the state, never in the tree, because an untracked file in the tree blocks the next update |
| **decisions** | **PROVEN** (1.2.15) | eight steps: expected value picked the careful option at +0.85; a guaranteed loss and a `blocked` option are both answered with "do none of these"; a chance of 1.7 and an unknown risk tier are refused; BM25 put the rare matching word first and returned **nothing** for an unrelated question; fourteen normal turns stayed quiet and a 9.0 s turn was flagged; a 1-in-1 option was explored once and then lost to the 12-in-12 option; and `decide` is reachable as a tool that asks no permission |
| **metacognition** | **PROVEN** (1.2.14) | eight steps: the ledger imports; 3 of 3 is reported as accuracy 1.0 with a bound of **0.439** and the verdict "not yet evidence"; 40 of 40 earns **0.912**; claims made at 95% and wrong are named as a 90-100% bucket with 0% hit rate (Brier 0.90); a lesson with no rule is **refused**; the rule comes back for a matching task and its use is counted; the proven strategy is passed over once so the untried one gets a fair test; one JSON file, no model, no network |
| **triggers** | **PROVEN** (1.2.33) | every tool leads with the condition that should trigger it, the model is told to match the request to the condition, two calls are counted as two, and the tool status names what has never been used. The test that mattered: measuring the real prompt showed the old budget watched the inline tools only — 16,620 characters — while the app sent 22,320 |
| **crash_record** | **PROVEN** (1.2.34) | eight steps: a report is written for an uncaught error, a worker thread, an unraisable object and a native fault; it carries the build, the kind, the traceback and the last notes before the fall; a credential in the message is **replaced**; the 21st report deletes the oldest; the next start says it crashed; and a proposal carries the crashes it was made from |
| **plugins** (extended 1.2.35) | **PROVEN** | as before, plus: **the provider accepts the list** — 46 declarations, every `required` name declared, every type the API knows. That step exists because five bridge plugins broke it and the whole session was refused with `1007` |
| **whatsapp** | **PARTIAL** (1.2.13) | driver exists and refuses a stranger; a real WhatsApp window needs Windows, so the last step is a SKIP, not a pass |

The **daily digest** was `NOT PRESENT` in 1.2.9 and removed from the gate in
1.2.10 as an Agentic OS property. You asked for it natively in Ultron, so it is
built, and the gate proves it is inert. `sees_screen` no longer reports `FAILED`
on a machine that has no screen: that is a `SKIP`, and `FAILED` is kept for a
machine that has a display and returns no frame. Details in `log.txt` PHASE 27 to
PHASE 29.

---

## What the gate will settle on your machine

Each of these flips from PARTIAL to PROVEN or FAILED the moment it runs on your
hardware, and nothing else I can do from here will move them:

1. **voice_in** — mic at your device's real rate, a peak above zero, and a
   transcript that matches what you said. (If peak is 0: Windows microphone
   privacy switch, not the code.)
2. **voice_out** — synthesis into PCM, then out of your speaker, and it sounds
   like speech.
3. **sees_screen** — a real desktop frame. Multi-monitor and mixed DPI is where
   `mss` actually gets tested.
4. **sees_camera** — your webcam, behind the consent gate, with the indicator and
   the stop.
5. **focus_safe** — the one that matters most for your "must not disturb my
   screen work" rule: hold a key in another app, run an action, confirm the
   foreground window never moved. UIA `InvokePattern` is designed for this; it has
   never been observed doing it.
6. **browser** — Playwright engine plus `browser_control` against a real page.
7. **brain (with `--live`)** — your account, your model, your latency, and whether
   it picks sensible tools.
8. **budgets** — startup seconds, idle RAM, spoken-turn latency against the
   numbers you actually care about. Set them: `--budget-startup 20 --budget-ram 900
   --budget-turn 4`. Until they exist, "zero performance issues" is not a claim
   that can be true or false.
9. **console** — that nothing flashes a black window while you type.

Two things no instrument can settle, and both are real:

- **SmartScreen / Defender.** An unsigned Python app that installs packages,
  injects keystrokes, reads the accessibility tree and captures the screen is,
  functionally, the description of a remote-access trojan. Expect an "unknown
  publisher" prompt on first run, and possibly a behaviour alert. Only a code-signing
  certificate changes that; no code change does.
- **Whether it looks right to you.** `verify_display.py` proves the window draws
  and the log panel is inside the frame. Legibility at your DPI is your eyes.

---

## The one structural gate — closed on 2026-11-06

This section used to say: **"There is no CI, so not one test has ever run on Windows
automatically."** That was true when it was written and it is not any more.
`.github/workflows/verify.yml` runs the suite, the machine verifier and the proof gate on
`ubuntu-latest` and `windows-latest` on every push, and both jobs are green on the last
push of build 1.2.36.

It paid for itself on the first night. It found four defects Linux could not see: a
workflow flag no script declared, a report folder missing on a fresh clone, three
instruments that called a missing device a broken product, and a claim whose code called
a method that was never written. In 1.2.34 it found two more in code that had already
passed on Linux: an open fault-handler handle that stopped a temporary folder being
deleted on Windows, and a test that used `chmod` to make a folder unwritable — a **false
pass**, because Windows ignores `chmod`.

**A red CI job is a real defect, not noise.** Read the job log, fix the code, and never
mark it as an environment problem without evidence.

---

## The shortest path from here

1. Install once with `run.ps1`, paste a key, and run
   `python scripts\verify_all.py` — that is the instrument that answers what **your**
   PC does, and it reports SKIP where a question does not apply.
2. Then `python scripts\proof_gate.py --live`. Whatever reads `FAILED` is the next
   defect. Whatever reads `NOT PRESENT` is a feature you either want built or do not —
   say which.
3. Set the three budget numbers, so "zero performance issues" becomes a sentence that
   can be true or false.
4. Then stop testing and use it for a day. The defects that survive that are the ones no
   instrument here can invent — and each of them now leaves a file in `logs/`, so the
   next agent starts from the report instead of from a guess.
