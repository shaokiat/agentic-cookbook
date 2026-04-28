# Long-term Memory: Hybrid Search (BM25 + Vector)

## What it is

Long-term memory is a searchable archive of past observations, facts, and conversation history that the agent can query on demand. Unlike intermediate memory (which injects everything into the system prompt), long-term memory only surfaces what's *relevant* to the current query — keeping context usage bounded regardless of how many facts have been accumulated.

This is the pattern Open Claw implements in `history.py`.

## The problem with static injection

Intermediate memory injects the entire fact store into every session's system prompt:

```
[system]: You are a helpful assistant.
--- Recalled from previous sessions ---
- Alice is a researcher...
- Bob is a software engineer...
- The team's language is Python...
- ... (all 500 facts)
```

This works for dozens of facts. It breaks at hundreds because:
- Token cost grows linearly with the number of stored facts
- The model's attention dilutes across irrelevant context
- Eventually you hit the context limit

## The retrieval pattern

Instead, store facts in an indexed store and retrieve by relevance:

```
Session start:  system prompt is clean (no facts injected)
                │
User query:     agent calls recall("what does Alice work on?")
                │
Retrieval:      hybrid search → top-3 relevant facts fetched
                │
Context:        only 3 facts added to context, not 500
```

## Why hybrid (BM25 + vector)?

Neither retrieval method works well alone:

| Method | Strength | Weakness |
|:-------|:---------|:---------|
| BM25 (keyword) | Exact matches — names, IDs, URLs, code | Misses semantic paraphrasing |
| Vector (cosine) | Semantic matches — concepts, synonyms | Misses exact tokens |
| Hybrid | Both | Slightly more complex to implement |

Example: the query *"deployment infrastructure"* should match the fact *"GitHub Actions for CI/CD"* and *"PostgreSQL on AWS RDS"*. Vector catches the semantic link; BM25 catches "AWS" if the query mentions it literally.

Open Claw weights: **30% BM25 + 70% vector**.

## Implementation

```python
class HybridMemoryStore:
    def add(self, text: str) -> None:
        embedding = self._embed(text)          # call embedding API once
        self.entries.append({
            "text": text,
            "embedding": embedding,
        })
        self._save()                            # persist to JSON

    def search(self, query: str, top_k: int = 3) -> list[str]:
        # BM25 — tokenize and score
        bm25 = BM25Okapi([e["text"].lower().split() for e in self.entries])
        bm25_scores = bm25.get_scores(query.lower().split())
        bm25_scores /= bm25_scores.max() or 1  # normalize to [0, 1]

        # Vector — cosine similarity
        query_emb = np.array(self._embed(query))
        stored_embs = np.array([e["embedding"] for e in self.entries])
        vector_scores = (stored_embs @ query_emb) / (
            np.linalg.norm(stored_embs, axis=1) * np.linalg.norm(query_emb)
        )

        # Combine
        combined = 0.3 * bm25_scores + 0.7 * vector_scores
        top_indices = np.argsort(combined)[::-1][:top_k]
        return [self.entries[i]["text"] for i in top_indices]
```

Two tools are exposed to the agent:
- `remember(fact)` — indexes a fact (embed + save to disk)
- `recall(query)` — retrieves top-k relevant facts by hybrid score

## Trade-offs vs other memory tiers

| | Intermediate (markdown) | **Long-term (hybrid search)** |
|---|---|---|
| Survives restart | Yes | Yes |
| Scales to | Dozens of facts | Thousands of facts |
| Context cost | O(n) — all facts injected | O(k) — only top-k retrieved |
| Retrieval quality | Perfect (everything present) | Good (top-k may miss edge cases) |
| Embedding cost | None | 1 API call per `add`, 1 per `recall` |
| Complexity | Low | Medium |

## Running the example

Install the additional dependencies first:

```bash
uv add rank-bm25 numpy
```

Then run:

```bash
python examples/02_memory_management/02_hybrid_search.py
```

The example runs three sessions:
1. **Session 1**: Agent indexes 10 facts into the store via `remember()`
2. **Session 2**: New agent reloads the store from disk, calls `recall("Alice")` — retrieves only the 2 Alice-related facts out of 10
3. **Session 3**: Same store, different query — demonstrates BM25 catching infrastructure keywords

The per-query score breakdown is printed showing `bm25=` and `vec=` contributions for each result.

## In Open Claw

The core Open Claw source (`research/claw-code-agent/src/history.py`) is a **simple in-memory session event log** — `HistoryLog` with `HistoryEvent(title, detail)` dataclass entries. It does not contain BM25 or vector search.

The hybrid retrieval pattern in this example is implemented by a community extension — [supermemory/openclaw-supermemory](https://github.com/supermemoryai/openclaw-supermemory) — which extracts Open Claw's conversation history and indexes it with BM25 + vector search. The 30/70 weight split is from that extension, not core Open Claw.

This example is an accurate illustration of *how* long-term retrieval can be layered on top of an agent loop. Core Open Claw relies on `CLAUDE.md` injection (static) for persistent memory; retrieval is left to extensions.

See [`docs/openclaw_memory_architecture.md`](../../docs/openclaw_memory_architecture.md) for the full breakdown of what Open Claw actually implements.
