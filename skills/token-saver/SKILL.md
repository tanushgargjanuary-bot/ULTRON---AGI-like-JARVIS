---
name: token-saver
description: Advanced token-budget optimization skill. Preserves LLM context window and reduces inference latency by pruning log noise, preventing prompt echo, and leveraging dense markdown constructs.
---

# Token-Saver: Advanced LLM Context Optimization

## Purpose
Preserve context window capacity, minimize inference costs, and reduce turn latency across long agent sessions.

## Rules
1. **Shell Output Filtering**:
   - Never pipe unbounded output (`cat`, `Get-Content`) into context.
   - Filter with `grep`, `Select-String`, `-Head`, or `-Tail` to capture only actionable error lines or summaries.
2. **Scratchpad Offloading**:
   - Large intermediate artifacts belong in temporary files (`scratch/`), not in conversational context.
   - Only return summary metrics or findings.
3. **No Prompt Echo**:
   - Never repeat the user's question, prompt, or instructions in the response.
4. **Information Packing**:
   - Use compact Markdown tables and key-value summaries over verbose narrative paragraphs.
   - Use standard status indicators: `[PASS]`, `[FAIL]`, `[SKIP]`.
