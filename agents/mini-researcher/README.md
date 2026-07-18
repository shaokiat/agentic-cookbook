# mini-researcher

A simplified port of [gpt-researcher](https://github.com/assafelovic/gpt-researcher): give it a query, it plans sub-questions, researches them in parallel, and synthesizes a cited report.

Built as a case study in composing several agentic patterns from this repo's `examples/` into one real pipeline: Plan-and-Execute (Level 2), parallel fan-out/fan-in (Level 5), and context compression via relevance filtering (Level 3). See `research/gpt-researcher-architecture.md` for the full architecture trace this was derived from.

**For the reasoning behind every structural choice below (why a fixed pipeline instead of a ReAct agent, why threads instead of asyncio, why compression is stateless, why there's no LangChain, etc.), see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).**

## Features

- Planner: one LLM call turns a query into 2-4 independent sub-questions (with a defensive JSON-parse fallback chain)
- Parallel research: each sub-question is searched, scraped, and compressed concurrently via `ThreadPoolExecutor` (~3x speedup over sequential on a 3-query run)
- Context compression: scraped pages are chunked and filtered to the most relevant chunks via a BM25 + embedding-similarity hybrid (adapted from `examples/02_memory_management/02_hybrid_search.py`'s `HybridMemoryStore`, made stateless)
- Synthesis: one final LLM call over the aggregated compressed context, with an explicit abstention guard — if there's no relevant context, it says so instead of hallucinating
- Cost/token tracking printed after every run
- Per-URL and per-sub-query failure isolation: a dead link or a failed search never kills the run

## Quickstart

mini-researcher lives inside the [agentic-cookbook](../../) monorepo's `agents/` directory as a standalone example, with its own dependencies and virtualenv.

```bash
git clone https://github.com/shaokiat/agentic-cookbook.git
cd agentic-cookbook/agents/mini-researcher
uv venv && uv pip install -e .
source .venv/bin/activate
cp .env.example .env  # add your ANTHROPIC_API_KEY or OPENAI_API_KEY
python researcher.py "What is the current state of solid-state batteries?"
```

Requires Python ≥ 3.11 and a valid LLM provider API key (any [litellm](https://docs.litellm.ai/docs/providers)-supported provider). No search API key required — the default search provider is DuckDuckGo.

## Usage

```
python researcher.py "<query>" [--sub-queries N] [--top-k N] [--model provider/model]
```

| Flag | Default | Meaning |
|---|---|---|
| `--sub-queries` | 4 | Max number of sub-questions the planner generates |
| `--top-k` | 5 | Chunks kept per sub-query after compression |
| `--model` | `$DEFAULT_MODEL` | Override the LLM used for planning, synthesis, and embeddings |

## Project structure

```
mini-researcher/
├── researcher.py            ← CLI entry point
├── researcher/
│   ├── config.py             ← env-driven config (model, search provider, chunk size, top_k)
│   ├── planner.py             ← generate_sub_queries(): one LLM call + JSON fallback chain
│   ├── search.py               ← SearchProvider protocol + DuckDuckGoProvider
│   ├── scraper.py                ← scrape(): requests + BeautifulSoup, isolated failure handling
│   ├── compress.py                ← chunk_text() + filter_relevant_chunks() (BM25 + vector hybrid)
│   ├── worker.py                   ← run_subquery_worker(): search -> scrape -> compress for one sub-query
│   ├── pipeline.py                  ← ResearchPipeline: ThreadPoolExecutor fan-out + synthesis + cost tracking
│   ├── report.py                     ← Report dataclass + markdown formatting
│   ├── prompts.py                     ← loads prompts/*.md
│   └── llm.py                          ← litellm wrapper with cumulative cost tracking
├── prompts/
│   ├── planner.md
│   └── synthesis.md
├── docs/
│   └── ARCHITECTURE.md              ← design decisions and tradeoffs
└── pyproject.toml
```

## How it differs from gpt-researcher

This is a scoped-down core loop, not a feature port. Deliberately skipped: MCP integration, image generation, multi-agent "team" mode, detailed/subtopic report merging with section-by-section synthesis, vector-store report sources, websocket streaming to a frontend, an optional LLM-based source-curation pass, and the original's 18-provider retriever matrix / 8-backend scraper matrix (this has one of each). See `research/gpt-researcher-architecture.md`'s "Scope Recommendation for a Minimal Port" section for the full reasoning.

## How to add a search provider

1. Add a class in `researcher/search.py` implementing `SearchProvider`'s `search(query, n) -> list[SearchResult]`
2. Add a branch for it in `get_search_provider()`
3. Set `SEARCH_PROVIDER=<name>` in `.env`

No changes needed to `worker.py` or `pipeline.py`.

## Disclaimer

This tool is for research and educational purposes only. It synthesizes web content via an LLM and can still be wrong — verify anything load-bearing against primary sources.
