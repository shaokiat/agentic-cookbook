# 02 Memory Management

Agents need memory at three different timescales. This section covers persistence strategies — how information survives beyond a single context window. For the mechanics of *managing* the context window itself (sliding window, auto-compact, token budgeting), see [`00_primitives/02_context_window`](../00_primitives/02_context_window.md).

## The Three Tiers

| Tier | Survives restart | Scales to | Context cost | Example here |
| :--- | :--- | :--- | :--- | :--- |
| Short-term (context window) | No | ~200K tokens | O(history) | → see `00_primitives/02_context_window` |
| Intermediate (file injection) | Yes | Dozens of facts | O(n) — all injected | `01_markdown_persistence.py` |
| Long-term (hybrid retrieval) | Yes | Thousands of facts | O(k) — top-k only | `02_hybrid_search.py` |

## Examples

| File | Concept |
| :--- | :--- |
| [`01_markdown_persistence.py`](./01_markdown_persistence.py) | Intermediate memory — write facts to a markdown file, inject into system prompt at session start ([guide](./01_markdown_persistence.md)) |
| [`02_hybrid_search.py`](./02_hybrid_search.py) | Long-term memory — BM25 + vector hybrid retrieval, only top-k relevant facts fetched per query ([guide](./02_hybrid_search.md)) |

## Open Claw reference

For a complete mapping of these patterns to actual Open Claw source files (with concrete before/after examples), see [`docs/openclaw_memory_architecture.md`](../../docs/openclaw_memory_architecture.md).

## Core Concepts

1. **Intermediate Memory**: Durable facts written to markdown files — survives restarts, human-readable, git-diffable. Works well for small, always-relevant context (user preferences, project goals). Breaks at scale.

2. **Long-term Memory (Hybrid Retrieval)**: Index facts by both keyword (BM25) and semantic embedding (vector). At query time, retrieve only what's relevant. This is how Open Claw's `history.py` works — 30% BM25 + 70% vector, combined score.

3. **Semantic / Episodic Memory** *(planned)*: Summarize completed sessions into structured notes. Retrieve relevant past episodes by topic rather than raw facts.
