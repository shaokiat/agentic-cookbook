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

---

## How production systems approach memory

### File structure: flat vs. layered

This cookbook uses a single `memory_store.md` for all facts. Both production systems split memory across multiple files with distinct semantics and distinct owners.

**OpenClaw** injects two files: `MEMORY.md` (project-level facts the agent has learned) and `CLAUDE.md` (workspace instructions authored by the human). The separation exists because these two files have different change rates and different authors — mixing them makes it impossible to distinguish human-set rules from agent-discovered facts. `CLAUDE.md` is the human's channel to the agent; `MEMORY.md` is the agent's channel to its future self.

**Nanobot** goes further with three files: `MEMORY.md` (facts), `USER.md` (user profile — name, preferences, expertise), and `SOUL.md` (agent personality and identity). The rationale is that these three categories have different staleness rates and should be updated independently. `SOUL.md` rarely changes; `MEMORY.md` updates frequently; `USER.md` updates when the user reveals new preferences. Each file is managed by the **Dream** processor separately, which makes the layering practical rather than cosmetic.

The cookbook's flat file is the right starting point. The layered structure becomes necessary when human instructions and agent-learned facts need different access controls, or when facts with different lifetimes would otherwise dilute each other.

### Memory updates: append-only vs. surgical editing

`save_fact()` in this cookbook appends a bullet to the file. Nothing is ever updated or removed — facts accumulate forever.

**OpenClaw** also appends, but `MEMORY.md` is reviewed and pruned manually. There is no automated staleness detection. The agent writes facts; humans curate them.

**Nanobot**'s Dream processor makes surgical edits rather than rewrites. Phase 1 is a plain LLM call that analyses unprocessed `history.jsonl` entries and produces a change plan. Phase 2 runs a full `AgentRunner` with `read_file`/`edit_file` tools to apply targeted edits. Each update is a git-committable diff, not a full rewrite. Before Phase 1, each line in `MEMORY.md` is annotated with its age in days via `git blame` (e.g., `← 30d`), giving the LLM the information it needs to identify and remove stale facts.

The append-only approach is simple and safe but accumulates noise. Surgical editing with staleness detection is the production-grade solution — it is more complex but produces memory that stays accurate over time rather than growing indefinitely.

### Retrieval: inject everything vs. retrieve on demand

`01_markdown_persistence.py` injects all facts into every session's system prompt. This is O(n) context cost — as facts grow, so does every prompt.

`02_hybrid_search.py` retrieves only the top-k relevant facts per query: O(k) context cost regardless of total store size. This is the key scaling difference between intermediate and long-term memory.

**OpenClaw** core uses static injection (`MEMORY.md` and `CLAUDE.md` are always present). Retrieval-augmented memory is available via a community extension (supermemory) rather than core. The constraint is simplicity — for a coding agent working in one project, the number of relevant facts is small enough that full injection is fine.

**Nanobot** pairs static injection (the three markdown files are always present) with on-demand retrieval from `history.jsonl` via the Dream processor. The static files contain distilled, curated facts; `history.jsonl` contains the raw session record. This two-layer approach means the always-injected content stays small while the full history remains queryable.
