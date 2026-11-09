# The ecosystem: what becomes part of Ultron, and what stays a name

A list of 200 projects arrived on 7 Nov 2026 with one question: build them in, or teach Ultron
to work with them?

**Neither, and the distinction is the whole answer.** Three tiers, one rule for choosing
between them.

## The rule

> If Ultron cannot do the job without it, and it must work offline, make it **native**.
> If it is already a program on the machine, make it an **adaptor**.
> If neither is true, it is **knowledge**: a name, a purpose, and a way to get it.

## The three tiers

| Tier | What it means | How many | Example |
|---|---|---|---|
| **Native** | Code inside this repository, imported, tested, shipped in the installer | Very few | the HUD, the voice loop, the OCR rung, memory |
| **Adaptor** | Ultron drives a program that is already installed, or its local API | About ten, ever | Ollama, ffmpeg, git, yt-dlp, Playwright, Everything |
| **Knowledge** | A catalogue entry: what it does, when to reach for it, its licence, its cost | Everything else | n8n, Milvus, CrewAI, LangGraph, Home Assistant |

A knowledge entry is not a lesser thing. Half of Ultron's usefulness is knowing that a tool
exists and when it is the wrong tool.

## Why not 200 native integrations

- **Startup and size.** Every native dependency is imported at launch or installed with the
  package. Ultron starts in seconds and must keep doing so.
- **Most of the list is a server, not a library.** n8n, Milvus, Kestra, Windmill, Uptime Kuma
  and Home Assistant are services with their own databases and ports. Shipping them inside a
  desktop assistant is shipping a data centre to a laptop.
- **Licence and update debt.** Each one needs a licence check, a version pin, a security
  watch, and a person to update it. Two hundred of those is a second job.
- **Surface area.** Every vendored project is a new way for the app to crash and a new place
  for a secret to leak. `find_files` already taught that lesson once (see `log.txt`).

## The one adaptor worth more than a hundred integrations

**MCP** — the Model Context Protocol. One client, and every MCP server on the machine becomes
a tool with a name, a schema and a permission boundary. That is the "teach Ultron to work with
them" answer at protocol level, and it is the only item on this page that changes the ceiling.

**Built.** `custom_jarvis/mcp_client.py`, one file, with the four rules written into it:

- **You choose and list the server; the app starts it.** `config/mcp_servers.json` holds a
  `command` and an `args` list. At application startup, each valid listed command is
  launched as a child process. Nothing is downloaded, fetched or installed.
- **Local process only.** An entry with a `url`, `host`, `port`, `socket` or `transport` is
  refused by name, with the reason — not ignored, and not quietly dialled.
- **Not an OS sandbox.** The child runs with the current user's permissions and
  inherits the app's process environment. It can access files, processes, network
  resources and environment variables available to that account. Environment variables
  may contain credentials. Configure only MCP programs and arguments you trust. The
  protocol's policy gate does not restrict the server process itself.
- **No shell.** A command with a space in it is refused and told to split itself into
  `command` + `args`. `shell=True` is not a shortcut; it is the door.
- **No exemption from policy.** A tool arrives as `mcp_<server>_<tool>`; `core/policy.py` has
  never seen that name, and its fail-closed default is `guarded` — **the owner is asked.**
  The client cannot classify its own tools. A test reads the source and fails if it tries.

The server's schema is translated once: supported lower-case JSON Schema types become
the upper-case form the provider accepts. Nested objects and arrays are preserved. Unknown
types, unions, references, combinators, unsupported constraints, invalid required names,
and invalid enums are refused rather than silently weakened. Schema depth, property count,
and protocol message size are bounded. A server that dies is one sentence, a server that
hangs times out, and closing the app closes the child's input so a well-behaved server exits
on its own.

What it does not do: install anything, connect to a remote MCP endpoint, run a command
through a shell, or approve its own tools. It does start the commands you configured, with
your operating-system permissions. Issue #10.

## The five that earn their place this quarter

1. **MCP client** — one adaptor, hundreds of tools, nothing vendored.
2. **OCR rung** — offline screen reading, already written on `antigravity` (issue #4).
3. **A file index** — SQLite FTS5, or Everything on Windows. Fast, and safer than walking the
   filesystem on every question.
4. **faster-whisper** — better offline speech recognition than the current path. One package.
5. **Piper or Kokoro** — a voice that never leaves the machine and costs nothing per sentence.

Five. Not two hundred. Each one has to survive the checklist below before it is sixth.

## A second list, measured against the code

A longer list arrived the same day, with its own priority shortlist. The instruction at the
end of it was the right one: *extract specific capabilities, integrate only where they solve a
measured weakness*. So each item was checked against this repository. A weakness counts only
if a file and a line can be shown.

| Measured weakness | Evidence | What fixes it | What does **not** |
|---|---|---|---|
| Memory has no time. Facts are stored, changes are not. | `memory/memory_manager.py` — six dictionaries (identity, preferences, projects, relationships, wishes, notes) with no timestamp and no history | date every write, keep the previous value, answer "what changed and when" | a graph database. One person's memory fits in SQLite |
| A plan does not survive a restart. | `custom_jarvis/planner.py` keeps `_resume_verified` in memory only; nothing writes plan state to disk. `core/crash.py` records the fall but does not resume it | write the step list and the confirmed steps to disk; on start, offer to continue | Temporal, Restate, DBOS, Hatchet, Inngest — all servers |
| The rehearsal is not isolated. | `plugin_forge.rehearse_in_sandbox` runs a child with the host environment in the project root, and trusts a printed sentinel | temp folder, scrubbed environment, no network, kill the tree, and judge by exit code plus a file diff | gVisor, Firecracker, youki, runc — Linux kernel features. A Windows desktop app cannot use them |
| Ultron cannot see the tools a person already runs. | no MCP client anywhere in the tree | one local MCP client, issue #10 | Composio — a cloud hub; it sends the work out, which is the one thing this app promises not to do |

And the reverse — things that look like gaps and are not:

- **A second agent framework** (LangGraph, AutoGen, CrewAI, MetaGPT, ADK, smolagents, pydantic-ai,
  openai-agents). `providers/engine_pipeline.py` and the action loader already are that runtime.
  A second one is two brains and one set of hands.
- **A second computer-use stack** (Cua, UI-TARS Desktop, Agent Desktop, Skyvern, Stagehand).
  `core/ui_ladder.py` already orders five rungs — tree, keyboard, OCR, vision, ask. Study the
  pattern; do not add the stack.
- **A second scoreboard** (Langfuse, MLflow, Opik, Phoenix, promptfoo, deepeval, ragas).
  `scripts/proof_gate.py` and `scripts/verify.py` are the scoreboard, and they run in CI.
- **A guardrail library** (guardrails-ai, rebuff, garak, ps-fuzz). The tiers in `core/policy.py`
  and the two-channel confirmation are the guardrail. Red-teaming is worth an hour of review,
  which is what the swarm did; it is not worth a shipped dependency.
- **A vector database** (Milvus, Qdrant, Weaviate, Chroma, LanceDB, pgvecto.rs, Neo4j, AGE).
  One user's files fit in SQLite with FTS5.

## The checklist, before anything becomes native

- [ ] Can Ultron do this job without it? If yes, it is knowledge.
- [ ] Does it work offline? If no, it is an adaptor at most.
- [ ] What does it weigh, in megabytes and in seconds at startup?
- [ ] Which licence, and does it allow shipping?
- [ ] Is there one test that fails when it breaks?
- [ ] Can it be removed again in one commit?

## What stays a name, always

Security scanners, OSINT tools, and scanners of other people's systems — Nuclei, Amass,
Sherlock, Subfinder, theHarvester, SpiderFoot. They are dual-use, they act on systems nobody
here owns, and a desktop assistant that ships them becomes a different product with a
different legal posture. They may appear in the catalogue. They do not ship in the installer.

## Related

- `docs/CAPABILITIES.md` — what the machine can do today.
- `docs/GITHUB_AWESOME_CATALOG.md` — the wider catalogue, on the `antigravity` branch.
- `core/tool_catalog.py` — the live list of tools Ultron can actually call.
