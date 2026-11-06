# Your system prompt

The instruction that shapes how Ultron behaves is **one text file** you own:

```
core/prompt.txt
```

It is not hidden in code, and it is not generated at runtime. What you read there is
what the model is given, with five placeholders filled in when a session starts:
your assistant's name, the operating system, the tools this build actually has, what
this build cannot do, and the current date and time.

---

## Three ways to read it

| Where | How |
|---|---|
| In the app, by voice or typing | *"Show me your system prompt."* |
| In a terminal | `python scripts/show_prompt.py` |
| In any editor | open `core/prompt.txt` |

`--template` prints the file exactly as it is, placeholders unfilled. `--check` runs
the rules an edit has to pass. `--history` shows every change ever applied.

---

## Telling Ultron to change it

Say what you want, in your own words:

> "From now on, keep your answers to two sentences unless I ask for detail."

Ultron stages the change and tells you plainly that **nothing has happened yet**.
You then confirm it **twice, in two different places** — say yes by voice, then click
confirm in the panel, or the other way round. Only the second confirmation writes
the file.

### Why twice

A model that can rewrite its own instruction in one step can also delete the
paragraphs that stop it doing something. Two acts, in two places, mean you have read
the change twice before it exists. This is the same rule the project already applies
to code: a human decides.

### What a change cannot do

These rules are checked before a change is even staged:

| Rule | Why |
|---|---|
| The placeholders must survive | `{limits}` deleted means the assistant stops knowing what it cannot do, and starts claiming it can |
| Under 19,000 characters | The build fails above 20,000 once the tool list is added |
| Not empty, not a stub | Under 2,000 characters is a description of a character, not an instruction |
| One exact passage at a time, or the whole file | An ambiguous "replace the" is refused rather than guessed |

### What a change cannot touch

Permissions, approval rules, which folders may be written, and which tools need a
confirmation live in **code**, not in this text. Editing the prompt changes how
Ultron talks and what it will attempt; it does not grant a single new permission.
That separation is deliberate: a prompt edit must never be a way around a gate.

---

## Going back

Every applied change keeps the text it replaced, in `config/prompt_versions/`, with a
changelog line naming the reason and where the two confirmations came from.

> "Which versions do you have?" → the list
> "Go back to the previous one." → staged, then confirmed twice, like any change

Nothing is deleted. If you want the history gone, delete that folder.

---

## Writing it by hand

You can edit `core/prompt.txt` in any editor. Two habits keep it working:

1. **Keep the five placeholders.** They are the difference between an assistant that
   knows its own limits and one that improvises.
2. **Keep it short.** Every tool already carries its own description, and the model
   reads all of them. A routing rule repeated here competes for attention with the
   rules written nowhere else — the ones about judgement, tone and untrusted content.

After a hand edit, run `python scripts/show_prompt.py --check`.
