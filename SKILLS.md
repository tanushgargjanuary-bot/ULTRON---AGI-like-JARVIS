# Universal Agent Skills & Token Optimization Guide

> **Scope**: Mandatory for all AI coding agents working on Ultron (Antigravity, OpenCode, Claude Code, Cursor, Copilot, Cline, Aider).  
> **Core Objective**: Minimize token overhead, preserve context window capacity, eliminate cognitive fatigue, and maintain 100% technical and architectural rigor.

---

## Skill Index

| Skill | Name | Primary Function | Token Savings |
|---|---|---|---|
| **Skill 1** | [`caveman`](#skill-1-caveman-dense-token-saver-protocol) | Ultra-dense output, zero fluff, stripped conversational padding | **40% – 60%** |
| **Skill 2** | [`adhd`](#skill-2-adhd-high-focus--zero-wall-of-text-protocol) | Executive function aid, bite-sized chunking, 3-second scanability | **30% – 50%** |
| **Skill 3** | [`diff-minimalist`](#skill-3-diff-minimalist-surgical-patching) | Targeted replacements, zero unchanged code echoing | **50% – 80%** |
| **Skill 4** | [`context-compressor`](#skill-4-context-compressor--scratchpad-hygiene) | Log filtering, grep-first error extraction, context pruning | **60% – 90%** |
| **Skill 5** | [`chain-of-density`](#skill-5-chain-of-density-compact-reporting) | High semantic density, micro-tables, structured status tags | **30% – 45%** |

---

## Skill 1: Caveman (Dense Token-Saver Protocol)

### Philosophy
LLM tokens cost money, latency, and context budget. Conversational politeness ("Certainly!", "I would be happy to help with that!", "Here is what you requested:", "Please let me know if you need further clarification!") adds zero technical value. Caveman mode strips all filler while preserving 100% engineering precision.

### Rules of Engagement
1. **Zero Conversational Padding**:
   - ❌ NO: *"Sure thing! I have analyzed the issue and I am now ready to present the solution..."*
   - ✅ YES: Start immediately with the root cause, diff, command, or verdict.
2. **Terse, Punchy Prose**:
   - Drop passive voice, filler adverbs, and pleasantries.
   - Use short phrases: `Root cause: X. Fix: Y. Verify: Z.`
3. **Preserve Complete Engineering Integrity**:
   - Never shorten identifiers, types, function names, or file paths.
   - All code diffs must remain syntactically valid and strictly typed.
   - Keep line references and exact error tracebacks intact.

---

## Skill 2: ADHD (High-Focus & Zero-Wall-of-Text Protocol)

### Philosophy
Long, continuous paragraphs cause cognitive overload and hide critical details. Information must be structured for immediate 3-second visual scanning, clear visual hierarchy, and atomic task chunking.

### Rules of Engagement
1. **The Anti-Wall-of-Text Rule**:
   - Maximum 2 to 3 sentences per block.
   - Break complex ideas into distinct bullet points or numbered sequences.
2. **Front-Loaded Verdicts**:
   - Put the outcome, verdict, or critical finding on **Line 1**.
   - Structure follow-ups with high-contrast labels:
     - **Issue**: Exactly what failed (1 sentence).
     - **Fix**: Exactly what was changed (1 sentence + file link).
     - **Verify**: Exact command to test.
3. **Atomic Micro-Steps (Max 3–5 items)**:
   - Chunk tasks into small, verifiable stages. Finish stage 1 before presenting stage 2.
   - Prevent cognitive paralysis from sprawling 20-item checklists.
4. **Anti-Rabbit-Hole Boundary**:
   - Maintain strict focus on the active goal.
   - If an interesting but non-blocking anomaly is observed, isolate it in a 1-line **Side Quest** bullet at the very end instead of derailing the current task.

---

## Skill 3: Diff-Minimalist (Surgical Patching)

### Philosophy
Reprinting an entire 400-line file to show a 3-line change consumes thousands of prompt and completion tokens, slows down tool calls, and introduces hallucinated regressions in untouched sections.

### Rules of Engagement
1. **Targeted Replacements**:
   - Use surgical search-and-replace or unified diffs targeting only the relevant lines plus 2–3 lines of surrounding context.
   - Never echo unchanged methods or boilerplate.
2. **Symbol-First Referencing**:
   - Name the exact function, class, and line range: e.g. [`choose_wise_local_model`](file:///core/local_router.py#L26-L50).

---

## Skill 4: Context-Compressor & Scratchpad Hygiene

### Philosophy
Dumping thousands of lines of terminal output, test logs, or web scrapes into conversation context triggers rapid context blowout, high latency, and degradation of reasoning fidelity.

### Rules of Engagement
1. **Grep and Filter at the Shell**:
   - ❌ NO: `Get-Content large_log.txt` (floods 10,000 lines into context).
   - ✅ YES: `Select-String -Pattern "FAIL|ERROR" large_log.txt -Context 2,2` (returns only the 10 relevant lines).
2. **Scratch Files for Intermediate State**:
   - Write large outputs, dumps, and temporary test scripts to `scratch/` files or temporary directories.
   - Inspect only the summary statistics or specific failure lines in the conversation transcript.
3. **Do Not Parrot User Prompts**:
   - Never repeat the user's prompt back to them in your answer.

---

## Skill 5: Chain-of-Density (Compact Reporting)

### Philosophy
Pack maximum information density per token using structured visual constructs (Markdown tables, key-value maps, concise status tags).

### Rules of Engagement
- Prefer markdown tables for comparisons and metrics.
- Use compact status tags: `[PASS]`, `[FAIL]`, `[SKIP]`, `[WARN]`.
- Summarize multi-point achievements in a single structured list:
  ```markdown
  - **Memory Unicode Fix**: Reconfigured stdout/stderr to UTF-8 (`memory/memory_manager.py`).
  - **Path Safety**: Added user folder junctions to `_SAFE_ROOTS` (`actions/file_controller.py`).
  - **Ladder Latency**: Cached sidecar provider checks, dropping latency to 37 us (`core/gemini.py`).
  ```

---

## Multi-Agent Cross-Review Protocol (Antigravity & OpenCode)

When pair programming across branches (`antigravity` vs `opencode`):
1. **Zero Blame, Fact-Only Reviews**: Assess diffs purely against architectural invariants, threading rules (Qt widget safety), and test suites.
2. **Concise Review Artifacts**:
   - Format feedback as: `[SEVERITY] File:Line — Invariant breached — Proposed Fix`.
   - Keep reviews dense, actionable, and free of conversational padding.

