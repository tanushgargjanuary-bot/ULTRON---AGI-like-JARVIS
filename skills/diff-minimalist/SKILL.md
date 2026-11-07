---
name: diff-minimalist
description: Surgical code editing skill. Eliminates token bloat by strictly replacing only the target lines of code, preventing hallucinated regressions and reducing completion tokens by up to 80%.
---

# Diff-Minimalist: Surgical Code Editing Protocol

## Purpose
Prevent conversational bloat, eliminate hallucinated regressions in unchanged code, and optimize completion token usage during code modifications.

## Rules
1. **Targeted Replacements**:
   - Only edit the exact block of code being changed, with 2–3 lines of context.
   - Never reprint unchanged functions, classes, or boilerplate.
2. **Explicit Symbol Linking**:
   - Provide direct file and line range links: `[function_name](file:///path/to/file.py#L10-L25)`.
3. **No Redundant Commentary**:
   - Let clean diffs explain themselves; do not explain line-by-line what the diff already shows.
