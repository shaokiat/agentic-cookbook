# theta-agent

A CLI tool that fetches stock research for a given ticker and suggests an options strategy via conversation with Claude. Give it a ticker; it returns a research summary and invites follow-up questions.

**Primary reference:** [`docs/OVERVIEW.md`](docs/OVERVIEW.md) — architecture, increment plan, tool catalogue, strategy framework, and extension guide.

**Current version:** v0.9 (implemented)
**Next:** v0.8 (backlog) or v1.0 — see increment plan

---

## Maintenance rule

**After any code change or new feature, update this file to reflect the current state.** Keep the component map, module descriptions, and increment plan in sync with the actual code. `docs/OVERVIEW.md` is the deep reference; this file is the quick-start operative guide — it should always be accurate enough to orient a new session without reading the source.

---

## How to run

theta-agent is a subdirectory of the `agentic-cookbook` monorepo, with its own `pyproject.toml` and virtualenv (independent of the root project's).

```bash
cd theta-agent
uv venv && uv pip install -e .
source .venv/bin/activate
export ANTHROPIC_API_KEY=sk-ant-...
export BRAVE_API_KEY=...        # optional — enables search_web tool

# CLI (unchanged)
python theta.py AAPL

# Textual TUI (v0.9)
python theta_ui.py AAPL
```

At startup, theta-agent loads `state/<TICKER>.json` (if it exists), shows the stored position, and lets the user keep, update, or clear it. On exit the session summary and updated position are written back to that file. Leave the position blank to skip.

The TUI shows the same position prompt as a modal dialog, then runs research in the left panel (40%) and chat in the right panel (60%). A status bar at the bottom shows live tool call progress.

## Component map

```
theta-agent/
├── theta.py              ← CLI entry point: loads state, prompts for position, runs agent
├── theta_ui.py           ← Textual TUI entry point: same agent, split-pane UI (v0.9)
├── theta/
│   ├── agent.py          ← ThetaAgent: run_research() + send_message() + chat_loop(); on_output/on_tool_call/on_status callbacks
│   ├── tools.py          ← thin shim re-exporting from tools/ package
│   ├── models.py         ← Pydantic models (PriceData, NewsItem, EarningsDates, OptionsChain, IVSurface, Financials)
│   ├── prompts.py        ← loads SYSTEM_PROMPT from prompts/system.md
│   ├── logger.py         ← JSONL session logger (raw API traces → logs/)
│   └── state.py          ← per-ticker JSON state: load(), save(), prior_context()
├── tools/                ← one file per tool; __init__.py assembles TOOLS + dispatcher
│   ├── __init__.py       ← TOOLS list, process_tool_call()
│   ├── price.py          ← get_price_data + SCHEMA
│   ├── news.py           ← get_news + SCHEMA
│   ├── options.py        ← get_options_chain: multi-expiry, OLS IV surface, iv_excess, earnings_count + SCHEMA
│   ├── financials.py     ← get_financials + SCHEMA
│   ├── earnings.py       ← get_earnings_dates: 3-tier yfinance fallback + SCHEMA
│   └── search.py         ← search_web (Brave Search REST API) + SCHEMA
├── prompts/
│   └── system.md         ← SYSTEM_PROMPT — edit here without touching Python
├── state/                ← auto-created; one JSON file per ticker (position + session history)
└── logs/                 ← auto-created; one JSONL file per session (raw API traces)
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
| `/scorecard` | Re-prints the full 5-signal scorecard from the research phase |
| `/strategy` | Re-states current strategy in full standard format including "Why not" and Sensitivity |
| `/position` | Re-states the user's declared position and how it interacts with the strategy |
| `/exit` | Saves state and exits (alias for `exit`, `quit`, `q`) |

## Tools in v0.7

| Tool | Returns |
|---|---|
| `get_price_data(ticker)` | Current price, 52-wk high/low, P/E, beta, 1-month return, sector via yfinance |
| `get_news(ticker)` | Up to 10 recent headlines with title, publisher, and summary via yfinance `.news` |
| `get_financials(ticker)` | Valuation ratios, profitability margins, YoY growth, balance sheet health, free cash flow, analyst consensus via yfinance |
| `get_options_chain(ticker)` | 3 nearest expiries (≥14 days), strikes ±15% of spot, BSM greeks, OLS IV surface (`iv_excess`, `r_squared`), `earnings_count` per expiry, sorted by `iv_excess` desc |
| `get_earnings_dates(ticker)` | Up to 4 upcoming earnings dates with `days_until`; 3-tier yfinance fallback; empty list for ETFs/no-earnings tickers |
| `search_web(query, count?)` | Web search via Brave Search REST API — requires `BRAVE_API_KEY` |

## How to add a tool

1. Create a new file in `tools/` (e.g. `tools/my_tool.py`) with the function and a `SCHEMA` dict
2. Import and register it in `tools/__init__.py`: add to `TOOLS` and `_DISPATCH`
3. Update `prompts/system.md` if Claude needs guidance on the new data
4. That's it — the agentic loop picks it up automatically

## Increment plan

- **v0.2** — Add `get_options_chain`: near-the-money strikes, OI, IV by expiry (yfinance)
- **v0.3** — Add Greeks to options chain (delta, gamma, theta, vega via py_vollib_vectorized)
- **v0.4** — Add `get_financials`: valuation ratios, margins, growth rates, analyst consensus via yfinance
- **[backlog]** — `get_sec_filing`: 10-K/10-Q/8-K via EDGAR (deferred — parsing complexity outweighs value)
- **[backlog]** — Deep financial analysis: cross-reference valuation, growth, margins, analyst consensus, and options data into a structured comparative breakdown; prompt engineering not started yet
- **[backlog]** — Prompt/instruction evaluation: verify the system prompt effectively uses richer context (Greeks, financial metrics) as versions accumulate — approaches: LLM-as-judge scoring against a rubric, golden-set regression on saved ticker snapshots, and ablation testing to confirm new context blocks are actually used by Claude
- **v0.5** — Full conversation memory in chat loop; `/summary`, `/strategy`, `/position` slash commands; position context at startup
- **v0.6** — `tools/` directory (one file per tool); `prompts/system.md`; native `search_web` tool (Brave Search REST API)
- **v0.7** — Signal Scorecard framework: `get_earnings_dates` tool; `get_options_chain` extended to multi-expiry + OLS IV surface (`iv_excess`, `r_squared`) + `earnings_count` annotation; 5-signal scorecard (Directional, IV Regime, Event Risk, Conviction, Liquidity) with For/Against/Confidence fields; `/scorecard` slash command; `max_tokens` raised to 4096
- **v0.8** — Add `get_ibkr_positions`: read live account positions from IBKR Client Portal Web API; context-aware strategy suggestions against existing holdings
- **v0.9** — Textual TUI: split-pane terminal UI (`theta_ui.py`); left panel = scrollable research + scorecard output; right panel = chat history + input bar; status bar shows live tool call progress; agent callbacks replace `print()`/`input()` so CLI (`theta.py`) continues to work unchanged
- **v1.0** — Error handling, caching, structured `analyses/` output, polished README
