# mini-researcher

A simplified port of gpt-researcher: query -> plan sub-questions -> parallel search/scrape/compress -> synthesize a cited report.

**Primary reference:** `README.md` — quickstart, usage, project structure. `docs/ARCHITECTURE.md` — design decisions and tradeoffs (why a fixed pipeline not ReAct, why threads not asyncio, why compression is stateless, why no LangChain, etc.). `research/gpt-researcher-architecture.md` (in the repo root, gitignored/local) has the full architecture trace of the *original* gpt-researcher this was derived from.

**Current version:** v1 (core loop complete)

---

## How to run

mini-researcher is a subdirectory of the `agentic-cookbook` monorepo, with its own `pyproject.toml` and virtualenv (independent of the root project's and of `agents/theta-agent`'s).

```bash
cd agents/mini-researcher
uv venv && uv pip install -e .
source .venv/bin/activate
export ANTHROPIC_API_KEY=sk-ant-...   # or OPENAI_API_KEY, matching DEFAULT_MODEL

python researcher.py "your research query"
```

## Component map

```
mini-researcher/
├── researcher.py            ← CLI entry point: argparse, load_dotenv, ResearchPipeline.run()
├── researcher/
│   ├── config.py             ← Config: model, embedding_model, search_provider, chunk_size, top_k_chunks (env-driven)
│   ├── llm.py                 ← LLM: litellm.completion()/embedding() wrapper with cumulative Usage tracking
│   ├── prompts.py               ← load(name, **kwargs): reads prompts/*.md, .format()s in kwargs
│   ├── planner.py                 ← generate_sub_queries(): one LLM call, JSON parse with regex + raw-query fallback chain
│   ├── search.py                   ← SearchProvider protocol, DuckDuckGoProvider (ddgs package), get_search_provider() factory
│   ├── scraper.py                   ← scrape(url): requests + BeautifulSoup, returns None on any failure (never raises)
│   ├── compress.py                   ← chunk_text() (paragraph-packing), filter_relevant_chunks() (BM25 0.3 + cosine-sim 0.7, stateless)
│   ├── worker.py                       ← run_subquery_worker(): search -> scrape -> chunk -> compress for one sub-query, isolated by try/except
│   ├── pipeline.py                      ← ResearchPipeline: fan-out via ThreadPoolExecutor, joins contexts, synthesis call, abstention guard
│   └── report.py                         ← Report dataclass, to_markdown()
├── prompts/
│   ├── planner.md                         ← sub-query generation system prompt (JSON array output)
│   └── synthesis.md                        ← report-writing system prompt (abstention guard instruction lives here)
```

## Data flow

1. `researcher.py` parses CLI args, builds `Config`, instantiates `ResearchPipeline`
2. `ResearchPipeline.run(query)`:
   a. `generate_sub_queries()` — one LLM call, query -> list of sub-questions
   b. `_fan_out()` — `ThreadPoolExecutor`, one `run_subquery_worker()` per sub-question, results collected via `as_completed` and re-ordered by index
   c. Each worker: `search_provider.search()` -> for each result, `scrape()` -> `chunk_text()` -> `filter_relevant_chunks()` -> join into a context string tagged with source URLs
   d. Contexts from all workers joined, `_synthesize()` — one LLM call, query + context -> markdown report (or an explicit "not enough information" if context is empty)
3. `Report` returned with `.usage` (cumulative cost/tokens across every LLM call in the run) and `.timing`

## Design notes worth preserving

- **No conversational memory** — each `ResearchPipeline.run()` call is single-shot, matching gpt-researcher's own `GPTResearcher` instance model. Don't add session persistence without a clear reason; it wasn't in scope for the port.
- **Failure isolation is layered on purpose**: `scrape()` never raises (returns `None`), `run_subquery_worker()` never raises (empty-string fallback), and `_fan_out()`'s `future.result()` is still wrapped in try/except as a third layer. Keep all three when touching this code — a single bad URL or sub-query must never crash the whole run.
- **Compression is stateless by design** — unlike `HybridMemoryStore` (the pattern this was adapted from), `filter_relevant_chunks()` doesn't persist embeddings; each call embeds its own batch and discards it. Don't reintroduce a persistent store unless there's a real cross-run caching need.
- **ThreadPoolExecutor, not asyncio** — deliberate choice; see `README.md`'s "How it differs from gpt-researcher" and `research/gpt-researcher-architecture.md` for the reasoning (sync blocking I/O throughout, asyncio would add dependency/design overhead for no benefit at this scale).

## How to add a search provider

1. Add a class in `researcher/search.py` implementing `SearchProvider.search(query, n) -> list[SearchResult]`
2. Add a branch for it in `get_search_provider()`
3. Set `SEARCH_PROVIDER=<name>` in `.env`
4. No changes needed in `worker.py`/`pipeline.py`

## Increment plan

- **v1 (done)** — Planner, `ThreadPoolExecutor` fan-out, BM25+vector compression, synthesis with abstention guard, cost tracking, per-URL/per-worker error isolation, README/CLAUDE.md.
- **v1.1 (done)** — Optional `on_event` progress callback (`ResearchPipeline(config, on_event=...)`, threaded through `run_subquery_worker`). Dict events: `planning_done`, `subquery_start`, `searched`, `scraped`, `subquery_done`, `synthesizing`, `done`. Callback failures are swallowed (`_emit`) so the failure-isolation layers are untouched. Consumed by the cookbook's Streamlit UI (`ui/pages/p90_mini_researcher.py`) via a thread-safe queue.
- **[backlog]** — Second search provider (e.g. Tavily) to prove the abstraction holds without redesign.
- **[backlog]** — Source curation pass (optional LLM re-rank after compression) — explicitly deferred during the v1 scoping decision, not essential.
- **[backlog]** — Subtopic/detailed report mode (per-section synthesis + merge) — explicitly out of scope for the minimal port; only add if there's a concrete teaching reason to demonstrate section-parallel synthesis.
- **[backlog]** — Tests (`pytest`, listed as an optional dependency but no test suite written yet).
