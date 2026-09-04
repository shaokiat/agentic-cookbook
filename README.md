# 🦀 agentic-cookbook

A barebones implementation of agentic architectures dedicated to demystifying how recursive agent loops work. Inspired by **Claude Code** and **Open Claw**.

## 🎯 Objectives
- **Educational**: Understand tool-calling, memory, and feedback loops without heavy abstractions.
- **Prototyping**: Minimalist playground for testing agentic concepts.
- **Documentation**: A curated guide to modern agentic architectures.

## 🏗️ Core Architecture
- **Agent Loop**: Sequential ReAct-style loop.
- **Tool Registry**: Dynamic schema generation from Python functions.
- **Model Abstraction**: Multi-provider support via `LiteLLM`.
- **Memory**: Simple list-based message history.

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

## 🤖 Agent Examples
Beyond the concept-ladder examples, `agents/` hosts standalone agents built on these patterns — each a self-contained project with its own dependencies and virtualenv:
- [`agents/theta-agent/`](agents/theta-agent/) — LangGraph multi-strategy options screener (conditional routing, human-in-the-loop `interrupt()`, Chainlit UI).
- [`agents/mini-researcher/`](agents/mini-researcher/) — simplified [gpt-researcher](https://github.com/assafelovic/gpt-researcher) port: plan → parallel search/scrape/compress → synthesize, composing Plan-and-Execute, multi-agent fan-out, and context compression into one pipeline.
