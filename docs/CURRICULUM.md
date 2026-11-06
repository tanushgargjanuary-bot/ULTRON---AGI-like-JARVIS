# The syllabus Ultron holds

> **The course is not here to be recited.** The topics that Ultron can actually do are
> wired into its own thinking, and each one names its course unit in the code. See
> [MENTAL.md](MENTAL.md) for what runs, and where.


Ultron carries your AKTU course. **8 subjects, 40 units, 284 topics, 42 reading links** — from the first lecture to the advanced paper, inside the assistant, with no internet needed to answer *"what is in unit 3 of DBMS?"*

## The plain version

Ask it like you would ask a classmate who has the syllabus open.

| You say | What it does |
|---|---|
| "What subjects do you know?" | All eight, with unit and topic counts |
| "Show me the DBMS syllabus." | Five units, the topics in each, and where the syllabus came from |
| "What is in DAA unit 2?" | The six topics of that unit, numbered |
| "Where do I start in DSTL?" | The first topic you have not marked done |
| "Give me the DAA plan." | The whole course in study order, numbered |
| "What should I read for deep learning, advanced?" | The reading for that level, with links |
| "Mark BCNF as done." | Records it — only because you said so |
| "Where does 'cache' come up?" | Every unit that mentions it |

## The eight subjects

| Short | Code | Subject | Units | Topics |
|---|---|---|---|---|
| DBMS | BCS501 | Database Management System | 5 | 48 |
| AI | BCAI501 | Artificial Intelligence | 5 | 33 |
| DAA | BCS503 | Design and Analysis of Algorithm | 5 | 37 |
| DS | BCS301 | Data Structure | 5 | 33 |
| AIML | BCAI601 | Machine Learning Techniques | 5 | 42 |
| DL | — | Deep Learning | 5 | 30 |
| DSTL | — | Discrete Structures and Theory of Logic | 5 | 32 |
| COA | BCS302 | Computer Organization and Architecture | 5 | 29 |

## Where each syllabus came from — and it says so in the app

This matters, because a syllabus that is quietly wrong is worse than none.

| Subject | Source |
|---|---|
| DBMS, AI, DAA, AIML | **Your PDF.** B.Tech CSE (AI & ML), NEP-2020, session 2024-25. The unit topics are yours, not a summary. |
| DS, DSTL, COA | Not in your PDF — those are earlier-year courses. Unit outlines come from the AKTU published outline. |
| DL | A standard curriculum. The university lists deep learning as an elective, and the field moves faster than a syllabus does. |

The text of each answer repeats the source. You can check any line against your own copy.

## The reading, in three levels

Every subject has links tagged **basics**, **intermediate** and **advanced** — a course page, a free book, or a practice site.

- **basics** — where a subject starts: MIT OCW lectures, *d2l.ai*, *SQLBolt*, *OpenDSA*, *nand2tetris*.
- **intermediate** — the real course: CMU 15-445 for databases, CS229 for machine learning, CS231n for vision, Princeton Algorithms.
- **advanced** — the field itself: the Red Book for databases, MIT 6.854 for algorithms, CS224n and Hugging Face for transformers, ETH's architecture course.

**Every one of the 42 links was opened and returned a page on 2026-11-06.** Three that failed were replaced rather than kept. The file records the date it was checked, so a dead link later is a known kind of debt, not a surprise.

## What is data and what is code

| Where | What |
|---|---|
| `curriculum/aktu_aiml.json` | the syllabus: subjects, units, topics, levels, links |
| `core/curriculum.py` | reading it, finding a subject by a spoken name, order, progress |
| `actions/curriculum.py` | the tool the model calls, and the sentences it says |
| `tests/test_curriculum.py` | 35 tests, including "his own phrases are still there" |

**The topics are in a data file, not in a Python literal.** A syllabus is a fact about your course. It belongs in a file you can open, correct, and diff — not in code that needs a programmer to fix a typo.

## Progress is opt-in

Nothing is recorded until you say a topic is done. What is stored is one list of topic keys in the settings file. "Reset" clears it. The syllabus itself is never changed by progress.

## Honest limits

1. **It does not teach by itself.** It says what the course contains, in what order, and where the good reading is. The teaching is the model's job, at the moment you ask.
2. **The order is the university's**, unit by unit. It does not claim to know a cleverer order than the people who wrote the course.
3. **The DL outline is my writing**, not AKTU's. If AKTU publishes a deep learning syllabus, it replaces that section and the file says so.
