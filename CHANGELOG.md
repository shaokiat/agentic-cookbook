# Changelog

All notable changes to theta-agent are documented here.

## [Unreleased]

### Planned — v0.8
- `get_ibkr_positions` — read live account positions from IBKR Client Portal Web API; context-aware strategy suggestions against existing holdings

---

## [0.7.0] — Signal Scorecard, IV surface, and earnings calendar

### Added
- `get_earnings_dates(ticker)` — new tool; 3-tier yfinance fallback (`get_earnings_dates()` → `calendar` → `earnings_dates` property); returns up to 4 future dates with `days_until`; returns empty list gracefully for ETFs and tickers with no earnings data
- `get_options_chain` extended to multi-expiry: 3 nearest expiries (each ≥ 14 days), strikes ±15% of spot (up from ±10%)
- OLS IV surface fit across all (strike, expiry) pairs: `iv_fitted` and `iv_excess` (`IV − IV_fitted`) per contract; `IVSurface` model with `r_squared` and `n_points` attached to the chain
- `earnings_count` per expiry — number of upcoming earnings dates falling within `(today, expiry_date]`; contracts spanning an earnings event are flagged automatically
- `spread_pct` (bid-ask as % of mid) on each `OptionContract`; `atm_spread_pct` on each `OptionsExpiry`
- Contracts within each expiry sorted descending by `iv_excess` (richest IV first) to guide credit-spread leg selection
- Signal Scorecard framework in the system prompt: 5 signals (Directional Bias, IV Regime, Event Risk, Conviction, Liquidity) each with For/Against/Confidence fields and explicit scoring anchors; strategy family selected from Directional × IV Regime matrix; Event Risk, Conviction, and Liquidity modifiers applied in order
- "Why not [alternative]" and Sensitivity fields added to every strategy recommendation
- `/scorecard` slash command — re-prints the full 5-signal scorecard from the research phase
- `/strategy` slash command updated to re-state the full format including "Why not" and Sensitivity
- Scorecard scores (`directional_bias`, `iv_regime`, `event_risk`, `conviction`, `liquidity`) added to the structured session-extraction JSON record stored in state
- `max_tokens` raised from 2048 → 4096 to accommodate the richer scorecard output
- Tool `[tool]` preview in terminal now shows `query` param for `search_web` (previously only `ticker` was shown)

### Models changed
- New: `EarningsDate`, `EarningsDates`, `IVSurface`, `OptionsExpiry`
- `OptionsChain` restructured: `expiries: list[OptionsExpiry]` replaces the single-expiry flat structure; top-level `iv_surface` field added; `atm_iv` field removed
- `OptionContract` extended with `iv_fitted`, `iv_excess`, `spread_pct`
- `Financials` extended with `short_ratio` (days-to-cover) and `short_pct_of_float`

---

## [0.6.0] — Modular tools and web search

### Added
- `search_web(query, count?)` — native web search via Brave Search REST API; requires `BRAVE_API_KEY` env var; gracefully returns an error dict if the key is absent rather than crashing
- `tools/` package: one file per tool, each exporting the function and a `SCHEMA` dict; `tools/__init__.py` assembles the `TOOLS` list and `_DISPATCH` map
- `prompts/system.md` — system prompt extracted from the Python constant in `theta/prompts.py` to a standalone Markdown file; loaded at startup with `Path.read_text()`; prompt diffs are now legible in git history without touching Python
- `theta/tools.py` reduced to a two-line shim re-exporting `TOOLS` and `process_tool_call` from the `tools/` package; `theta/agent.py` unchanged
- `requests>=2.34.2` added as a runtime dependency for `search_web`
- `load_dotenv()` moved to before tool imports in `theta.py` so env vars are available at module-init time (fixes `BRAVE_API_KEY` not being set when `search_web` is registered)
- `pyproject.toml` version bumped to 0.6.0; `tools*` added to `packages.find` so the new package is installed correctly
- `README.md` — user-facing quick-start guide (installation, usage, tool list, slash commands)

### System prompt additions (v0.6)
- Instruction to prefer `search_web` results over yfinance news when both are available for the same event

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
