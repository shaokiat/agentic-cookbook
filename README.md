# 🍳 agentic-cookbook

A hands-on library of agent architectures, design patterns, and tool-use techniques — barebones implementations you can read end to end, plus real agents built on top of them.

## 🎯 Objectives

- **Educational**: Understand tool-calling, memory, and feedback loops without heavy abstractions.
- **Pattern library**: A curated, working reference for agent architectures — ReAct, Plan-and-Execute, multi-agent orchestration, memory pipelines, tool-use patterns — each with a minimal implementation and a walkthrough.
- **Applied**: `agents/` turns those patterns into real, self-contained agents solving specific problems.

## 🏗️ Core Architecture

- **Agent Loop**: Sequential ReAct-style loop.
- **Tool Registry**: Dynamic schema generation from Python functions.
- **Model Abstraction**: Multi-provider support via `LiteLLM`.
- **Memory**: Simple list-based message history.

## 📖 Concepts

Each category below is a directory of runnable examples in `examples/`, each with a short walkthrough `.md` next to its `.py` file. Full detail — including how each pattern maps to production systems like Claude Code, OpenClaw, and Nanobot — lives in [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).

| Category | Directory | Covers |
| :--- | :--- | :--- |
| Primitives | `examples/00_primitives/` | Tool use, the context window as working memory, stop conditions |
| Agent Loop Patterns | `examples/01_agent_patterns/` | ReAct, Plan-and-Execute, Reflexion |
| Memory Management | `examples/02_memory_management/` | Context governance, intermediate memory, skills, consolidation pipelines |
| Multi-Agent Systems | `examples/03_multi_agent_systems/` | Orchestrator/worker, message bus, async announce, per-session concurrency |
| Tool Use Patterns | `examples/04_tool_use_patterns/` | Parallel tool calls, tool policy pipeline, error recovery |
| Evaluation & Monitoring | `examples/05_evaluation_and_monitoring/` | Tracing, structured logging, task-level evaluation |
| Frameworks | `examples/06_frameworks/` | Reading production frameworks (pi-agent/pi-mono) once you recognize the patterns |
| Inference & Serving | `examples/07_inference/` | Self-hosting: TTFT vs ITL, continuous batching, the concurrency knee |

## 🤖 Agent Examples

Beyond the pattern library, `agents/` hosts standalone agents built on these patterns — each a self-contained project with its own dependencies and virtualenv:

- [`agents/theta-agent/`](agents/theta-agent/) — LangGraph multi-strategy options screener (conditional routing, human-in-the-loop `interrupt()`, Chainlit UI).
- [`agents/mini-researcher/`](agents/mini-researcher/) — simplified [gpt-researcher](https://github.com/assafelovic/gpt-researcher) port: plan → parallel search/scrape/compress → synthesize, composing Plan-and-Execute, multi-agent fan-out, and context compression into one pipeline.
- [`agents/text-to-sql/`](agents/text-to-sql/) — natural-language-to-SQL CLI over any SQLite/Postgres/MySQL database: schema-grounded prompt ablation (baseline → schema → docs → hints), a read-only guard as the real safety boundary, and one bounded repair-on-failure turn.

## 📚 Documentation

- [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) — motivation, the Level 1–8 concept ladder, and the map from each example to its production counterpart.
- [docs/llm_provider_strategies.md](docs/llm_provider_strategies.md) — who owns the translation layer between your agent and a provider.
- [docs/inference_serving.md](docs/inference_serving.md) — the layer below that: KV cache, PagedAttention, continuous batching, and why throughput and latency are the same dial.
- [docs/reference_architectures.md](docs/reference_architectures.md) — how the reference implementations are put together.

## 🛠️ Usage

Check the `examples/` directory for working implementation examples.

```bash
python examples/01_react_basic.py
```

### Web UI

Every example (and mini-researcher) has an interactive demo page with a model picker and per-agent knobs:

```bash
streamlit run ui/app.py
```

Chat-style pages keep the agent and its memory in the session; demo pages stream the agent's events (tool calls, observations, approvals) as they happen.

## ⚡ Self-Hosted Inference

Run an open-weight model yourself and point the whole cookbook at it — no code changes, just env vars:

```bash
make serve-vllm      # vllm-metal on Apple Silicon (or serve-mlx / serve-ollama)
make probe           # which engine is live, and what it has loaded
```

```bash
# .env — one local endpoint; all three engines serve on it, one at a time
LOCAL_API_BASE=http://localhost:8000/v1
HOSTED_VLLM_API_BASE=http://localhost:8000/v1   # for the sidebar model picker
```

[`deploy/vllm/`](deploy/vllm/) covers local serving and GCP deployment (Cloud Run first, GKE second). [`examples/07_inference/`](examples/07_inference/) measures what you get — TTFT, decode rate, and the concurrency knee where continuous batching stops helping.

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- OpenAI or Anthropic API Key

### Installation

#### Option 1: Using `uv` (Recommended)

`uv` is an extremely fast Python package manager.

```bash
# Install dependencies
uv pip install -e .

# Or run directly if using uv project management (if applicable)
# uv run some_example.py
```

### Setup

1. Copy `.env.example` to `.env`:

   ```bash
   cp .env.example .env
   ```

2. Add your API keys to the `.env` file.
