# How a skill gets used

The owner asked this, and it was the right question to ask:

> they need a condition to get triggered, otherwise ULTRON will never use them. Is this
> solved already?

The honest answer was **no**. Three things have to be true before a feature is used,
and only the first one was true.

## 1. The tool exists

Every file in `actions/` that carries a tool description is found at start-up. A tool
that cannot load is listed with the reason, on screen and in the log, instead of
disappearing. This part was already solved, and the proof gate checks it.

## 2. The model is told when to use it

This was broken. The system instruction lists the tools, but it cut each description at
150 characters. On this build **10 of 32 tools had the sentence that says when to use
them past that cut** — including `reasoning`, `curriculum`, `philosophy`,
`self_modify` and `recall_memory`. The ability was there. The reason to use it was not.

It is fixed like this: each line now leads with the condition.

```
- reasoning: Use it before any multi-step task: 'plan' the steps, then take them in that order. — …
- curriculum: Use this tool whenever the user asks about their syllabus … — …
```

The condition is taken from the tool's own text, never written a second time, so a tool
cannot be described in one place and triggered from another. Twelve tools had no
condition at all and now have one plain sentence each.

## 3. Something counts the calls

A condition in the instruction is a hope. Nothing could tell "the user never needed it"
apart from "the model never once thought of it", because nothing counted.

Now every approved call is counted, with the date, in the settings file. Ask Ultron
**"what can you do"** and the answer ends with which tools have never been called:

> 12 of 32 tools have been called. Most used: web_search (40), reminder (7).
> Never called (20): flight_finder, game_updater, … A tool in this list has a
> description the model has not found a reason to use.

That sentence is the trigger audit. It is how a dead feature is found by using the
assistant, not by reading it.

## What to do about a tool that is never called

In this order, cheapest first:

1. **Read its condition.** If it describes the tool instead of the moment, rewrite that
   one sentence.
2. **Ask it the exact question** the condition describes, for example "search the web
   for today's price of gold". If it fires, the condition is right and the tool is
   simply rare.
3. **Check its price.** A guarded tool waits for a confirmation, so it is reached for
   less often. That is a decision, not a fault.

## What this does not do

It does not make the model call a tool. It makes the reason visible when it does not,
which is the part that can be fixed. A trigger that fires in a test and never in a
conversation is not a trigger, and the count is how the difference shows up.

## The cost

The tool block stayed at 4,736 characters for 32 tools, the same as before, because the
line is 150 characters either way and the condition took the front of it. The whole
instruction is 22,320 characters — measured, and held under a ceiling by a test that
uses the real tool set rather than the ten inline ones.
