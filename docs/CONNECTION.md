# When it will not connect

A session that drops sends one close code. This page is what the codes mean, and the
mistake that made the owner re-enter a key that was never wrong.

## The short story

On 6 November 2026 Ultron would not stay connected on Windows. His activity log repeated:

```
SYS: Connection dropped — APIError: 1007 None. *[BidiGenerateContentRequest.setup
     .tools[0].function_declarations[40].parameters.required[0]: property is not
     defined*  Bid. Retrying in 6s.
ERR: API key invalid — please re-enter your key.
SYS: Initialised. OS=WINDOWS. Ultron online.
```

Two faults, one cause.

## Fault one: one field of one tool stopped everything

Every tool is described to the model by a small schema. A schema says: these are the
arguments, and these of them are **required**. The rule is one line long — a name may only
be required if it is also declared.

Five bridge plugins broke that rule. Each said *"action is required"* and then never
declared an `action`. The handler read the action out of the call, so the field worked
in code and was invisible in the schema.

Google does not ignore a schema it dislikes. It refuses the **whole list** and closes the
session with code 1007, naming the position: `function_declarations[40]`. Ultron retried,
resent the same list, and was refused the same way. Nothing about retrying could ever fix
it.

**Fixed:** every bridge now declares `action`, with the values it accepts.

**Guarded:** `core/action_loader.py` has a repair pass that runs on every start. A name
that is required but not declared is dropped, a property with no type is given one, and
each repair is printed and written to the activity log. A bad field now costs one
argument, not the whole evening.

## Fault two: the number was read as an answer

The reconnect loop tested:

```python
if "API key not valid" in err_str or "1007" in err_str:
```

1007 is the Live API's general-purpose close. It covers a bad key, a bad model name and a
malformed tool list alike. The condition made any 1007 open the re-key panel, so the
assistant asked for a key over and over while the real fault was a schema.

**Fixed:** `core/close_codes.py` reads the message, not the number. It answers one of six
things — schema, key, quota, model, network, other — and quotes the message when it does
not recognise it. A rejected tool list now says so, and says which tool, using the index
the server gave.

The owner's key was never the problem. It did not need to be re-entered, and it does not
need to be re-entered now.

## The rule that keeps this closed

Every declaration in `actions/`, `plugins/` and `main.py` is checked at test time and in
the proof gate: **no `required` name without a declared property, and no property type the
provider does not know**. One bad plugin used to cost the whole session, and a check that
lives in a test costs nothing at start.

| Where | What it does |
|---|---|
| `core/action_loader.py` | `sanitize_declarations()` — repairs a bad list and reports each repair |
| `core/close_codes.py` | reads a close message and names the fault; a code alone never decides |
| `tests/test_provider_schema.py` | 18 tests over every declaration the model is given |
| `scripts/proof_gate.py` | the `plugins` claim now proves "the provider accepts the list" |
