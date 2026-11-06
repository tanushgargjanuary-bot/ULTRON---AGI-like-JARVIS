# Architecture — read this before you change anything

One page, in the order a change travels: what the layers are, where each kind of
addition belongs, and which test refuses a mistake. `docs/MAP.md` is the generated
module-by-module version of this; `docs/INDEX.md` lists every document.

## The six layers

| # | Layer | Folder | Answers | May not |
|---|---|---|---|---|
| 1 | **Host** | `main.py`, `ui.py`, `dashboard/` | what the user sees and says | contain logic the other layers own |
| 2 | **Providers** | `providers/` | how a model is spoken to | know about tools or memory |
| 3 | **Safety** | `core/policy.py`, `core/custom_gate.py`, `core/evidence*` | whether an act is allowed, and what proves it happened | be bypassed by any other layer |
| 4 | **Capability** | `actions/`, `plugins/`, `core/bridges.py`, `core/webapi.py` | one tool, one job | decide its own risk tier |
| 5 | **Judgement** | `custom_jarvis/` | plan, verify, remember, decide, learn | act without the registry |
| 6 | **State** | `memory/`, `custom_jarvis/settings.py`, `core/paths.py` | what survives a restart | hold a secret in a prompt |

**The rule that keeps this honest:** layer 5 asks layer 3 for permission, and
layer 3 never asks layer 5 who the user is. Safety is not a feature of the
planner; it is the thing the planner runs through.

## One turn, end to end

```
microphone or text
   → providers/  (model, streamed)
   → tool call named by the model
   → core/tool_catalog.py    is this a real tool?
   → core/policy.py          which tier, and does it need a human?
   → ControlledRegistry      workspace confinement, backups, evidence
   → the tool                a plugin, a bridge, an action, or a custom tool
   → EvidenceEngine          did it actually happen? read it back
   → custom_jarvis/metacog   record the claim, its confidence, its outcome
   → spoken reply            core/tts or the configured provider
```

Every arrow is a file you can open. Nothing happens "inside the model".

## Where a change belongs

| You want to add | Edit | Then |
|---|---|---|
| a local, keyless utility | `plugins/<name>.py` with a `PLUGIN` dict | add the name to `core/policy.py` and a test |
| a public read-only data source | `core/webapi.py` does the transport; add a small module like `core/github.py` | a plugin that speaks sentences, and a fake-opener test |
| an external application | `core/bridges.py` (probe + one bounded call) | a `_bridge.py` plugin, and the risk table |
| a recipe over existing tools | `custom_jarvis/skills.py` | a test that it is listed and its steps run |
| a recipe Ultron writes itself | a **skill pack** (JSON in `<state>/skills/`) | `custom_jarvis/skillpacks.py` validates it; no code change |
| a new custom tool | `custom_jarvis/*_tools.py`, `register_*` | a test through `CustomService`, and its tier |
| a decision rule | `custom_jarvis/decision.py` | one arithmetic rule used by everything |
| a migration of stored data | `custom_jarvis/knowledge.py` | a migration check in `scripts/verify.py` |

## The invariants, and what enforces each

| Invariant | Enforced by |
|---|---|
| A tool cannot escape the workspace | `addon_runtime.PATH_ARGUMENTS` + `prepare_args`, tested per tool |
| A tool has a risk tier, or it asks | `tests/test_policy_new_tools.py` |
| A promise in a docstring needs a file | `scripts/proof_gate.py` (`NOT PRESENT` is a verdict) |
| Confidence is a lower bound, never a ratio | `custom_jarvis/metacog.py`, `tests/test_metacog.py`, gate claim `metacognition` |
| A decision can refuse | `custom_jarvis/decision.py`, gate claim `decisions` |
| A skill Ultron writes cannot write | `custom_jarvis/skillpacks.py` allow-list, gate claim `self_extension` |
| A token never leaves one header | `core/github.py`, `tests/test_web_platforms.py`, gate claim `github` |
| Interruption is earned, not scheduled | `custom_jarvis/schedule.py`, gate claim `reminders` |
| A secret never reaches a commit | `custom_jarvis/ship.py:scan`, gate claim `shipping` |
| A push is fast-forward only, never forced | `custom_jarvis/ship.py:push`, gate claim `shipping` |
| A version that does not parse is put back | `custom_jarvis/selfupdate.py:apply`, gate claim `self_update` |
| Nothing flashes a console window | gate claim `console`, `tests/test_*` |
| Every module has a docstring and a test | `python scripts/map.py` (exit 1 on a new gap) |

## Data on disk

| Path | What | Bounded |
|---|---|---|
| `<state>/knowledge.sqlite3` | capability counters, procedures, budget usage | yes |
| `<state>/metacog.json` | predictions, lessons, strategy attempts | 500 / 300 / 200 |
| `<state>/skills/*.json` | skill packs Ultron wrote | 8 steps each |
| `<state>/reminders.json` | what was shown, and when | one entry per card |
| `<state>/web_cache.json` | ETags and bodies for the four platforms | 400 entries |
| `<state>/github_watch.json` | the repositories and languages being watched | 10 + 5 |
| `memory/long_term.json` | what the **user** approved | approval-gated |
| `<state>/ship_log.json` | the last 100 shipping attempts, with the stage that refused | 100 |
| `<state>/ship_pending.json` | self-evolutions waiting to be shipped | 50 |
| `<state>/restart-required.json` | written only when a pull changed a `.py` file | one file |
| `config/api_keys.json` | keys and tokens, including `github_token` and `ship_auto` | never logged |

## The three rules that survive every refactor

1. **Measure, then claim.** A number in a document must come from
   `scripts/verify.py` or `scripts/proof_gate.py`, or it does not go in.
2. **Silence is a decision.** A refusal, an empty recall, an unshown reminder and
   a `SKIP` in the gate are all correct answers. Rounding them up to a pass is the
   one defect this project keeps finding, because it is the easiest one to make.
3. **Code that nothing calls is a liability.** It looks like progress, it rots,
   and it lies in the map. If an algorithm has no caller, it waits in
   `ALGORITHMS.md` until the feature that needs it exists.

## Reading order for a newcomer

1. `readme.md` — what the product is, and what changed last.
2. `ARCHITECTURE.md` — this page.
3. `docs/MAP.md` — the modules, generated.
4. `DECISIONS.md` — what the owner decided, and where it is enforced.
5. `GATEKEEPERS.md` — what is proven, and what is not.
6. `HANDOFF.md` — how the last build was made and what it cost.
