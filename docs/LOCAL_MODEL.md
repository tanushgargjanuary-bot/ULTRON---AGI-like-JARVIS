# Running a local model

## Automatic local fallback

The application does not switch to a local model unless you explicitly approve it.
To enable this feature, add the following setting to `config/api_keys.json`:

```json
"local_fallback_consent": true
```

This consent allows a temporary fallback after the cloud quota is exhausted. The
fallback accepts only quantized chat models between 1.5B and 3B parameters. It reads
the quantization level from Ollama's model metadata. It refuses unquantized models,
models outside that size range, and embedding-only models. The saved cloud provider
configuration is not changed.

The fallback's HTTP client accepts literal loopback IP addresses only. It disables proxy
use and redirects, and it caps each JSON response at 2 MiB. It does not contact a LAN or
public model endpoint.

To disable the feature, remove the key or set it to `false`.

The same consent also allows automatic failover to another local provider you
configured (Ollama, LM Studio, llama.cpp, vLLM, Jan) when a hosted provider
fails. Without the flag, the failover ladder never moves the conversation onto
this machine by itself. Choosing a local model yourself is not a fallback and
does not need the flag.

Ultron already talks to a model on this machine. `core/llm_client.py` reads three keys from
`config/api_keys.json` and defaults to Ollama:

```
llm_provider   "ollama"                 or "openai" for LM Studio, Jan, llama.cpp
llm_url        "http://127.0.0.1:11434"
llm_model      "llama3.2"               the model name, exactly as the server lists it
```

Nothing else is needed. The missing part was knowing **which** model this machine can run,
and whether it answers. `scripts/local_model.py` answers that.

## Four commands

```powershell
python scripts\local_model.py          # what this machine can run, and what is installed
python scripts\local_model.py pull     # download the recommended model
python scripts\local_model.py test     # ask it one question and time the answer
python scripts\local_model.py bench    # three tiny jobs, timed, with a pass mark
python scripts\local_model.py write    # point the app at it, keeping a .bak copy
python scripts\local_model.py pull --model lfm2:1.2b
```

`bench` is the honest answer to "is this model worth using". Three jobs: answer one word, fix
one function, return one JSON object. It prints seconds and a pass mark for each. A model that
fails all three is a model that will waste an evening.

`check` writes nothing. `write` merges three keys and never deletes one you pasted, so a cloud
key survives a switch to a local model.

## If the command is not found

Three failures look the same and are not:

| What you see | What it means | Fix |
|---|---|---|
| `Python was not found; run without arguments to install from the Microsoft Store` | Windows is showing a placeholder, not a Python. | Install 3.11–3.13 from python.org and **tick "Add python.exe to PATH"**. Then close and reopen the terminal. |
| `can't open file ... No such file or directory` | The terminal is in the wrong folder. | `cd` into the repository first. `dir scripts\local_model.py` must list the file. |
| `No module named 'requests'` | The Python you called is not the one the application uses. | Use the folder's own Python: `.venv\Scripts\python.exe scripts\local_model.py check`. |

Two shortcuts that avoid the problem: the Windows launcher `py` instead of `python`, and
`cd` into the repository before any `python scripts\...` command.

Better still, name the folder's own interpreter, which always has the packages:

```powershell
.venv\Scripts\python.exe scripts\local_model.py check
```

Copy the command from a web page with care: a chat window can turn `local_model.py` into a
link, and pasting the link text gives `local_[model.py](http://model.py)` and an error that
says nothing about the real cause.

## Which model, and why that one

The script reads memory and the graphics card, then picks the smallest model that does the job:

| This machine | Model | Size on disk | Why |
|---|---|---|---|
| 4 GB or a phone | `lfm2:1.2b` | under 900 MB | Liquid AI's edge model. Runs on a processor at two to three times the speed of a transformer of the same size. |
| 8 GB | `llama3.2:3b` | about 2 GB | fine for chat and summaries, weak at code |
| 16 GB | `qwen2.5-coder:7b` | about 5 GB | the smallest model worth using for code edits |
| 32 GB | `qwen2.5-coder:14b` | about 9 GB | better judgement, still runs on a desktop |
| 32 GB and a big card | `qwen2.5-coder:32b` | about 20 GB | the strongest model that still runs at home |

LFM2 is the one to try first on a laptop that is already busy. It is small enough that the
model is not the thing that slows the machine down; the application is.

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

## One model at a time, and the memory it costs

- Ollama loads **one** model into memory and unloads it after a few minutes of no use. Two
  models on disk do not mean two models in memory.
- A loaded model costs its file size in memory: under 1 GB for LFM2 1.2B, about 5 GB for a 7B.
- Idle, a loaded model costs almost no processor time. It is a parked car, not a running one.
- The pressure comes from the **context**, not the weights: a long conversation costs more
  memory than the model does. LFM2 1.2B holds 32,000 tokens.

So one small model on a working laptop is not a strain. Three large ones at once would be,
which is why the tool never starts a second one.

## How this fits a bigger agent

A small local model is good at **doing one thing to one file**. It is not good at planning.
The split that works:

1. The bigger agent writes the task as one file, one instruction, and one test that fails.
2. The local model edits that one file.
3. The test decides. Not the model's opinion of its own work.

Without step 3 the loop produces confident wrong code. This repository's rule already says it:
a claim needs evidence.

## Related

- `docs/CAPABILITIES.md` — what else the machine can do, and what it cannot.
- `core/llm_client.py` — the client that reads the three keys.
