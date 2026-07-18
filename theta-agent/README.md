# theta-agent

A CLI tool that fetches stock research for a given ticker and suggests an options strategy via conversation with Claude.

Give it a ticker; it fetches price data, news, financials, and the options chain — then invites follow-up questions.

## Features

- Agentic research loop: Claude decides which tools to call and synthesises the results
- BSM Greeks (delta, gamma, theta, vega) computed per contract — pure Python, no C dependencies
- Per-ticker session memory: position and structured session history persist across runs
- Interactive REPL with slash commands: `/summary`, `/strategy`, `/position`, `/exit`
- JSONL session logs for every run

## Quickstart

```bash
git clone https://github.com/shaokiat/theta-agent.git
cd theta-agent
uv venv && uv pip install -e .
source .venv/bin/activate
cp .env.example .env  # add your ANTHROPIC_API_KEY
python theta.py AAPL
```

Requires Python ≥ 3.11 and a valid `ANTHROPIC_API_KEY`.

## Usage

```
python theta.py <TICKER>
```

At startup, theta-agent loads any stored position for the ticker and lets you keep, update, or clear it. The agent then runs the research phase (tool calls logged to `logs/`) and drops into an interactive chat with the full context in memory.

### Slash commands

| Command | Behaviour |
|---|---|
| `/summary` | One-paragraph recap of ticker, price, thesis, and recommended strategy |
| `/strategy` | Re-states the strategy in full standard format |
| `/position` | Re-states your declared position and how it interacts with the strategy |
| `/exit` | Saves state and exits (alias: `exit`, `quit`, `q`) |

## Tools

| Tool | Returns |
|---|---|
| `get_price_data` | Price, 52-wk range, P/E, beta, sector, 1-month return |
| `get_news` | Up to 10 recent headlines with title, publisher, summary |
| `get_financials` | Valuation ratios, margins, growth rates, balance sheet health, analyst consensus |
| `get_options_chain` | Top 5 calls + puts by OI within 10% of spot, IV, bid/ask, and BSM Greeks |

## Project structure

```
theta-agent/
├── theta.py              ← CLI entry point
├── theta/
│   ├── agent.py          ← ThetaAgent: research loop + chat REPL
│   ├── tools.py          ← tool implementations, schemas, dispatcher
│   ├── models.py         ← Pydantic models
│   ├── prompts.py        ← system prompt
│   ├── logger.py         ← JSONL session logger
│   └── state.py          ← per-ticker JSON state
├── docs/                 ← architecture and tool reference
├── tests/
└── pyproject.toml
```

## Disclaimer

This tool is for research and educational purposes only. Nothing it produces constitutes financial or investment advice.
