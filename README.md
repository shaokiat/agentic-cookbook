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
Check out [Architectures Guide](docs/architectures.md) for a deep dive into ReAct, Plan-and-Execute, and Reflexion patterns.

## 🛠️ Usage
Check the `examples/` directory for working implementation examples.
```bash
python examples/01_react_basic.py
```
