# Tools Ultron should have next

Written on 2026-11-06 for build 1.2.12. It answers two questions the owner asked:
which Computer Science, web development and cybersecurity tools belong in Ultron,
and what else a "cool Ultron" needs.

## How a tool earns a place here

A tool is a candidate only if all five lines are true.

1. It runs on Windows without a server.
2. It answers a question Ultron is asked by voice.
3. It has a stable interface: one executable, one CLI, or one HTTP port.
4. It fails in a sentence, not a stack trace, when it is absent.
5. It can be refused. A tool that cannot be turned off is not accepted.

The cost of a tool is not the code. The cost is the prompt, the tab, the test,
and the risk table row. Five integrations are already done: REA, HyperFrames,
Hindsight, VoiceStudio and Hypit. This list is what comes next.

## Tier A — integrate now, low risk, high value

These are local, read-mostly or reversible. Each one is a CLI bridge of about
30 lines, the same shape as `core/bridges.py`.

| Tool | What it gives Ultron | Interface | Risk | Windows |
| --- | --- | --- | --- | --- |
| **ripgrep** (`rg`) | Fast text search over a folder in under a second | CLI, JSON output | OBSERVE | one `.exe` |
| **ast-grep** (`sg`) | Search and rewrite by code structure, not text | CLI, JSON | ROUTINE for search, GUARDED for rewrite | `npm i -g @ast-grep/cli` |
| **ruff** | Lint and format Python before it is written to disk | CLI, JSON | ROUTINE (lint), GUARDED (fix) | pip wheel, no compiler |
| **semgrep** | Static analysis with a rule library that is readable | CLI, JSON | OBSERVE | pip, needs Python 3.9+ |
| **trivy** | Known CVEs in a folder, a lock file or an image | CLI, JSON | OBSERVE | one `.exe` |
| **git** | Diff review, blame, log, branch — the questions a coder asks | CLI, porcelain | OBSERVE read, GUARDED write | already on the machine |
| **jq** / **yq** | JSON and YAML queries without a script | CLI | OBSERVE | one `.exe` each |
| **tokei** | Lines of code per language, instantly | CLI, JSON | OBSERVE | one `.exe` |
| **pandoc** | Markdown to DOCX, PDF to Markdown, 40 formats | CLI | ROUTINE | one `.exe` |
| **ffmpeg** | Cut, convert, compress any audio or video | CLI | ROUTINE | one `.exe` |

Why these ten first: each one replaces a guess. "How many lines", "where is this
string", "does this file have a known CVE" and "convert this to PDF" are
questions Ultron currently answers by asking a model, which is slower, dearer,
and sometimes wrong.

## Tier B — web development

| Tool | What it gives Ultron | Interface | Risk |
| --- | --- | --- | --- |
| **Lighthouse** | Performance, accessibility and SEO score for a page | `npx lighthouse --output json` | ROUTINE |
| **axe-core CLI** | Accessibility defects, the same idea as our tree-first screen reading | `npx @axe-core/cli` | ROUTINE |
| **ESLint** / **Prettier** / **Stylelint** | The three linters a web project already has | CLI, JSON | ROUTINE, GUARDED to fix |
| **TypeScript** (`tsc --noEmit`) | Real type errors instead of a plausible answer | CLI | OBSERVE |
| **k6** | Load test a local endpoint and report p95 | CLI, JSON | GUARDED |
| **newman** | Run a Postman collection as a test suite | CLI, JSON | GUARDED |
| **svgo** | Shrink an SVG without changing how it looks | CLI | ROUTINE |
| **Vite** | Scaffold and build a front end | CLI | GUARDED (writes files) |
| **Storybook** | Only if the owner builds interfaces; heavy, 400 MB+ | CLI | low value here |

Two are worth more than the rest. **Lighthouse** answers the question the owner
asks most often ("why is this page slow") with numbers. **axe-core** matches the
standing rule that structure beats pixels: it reads the page the way Ultron tries
to read windows.

## Tier C — cybersecurity

The line here is consent, not capability. Each of these is a real, legal tool
that can also be pointed at a host that is not yours. Ultron must refuse a public
target unless the owner says so in the same turn, and must record the refusal.

| Tool | What it gives Ultron | Risk | Guard needed |
| --- | --- | --- | --- |
| **osv-scanner** | Dependency vulnerabilities from the OSV database | OBSERVE | none |
| **bandit** | Security lint for Python | OBSERVE | none |
| **gitleaks** | Finds secrets that were committed by mistake | OBSERVE | path confinement |
| **testssl.sh** / **sslyze** | TLS configuration of a host you own | GUARDED | private host only |
| **nmap** | Port and service inventory of the local network | GUARDED | private range only, named host, one scan |
| **tshark** | Read a packet capture file | SENSOR | capture requires consent + indicator |
| **mitmproxy** | Watch traffic from your own device | SENSOR | explicit consent, stop control |
| **YARA** | Match files against malware rules | OBSERVE | path confinement |
| **Ghidra** / **rizin** | Disassembly, deeper than REA's agent view | GUARDED | files the owner names |
| **Volatility 3** | Memory forensics on an image file | OBSERVE | path confinement |
| **hashcat** / **john** | Recover a password from a hash you own | GUARDED | offline only, never a service |
| **CyberChef** | The "what is this string" workbench, as a local page | OBSERVE | served on loopback |

**CyberChef is the highest-value single addition in this table.** It is a static
web application with no backend, it runs from a folder, and it does exactly what
`crypto_ident` now does by hand — decode, unpack, hash, convert — for a hundred
formats. Ultron can serve it on `127.0.0.1` and open it in a tab next to the tool
list. That is one afternoon of work for a large capability jump, and it is safe
because nothing leaves the loopback interface.

**Do not add**: Metasploit, sqlmap, Hydra, exploit-db search, or any "scan the
whole internet" tool. They are legal when used correctly, and the correct use is
not something a voice assistant can verify. The cost of one wrong target is a
criminal act. That is not a risk worth a feature.

## Tier D — the local brain and the local ear

| Tool | Why | Note |
| --- | --- | --- |
| **Ollama** | Runs the 1.5–3B quantized model the owner approved, on his own machine | the one dependency that makes offline mode real |
| **faster-whisper** (or whisper.cpp) | Transcribes offline, and transcribes uploaded audio | Whisper.cpp is a single `.exe`, no Python |
| **Piper** | Local neural speech out, small and fast | keeps the voice working with no network |
| **sqlite-vec** or **Chroma** | Search the owner's own documents by meaning | the honest base for a second brain |

Offline is not a feature. It is the difference between an assistant and a web
form. Cloud reasoning stays first, because it is better. Local must exist for the
day the network does not.

## What a cool Ultron must have

Capabilities are half of it. The other half is the feeling that it is present,
useful and safe. In the order that matters:

1. **It says what it can do, truthfully.** Done in 1.2.12: `tools_status` reads
   the real catalog, and the TOOLS tab shows every tool with its blocker.
2. **One command to undo the last thing.** The undo ledger exists. It should
   cover every write, including plugin writes, and it should be one sentence:
   "Undo that".
3. **A cost meter.** Tokens and money per day, a soft cap, and a spoken warning.
   An assistant that can spend without limit is not trusted for long.
4. **Offline mode that actually works.** Ollama plus faster-whisper plus Piper.
   A switch, not a config file.
5. **A second brain you can see.** A memory timeline: what it learned, from which
   conversation, editable, deletable. Memory the owner cannot inspect is memory
   he cannot trust.
6. **Project awareness.** "This folder, this task, this branch" as a first-class
   object, so "run the tests" means the right tests.
7. **Checkpoints for long tasks.** A plan with steps, each one resumable, each
   one visible. A five-minute task must survive a crash.
8. **Do-not-disturb awareness.** If a full-screen app or a call is running, it
   waits and says it waited. This is the "background must not disturb" promise,
   extended to time.
9. **A one-click plugin store.** Discover, verify, install, disable — with a
   signature or a hash in the listing. Twelve plugins exist; a store makes the
   next hundred possible without me writing each one.
10. **A health panel with a "prove it" button.** The proof gate exists on the
    command line. It belongs in the UI, with the same honesty: PARTIAL is not a
    pass.
11. **A wake word and a hard stop.** Both are asked for. Both must be physical:
    a key, or a phrase, always listening locally.
12. **A voice that shows emotion only when the content earns it.** Already the
    rule. It stays.

## What is honest about this list

- Tier A is one day's work per tool with tests, and I can do it without the
  tool installed by testing against a fake binary, the way `tests/test_bridges.py`
  does.
- Tier B and C need Node, or a big download, or an administrator prompt. They
  cannot be proven on this machine. They can be written so that absence is a
  sentence.
- The last four items of the "cool Ultron" list are projects, not features. Each
  is weeks. Saying so now is cheaper than a promise later.
