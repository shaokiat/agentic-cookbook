# theta-agent

A CLI tool that fetches stock research for a given ticker and suggests an options strategy via conversation with Claude. Give it a ticker; it returns a research summary and invites follow-up questions.

**Primary reference:** [`docs/OVERVIEW.md`](docs/OVERVIEW.md) — architecture, increment plan, tool catalogue, strategy framework, and extension guide.

**Current version:** v0.5 (implemented)
**Next:** v0.6 — Extract tool functions to `tools/` directory; move system prompt to `prompts/system.md`

---

## Maintenance rule

**After any code change or new feature, update this file to reflect the current state.** Keep the component map, module descriptions, and increment plan in sync with the actual code. `docs/OVERVIEW.md` is the deep reference; this file is the quick-start operative guide — it should always be accurate enough to orient a new session without reading the source.

---

## How to run

```bash
cd theta-agent
uv venv && uv pip install -e .
source .venv/bin/activate
export ANTHROPIC_API_KEY=sk-ant-...
python theta.py AAPL
```

At startup, theta-agent loads `state/<TICKER>.json` (if it exists), shows the stored position, and lets the user keep, update, or clear it. On exit the session summary and updated position are written back to that file. Leave the position blank to skip.

## Component map

```
theta-agent/
├── theta.py              ← CLI entry point: loads state, prompts for position, runs agent
├── theta/
│   ├── agent.py          ← ThetaAgent: run_research() + chat_loop(); saves state on exit
│   ├── tools.py          ← tool functions + TOOLS schemas + process_tool_call() dispatcher
│   ├── models.py         ← Pydantic models (PriceData, NewsItem, OptionsChain, Financials)
│   ├── prompts.py        ← SYSTEM_PROMPT constant
│   ├── logger.py         ← JSONL session logger (raw API traces → logs/)
│   └── state.py          ← per-ticker JSON state: load(), save(), prior_context()
├── state/                ← auto-created; one JSON file per ticker (position + session history)
├── logs/                 ← auto-created; one JSONL file per session (raw API traces)
├── tools/                ← one file per tool from v0.6 (not yet created)
└── prompts/              ← system.md from v0.6 (not yet created)
```

## Session flow

1. `theta.py` loads `state/<TICKER>.json`, shows stored position, prompts to keep/update/clear
2. `ThetaAgent.run_research()` builds the initial prompt with position context and last 3 session summaries injected, runs the tool-use loop, returns `(summary, full_messages)`
3. `ThetaAgent.chat_loop()` starts an interactive REPL with the full research history in context
4. On exit (`exit`, `quit`, `q`, `/exit`, or Ctrl-C), saves position + session summary to `state/<TICKER>.json`

## Slash commands (v0.5+)

| Command | Behaviour |
|---|---|
| `/summary` | One-paragraph recap of thesis, key data, and recommended strategy |
| `/strategy` | Re-states current strategy in full standard format |
| `/position` | Re-states the user's declared position and how it interacts with the strategy |
| `/exit` | Saves state and exits (alias for `exit`, `quit`, `q`) |

## Tools in v0.5

| Tool | Returns |
|---|---|
| `get_price_data(ticker)` | Current price, 52-wk high/low, P/E, beta, 1-month return, sector via yfinance |
| `get_news(ticker)` | Up to 10 recent headlines with title, publisher, and summary via yfinance `.news` |
| `get_financials(ticker)` | Valuation ratios, profitability margins, YoY growth, balance sheet health, free cash flow, analyst consensus via yfinance |
| `get_options_chain(ticker)` | Top 5 calls + puts by OI within 10% of spot, IV, bid/ask, delta, gamma, theta, vega for expiry ~30 days out |

## How to add a tool

1. Write the function in `theta/tools.py`
2. Add its JSON schema to `TOOLS` in the same file
3. Add a branch to `_DISPATCH` in the same file
4. Update `SYSTEM_PROMPT` in `theta/prompts.py` if Claude needs guidance on the new data
5. That's it — the agentic loop picks it up automatically

## Increment plan

- **v0.2** — Add `get_options_chain`: near-the-money strikes, OI, IV by expiry (yfinance)
- **v0.3** — Add Greeks to options chain (delta, gamma, theta, vega via py_vollib_vectorized)
- **v0.4** — Add `get_financials`: valuation ratios, margins, growth rates, analyst consensus via yfinance
- **[backlog]** — `get_sec_filing`: 10-K/10-Q/8-K via EDGAR (deferred — parsing complexity outweighs value)
- **[backlog]** — Deep financial analysis: cross-reference valuation, growth, margins, analyst consensus, and options data into a structured comparative breakdown; prompt engineering not started yet
- **[backlog]** — Prompt/instruction evaluation: verify the system prompt effectively uses richer context (Greeks, financial metrics) as versions accumulate — approaches: LLM-as-judge scoring against a rubric, golden-set regression on saved ticker snapshots, and ablation testing to confirm new context blocks are actually used by Claude
- **v0.5** — Full conversation memory in chat loop; `/summary`, `/strategy`, `/position` slash commands; position context at startup
- **v0.6** — Extract tool functions to `tools/` directory; move system prompt to `prompts/system.md`
- **v0.7** — MCP integration: Brave Search for richer news
- **v0.8** — Add `get_ibkr_positions`: read live account positions from IBKR Client Portal Web API; context-aware strategy suggestions against existing holdings
- **v1.0** — Error handling, caching, structured `analyses/` output, polished README
