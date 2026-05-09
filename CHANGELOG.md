# Changelog

All notable changes to theta-agent are documented here.

## [Unreleased]

### Planned — v0.6
- Extract tool functions to `tools/` directory
- Move system prompt to `prompts/system.md`

---

## [0.5.0] — Conversation memory and slash commands

### Added
- Full `messages[]` history (including raw tool results) carried forward from `run_research()` into `chat_loop()` — Claude retains complete context across both phases
- `/summary` — one-paragraph recap of ticker, price, directional thesis, key data, and recommended strategy
- `/strategy` — re-states the recommended strategy in the standard format (STRATEGY / OUTLOOK / TRADE / MAX PROFIT / MAX LOSS / BREAKEVEN / RATIONALE)
- `/position` — re-states the user's declared position and how it interacts with the recommended strategy
- `/exit` — alias for `exit`, `quit`, `q`; triggers state save before quitting
- Per-ticker JSON state persistence (`state/<TICKER>.json`) — stores current position and up to 10 structured session records
- `state.py` — `load()`, `save()`, `prior_context()` helpers; `prior_context()` formats the last 3 sessions as a prompt-injection block for continuity across runs
- Startup position flow — loads stored position, prompts user to keep, update, or clear it before research begins
- Structured session extraction — after each session, Claude is asked to distil a JSON record (price, bias, strategy, trade details, IV environment, key themes, thesis) for compact state storage
- `SessionLogger` in `theta/logger.py` — writes JSONL session logs to `logs/` (auto-created)

---

## [0.4.0] — Financial metrics

### Added
- `get_financials(ticker)` — fetches fundamental metrics from yfinance in four groups:
  - **Valuation:** trailing P/E, forward P/E, P/B, P/S, EV/EBITDA
  - **Profitability:** gross, operating, and net margins; ROE; ROA
  - **Growth:** YoY revenue growth, YoY earnings growth
  - **Balance sheet:** debt/equity, current ratio, quick ratio
  - **Cash flow:** free cash flow, EBITDA
  - **Dividends:** yield, payout ratio
  - **Analyst consensus:** mean target price, recommendation key, analyst count
- System prompt updated: Claude instructed to call `get_financials` in the research phase and to use valuation, growth, balance sheet health, and analyst consensus to qualify or challenge the options thesis
- `max_tokens` in `run_research()` raised from 1024 → 2048 to accommodate richer context

### Tests added (`TestGetFinancials`)
- Field mapping from yfinance info to model
- `None` fields excluded from output (`exclude_none=True`)
- Ticker symbol uppercased regardless of input case
- yfinance exception returns `{"error": ...}` rather than raising
- `get_financials` reachable via `process_tool_call` dispatcher

### Notes
- SEC filing tool (`get_sec_filing`) moved to backlog; EDGAR parsing complexity outweighs marginal value over yfinance metrics

---

## [0.3.0] — Greeks

### Added
- BSM Greeks (delta, gamma, theta, vega) computed per contract in `get_options_chain`
  - Implemented in pure Python using `math.erf` — no additional C dependencies
  - Theta expressed as per-calendar-day decay; vega expressed per 1% change in IV
  - Greeks omitted for contracts where IV is unavailable (NaN)
- `OptionContract` model extended with optional `delta`, `gamma`, `theta`, `vega` fields
- System prompt updated with guidance on interpreting each Greek: delta for directional exposure, theta for daily decay cost, vega for IV sensitivity, gamma for rate-of-change near expiry

### Tests added (`TestGreeks`)
- Greeks present on call and put contracts
- Call delta positive, put delta negative
- ATM call delta in (0.4, 0.6)
- Theta negative for both calls and puts
- Vega positive for both calls and puts
- Contracts with NaN IV have no Greek fields in output

### Notes
- `py_vollib_vectorized` (originally planned) replaced with a pure-Python BSM implementation to avoid C build dependencies; results are equivalent for European-style options

---

## [0.2.0] — Options chain

### Added
- `get_options_chain(ticker)` — fetches the nearest expiry ≥ 14 days out; returns top 5 calls and puts by open interest, filtered to strikes within 10% of spot; includes IV, bid/ask, volume, OI per contract
- `atm_iv` field in options chain output for quick IV environment assessment
- System prompt updated with IV/OI reasoning guidance and ATM vs OTM strike selection logic
- IV environment thresholds documented in OVERVIEW.md (low IV proxy < 0.30, high IV proxy > 0.50)

### Notes
- Greeks not yet included; planned for v0.3 via `py_vollib_vectorized`

---

## [0.1.0] — Initial release

### Added
- `theta.py` CLI entry point — validates ticker and `ANTHROPIC_API_KEY`, instantiates `ThetaAgent`
- `ThetaAgent` in `theta/agent.py` with two-phase execution:
  - **Phase 1** `run_research()` — agentic loop: sends research prompt, executes tool calls requested by Claude, collects JSON results, loops until `stop_reason == "end_turn"`, returns text summary
  - **Phase 2** `chat_loop()` — interactive REPL seeded with Phase 1 summary; stateless (v0.1 does not carry raw tool results forward)
- `get_price_data(ticker)` — current price, previous close, 52-week high/low, market cap, P/E, beta, volume, average volume, sector, industry, 1-month return via yfinance
- `get_news(ticker, max_items=8)` — up to 10 recent headlines with title, publisher, summary, published_at, url via yfinance `.news`; normalises both legacy flat shape and newer `content{}` shape
- `TOOLS` list and `_DISPATCH` dict in `theta/tools.py` — tool registry and dispatcher; `process_tool_call()` routes Claude's tool requests to the correct function
- Pydantic models in `theta/models.py` — `PriceData`, `NewsItem`
- `SYSTEM_PROMPT` in `theta/prompts.py` — agent identity, tool-use instruction, structured output format, financial disclaimer
- `SessionLogger` in `theta/logger.py` — writes JSONL session logs to `logs/` (auto-created)
- Structured strategy output format: strategy name, outlook, contracts, max profit/loss, breakeven, rationale
- `pyproject.toml` with `uv`-compatible dependency spec (`anthropic`, `yfinance`, `pydantic>=2.0`, `python-dotenv`)
- `docs/OVERVIEW.md` — north-star reference: architecture, ASCII data flow, increment plan, tool catalogue, strategy framework, extension guide
- `docs/tools.md` — deep walkthrough of the tool layer and agentic loop
