# Running a local model

Ultron already talks to a model on this machine. `core/llm_client.py` reads three keys from
`config/api_keys.json` and defaults to Ollama:

```
llm_provider   "ollama"                 or "openai" for LM Studio, Jan, llama.cpp
llm_url        "http://localhost:11434"
llm_model      "llama3.2"               the model name, exactly as the server lists it
```

Nothing else is needed. The missing part was knowing **which** model this machine can run,
and whether it answers. `scripts/local_model.py` answers that.

## Four commands

```powershell
python scripts\local_model.py          # what this machine can run, and what is installed
python scripts\local_model.py pull     # download the recommended model
python scripts\local_model.py test     # ask it one question and time the answer
python scripts\local_model.py write    # point the app at it, keeping a .bak copy
```

`check` writes nothing. `write` merges three keys and never deletes one you pasted, so a cloud
key survives a switch to a local model.

## Which model, and why that one

The script reads memory and the graphics card, then picks the smallest model that does the job:

| This machine | Model | Why |
|---|---|---|
| 8 GB or less | `llama3.2:3b` | fast, fine for chat and summaries |
| 16 GB | `qwen2.5-coder:7b` | the smallest model worth using for code edits |
| 32 GB | `qwen2.5-coder:14b` | better judgement, still runs on a desktop |
| 32 GB and a big card | `qwen2.5-coder:32b` | the strongest model that still runs at home |

Graphics memory counts, because a model that fits on the card runs ten to fifty times faster.

## What a local model is good for

- Chat, summaries, rewriting, naming, translation.
- Code edits on one file, where you can read the result in ten seconds.
- Anything private: no text leaves the machine.

## What it is not good for

- Planning a change across twenty files. Small models lose the thread and invent file names.
- Tools. Tool calling needs a model trained for it, and a small model often calls the wrong
  tool with great confidence.
- Speed on a machine with no graphics card: a 7B model answers at a few words a second, and
  a long answer takes minutes.

Speed is measured, not guessed: `python scripts/local_model.py test` prints the seconds.

## Related

- `docs/CAPABILITIES.md` — what else the machine can do, and what it cannot.
- `core/llm_client.py` — the client that reads the three keys.
