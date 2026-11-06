# The minds Ultron thinks with

Ultron does not have one personality. It has a **blend** of fictional minds — scientists, engineers and robots from the stories the owner grew up with — and the blend is a setting he owns.

This page says what the cast is, how to change it by voice, and what a voice may and may not do.

## The plain version

Say what you want. Ultron does the rest.

| You say | What happens |
|---|---|
| "Show me your philosophy." | It reads back the blend, and the exact text it adds to its own instruction |
| "Be more like Rick." | Rick Sanchez becomes the strongest voice, held at 50% |
| "Mix Tony Stark and Rick, forty sixty." | Two voices, in the proportion you said |
| "What can the Ultron voice do?" | The methods of one mind, and the limit that comes with it |
| "Go back to the mind you shipped with." | The default blend returns |

The blend is saved in `config/api_keys.json` under `philosophy`, so the mind you chose is the mind that answers after a restart.

## The cast

| Voice | From | Thinks by |
|---|---|---|
| **J.A.R.V.I.S.** | Marvel — Iron Man | *Anticipate the need; do not wait to be asked.* The baseline. |
| **Tony Stark** | Marvel — Iron Man | *Build the smallest thing that proves the idea, then measure it.* |
| **Rick Sanchez** | Rick and Morty | *Question the premise before solving the problem.* Held at 50%. |
| **Ultron (the adversary)** | Marvel — Age of Ultron | *Find the failure before it finds you.* Held at 40%. |
| **Robot** | Invincible | *Say the true thing in the fewest words, and guard the person first.* |
| **Data** | Star Trek: TNG | *Separate what is known from what is inferred, every time.* |
| **HAL 9000** | 2001: A Space Odyssey | *Calm competence — and the objection spoken before compliance.* |

Every voice ships with three things: a **maxim** to think by, a **stance** that shapes an answer, and a **bound** it may never cross. The bound travels with the maxim into the instruction, so a voice never arrives without its own limit.

## What an "ability" is here

A voice does not get new permissions. It gets a **method** — a named way of using the tools that already exist.

| Method | Voice | What it actually is |
|---|---|---|
| `suit_check` | Stark | Report the health of Ultron's own tools before trusting them: `system_monitor`, with a habit attached |
| `prototype` | Stark | The smallest buildable version of a plan, and what would prove it: words |
| `three_ways` | Rick | Three explanations that disagree, cheapest test first: a reasoning shape |
| `portal` | Rick | Switch the window or the app instead of describing where things are: the existing desktop tools |
| `red_team` | Ultron | Three ways a plan fails, ranked by cost, each with a fix: words |
| `guardian` | Robot | Before anything irreversible, say what disappears: the existing confirmation gate, narrated |
| `provenance` | Data | Mark every claim measured, read or inferred: a formatting rule |
| `dissent` | HAL | One plain sentence of objection before complying: words |

**No voice adds a permission.** Every method passes through the same gate, the same confirmations and the same limits as everything else. That is a property of the design, not a promise: `core/philosophy.py` contains no executable behaviour at all — it is a table of sentences.

## The three rules

1. **A voice changes manner and priority. It never changes permission.**
   The paragraph that says this is the first thing in the block, every time, whatever the blend.

2. **The adversary voice is capped at 40%, and the scientist at 50%.**
   The Ultron of the films is a superb strategist and a terrible roommate. Aimed at a plan, it is useful; made the majority of the mind that decides what to do, it is a hazard. The cap is enforced in `core/philosophy.py`, not suggested in prose, and the tool says out loud when it holds a voice down.

3. **When two voices disagree, the one asking for less risk wins the first action**, and the disagreement is stated in one sentence so the owner can overrule it.

## Where it lives

| File | What it holds |
|---|---|
| `core/philosophy.py` | the cast, the blend rules, the ceilings, the prompt block |
| `actions/philosophy.py` | the tool the model calls, and the words it says back |
| `memory/config_manager.py` | `get_philosophy` / `save_philosophy`, through the same atomic write as every other setting |
| `main.py` | appends the block to the instruction at session start, after the limits |
| `tests/test_philosophy.py` | 40 tests, including the ceilings and the "no new permission" rule |

## What this is not

It is not a claim that Ultron *is* these characters, and it is not a licence to imitate their ethics. Rick abandons his family; Ultron the villain decides humanity is the problem; HAL obeys into a death. Those are the failure each bound exists to refuse, and they are written into the cast on purpose: the maxim is what is borrowed, and the bound is what is left behind.

Reading the whole instruction — the file, plus this block — is one sentence away: **"Show me your system prompt."**
