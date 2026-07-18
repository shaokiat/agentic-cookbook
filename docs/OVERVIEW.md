# theta-agent — Reference Overview

> This is the north-star document for the theta-agent project. All implementation sessions should start here. For a deep walkthrough of how tools and the agentic loop work, see [`docs/tools.md`](tools.md). For a deep dive into the state store implementation, see [`docs/state_store.md`](state_store.md).

---

## 1. Project Summary

**theta-agent** is a CLI tool that fetches live stock data and proposes a concrete options strategy via an agentic conversation with Claude. Given a ticker symbol, it autonomously fetches price data and news, synthesises a directional thesis, recommends a specific trade with exact strikes and expiry, and then opens an interactive session for the user to refine and explore alternatives.

**Intended user:** A retail options trader or finance student who understands basic options mechanics (calls, puts, spreads) and wants a research head-start, not a fully autonomous trading bot. They are comfortable with a terminal and know that this is a tool for ideation, not execution.

**What theta-agent is NOT:**
- Not a trade executor or brokerage integration
- Not a portfolio manager or position tracker
- Not a real-time price feed or alerting system
- Not a backtester or strategy optimizer
- Not regulated financial advice of any kind

**Design philosophy:** Start with the simplest possible thing that produces genuine value — one ticker, two tools, one strategy suggestion. Earn each added capability by proving the simpler version is useful first. Never add infrastructure until it earns its keep.

---

## 2. Architecture Overview

### Plain English

The entry point is `theta.py`, a thin CLI shim that parses the ticker, initialises an Anthropic client, and hands off to `ThetaAgent` (in `theta/agent.py`).

The agent runs in two phases. In **Phase 1** it enters an agentic loop: it sends a research prompt to Claude with a list of available tools. Claude responds by requesting tool calls. The agent executes each tool, collects the JSON results, sends them back, and repeats until Claude produces a final text summary. In **Phase 2** it enters a conversational REPL: the user types follow-up questions, which are answered with the full session context in memory.

The **tool layer** (`theta/tools.py`) contains pure Python functions that fetch data from yfinance or other sources. Each function has a matching JSON schema registered in the `TOOLS` list. The dispatcher `process_tool_call()` routes Claude's tool requests to the right function. From v0.6 onwards, the tool layer lives in `tools/`, one file per tool.

MCP servers will slot into the tool registry in v0.7 — they appear alongside native tools in the `TOOLS` list and are dispatched the same way, with the MCP client handling the remote call transparently.

### ASCII Data Flow

```
User types: python theta.py AAPL
                    │
                    ▼
            ┌──────────────┐
            │   theta.py   │  parses argv, loads env, creates Anthropic client
            └──────┬───────┘
                   │ ThetaAgent(ticker, client)
                   ▼
       ┌───────────────────────┐
       │  ThetaAgent           │
       │  .run_research()      │◄──────────────────────────┐
       └──────────┬────────────┘                           │
                  │                                        │ loop until
                  │ messages.create(                       │ stop_reason
                  │   system=SYSTEM_PROMPT,                │ == "end_turn"
                  │   tools=TOOLS,                         │
                  │   messages=[...]                       │
                  │ )                                      │
                  ▼                                        │
       ┌──────────────────┐                               │
       │   Claude API     │                               │
       │  (Sonnet 4.6)    │                               │
       └──────┬───────────┘                               │
              │                                           │
      ┌───────┴────────┐                                  │
      │                │                                  │
stop_reason        stop_reason                            │
"tool_use"         "end_turn"                             │
      │                │                                  │
      ▼                ▼                                  │
┌──────────┐    ┌─────────────┐                          │
│ToolUse   │    │ TextBlock   │                          │
│ blocks[] │    │ (summary)   │                          │
└────┬─────┘    └──────┬──────┘                          │
     │                 │                                  │
     ▼                 │ return summary                   │
┌──────────────────┐   │                                  │
│process_tool_call │   │                                  │
│ get_price_data() │   │                                  │
│ get_news()       │   │                                  │
│ get_options_     │   │                                  │
│   chain() [v0.2] │   │                                  │
└──────┬───────────┘   │                                  │
       │ JSON string   │                                  │
       ▼               │                                  │
  tool_result msgs ────┼──────────────────────────────────┘
  appended to          │
  messages[]           │
                       ▼
             ┌──────────────────┐
             │  .chat_loop()    │  stateless v0.1 → stateful v0.5
             └──────┬───────────┘
                    │
              ┌─────┴──────────────────┐
              │   Interactive REPL      │
              │                         │
              │  You: "What if IV       │
              │        spikes?"          │
              │        │                 │
              │        ▼                 │
              │  messages.create()      │
              │  (no tools, pure chat)  │
              │        │                 │
              │        ▼                 │
              │  Claude: "IV spike      │
              │   would help a long     │
              │   straddle because..."  │
              │        │                 │
              │  loop until exit        │
              └─────────────────────────┘
```

### Component Map

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
├── tools/                ← one file per tool from v0.6 (not yet created)
├── prompts/              ← system.md from v0.6 (not yet created)
├── analyses/             ← saved JSON outputs from v1.0 (not yet created)
└── logs/                 ← JSONL session logs (auto-created)
```

---

## 3. Increment Plan

| Version | Name | What it adds | New tools | Complexity |
|---|---|---|---|---|
| v0.1 | Bare bones | Price data + news → one strategy suggestion; basic chat loop | `get_price_data`, `get_news` | Low |
| v0.2 | Options chain | Live strikes, OI, IV by expiry; ATM filter; system prompt updated for IV/OI reasoning | `get_options_chain` | Low-medium |
| v0.3 | Greeks | Delta, gamma, theta, vega per contract via BSM; system prompt updated | extends `get_options_chain` | Medium |
| v0.4 | Financial metrics | Valuation ratios, margins, growth rates, analyst consensus, balance sheet health via yfinance | `get_financials` | Low |
| v0.5 | Conversation memory + state | Full `messages[]` history in chat loop; `/summary`, `/strategy`, `/position` slash commands; per-ticker JSON state store (position persistence + session history injected into future prompts) | none | Low |
| v0.6 | Modular tools | `tools/` directory with one file per tool; `prompts/system.md`; native `search_web` (Brave Search REST API) | `search_web` | Low (refactor) |
| v0.7 | IV surface + earnings | `get_earnings_dates` tool; `get_options_chain` extended to multi-expiry with iv_excess ranking and earnings_count annotation; system prompt updated for structured analysis chain | `get_earnings_dates`, extends `get_options_chain` | Medium |
| v0.8 | IBKR positions | Read live account positions from IBKR Client Portal Web API; context-aware strategy suggestions against existing holdings | `get_ibkr_positions` | Medium |
| v0.9 | Textual TUI | Split-pane terminal UI (`theta_ui.py`); agent callbacks replace `print()`/`input()`; CLI (`theta.py`) unchanged | none new | Medium |
| v1.0 | Production baseline | Error handling, rate limiting, response caching, `analyses/` JSON output, polished README | none new | Medium-high |

**Backlog (deferred, not scheduled):**

*Near-term / low complexity:*
- `/compare <TICKER2>` slash command: mid-session side-by-side directional bias and IV regime for a second ticker — no new tools, just a second research pass with the existing tool set; useful for pairs trades and sector rotation
- Historical RSI context (`rsi_52w_avg`): extend price history fetch to 1 year, compute average RSI over the trailing 52 weeks to provide a relative baseline — RSI 72 is less alarming if the stock routinely trades at 70+; purely additive to `get_price_data`, no new dependency

*v1.0 production baseline:*
- Response caching: TTL cache at the `process_tool_call` dispatcher level — 5-min TTL for options chain, session-scoped for price/financials; cuts latency and reduces yfinance rate-limit exposure; modular tool layer makes this a clean insertion point
- `analyses/` structured output: write the full session record (scorecard scores, strategy recommendation, raw tool results) to `analyses/<TICKER>_<DATE>.json` on exit; enables reviewing past sessions, tracking scorecard drift over time, and provides the snapshot dataset needed for golden-set regression testing
- Prompt/instruction evaluation: verify the system prompt effectively uses richer context (Greeks, financial metrics, RSI, skew, short interest) as versions accumulate — candidate approaches: (1) LLM-as-judge scoring each session output against a rubric (`did it cite RSI?`, `did it mention skew direction?`, `is iv_excess cited in contract selection?`); (2) golden-set regression — a small set of saved `analyses/` snapshots with expected strategy fields, run after each prompt change to detect regressions; (3) ablation — compare outputs with and without a new context block to confirm Claude actually uses it; requires `analyses/` output (above) to be in place first

*Longer-term:*
- IBKR positions (`get_ibkr_positions`): read live account positions from IBKR Client Portal Web API; context-aware strategy suggestions against existing holdings; medium complexity, dependent on user running CP Gateway locally
- Sector/market regime signal: fetch SPY or the sector ETF alongside the ticker to compute relative strength — the one identified blind spot that warrants a 6th scorecard signal; deferred until response caching (above) makes the second yfinance fetch cheap
- SEC filings (`get_sec_filing`): 10-K/10-Q/8-K via EDGAR free API — parsing complexity and token cost outweigh marginal value over yfinance financial metrics
- MCP integration: Brave Search MCP server as an alternative to the native `search_web` tool; unified tool registry for native + MCP tools; deferred because native search_web already covers the use case
- Deep financial analysis: structured multi-dimensional analysis using data already retrieved by existing tools — cross-referencing valuation, growth, margins, analyst consensus, and options metrics into a comparative breakdown (e.g. vs sector peers, vs historical ranges); prompt engineering deferred

---

## 4. Tool Catalogue

### Quick Reference

| Tool | Introduced | Source | API Key | Cache TTL |
|---|---|---|---|---|
| `get_price_data` | v0.1 | yfinance | None | Session (once) |
| `get_news` | v0.1 | yfinance `.news` | None | 15 min |
| `get_options_chain` | v0.2 | yfinance `.option_chain` | None | 5 min |
| `get_financials` | v0.4 | yfinance `.info` | None | Session (once) |
| `search_web` | v0.6 | Brave Search REST API | `BRAVE_API_KEY` | 15 min |
| `get_earnings_dates` | v0.7 | yfinance (3-tier fallback) | None | Session (once) |
| `get_ibkr_positions` | v0.8 | IBKR Client Portal Web API | None (CP Gateway session) | Session (once) |

### v0.7 Tool Specifications

#### `get_earnings_dates(ticker)`

Fetches upcoming earnings dates using a 3-tier yfinance fallback (most reliable first):
1. `ticker.get_earnings_dates(limit=8)` — preferred
2. `ticker.calendar["Earnings Date"]` — handles dict and DataFrame forms
3. `ticker.earnings_dates` — property fallback

Returns up to 4 future earnings dates as a list of `{date, days_until}` objects. Returns an empty list gracefully if no data is available (not all tickers have earnings — ETFs, SPACs, etc.).

```json
{
  "ticker": "AAPL",
  "earnings_dates": [
    {"date": "2026-07-31", "days_until": 71},
    {"date": "2026-10-30", "days_until": 162}
  ]
}
```

#### `get_options_chain(ticker)` — enhanced in v0.7

Fetches the nearest 3 expiries (each ≥ 14 days out), wider strike band (15% of spot in each direction), then fits an IV surface via OLS and annotates each contract with `iv_excess` and `earnings_count`.

**IV surface model:** `IV ≈ a + b·m + c·m² + d·√T + e·m·√T` where `m = log(K/S)` (log-moneyness) and `T = DTE/365`. Fit globally across all (strike, expiry) pairs with `iv > 0.02` and `dte > 0`. Requires ≥ 5 valid data points; gracefully degrades to `iv_excess = 0.0` if fewer.

**`iv_excess`:** `iv - iv_fitted` — how many volatility points the contract's actual IV exceeds (or is below) the modeled surface. Positive = IV rich, negative = IV cheap.

**`earnings_count`:** Number of upcoming earnings dates that fall within `(today, expiry_date]`. Contracts with `earnings_count > 0` span at least one earnings event.

**Output structure:**

```json
{
  "current_price": 189.42,
  "iv_surface": {"r_squared": 0.87, "n_points": 42},
  "expiries": [
    {
      "expiry": "2026-06-20",
      "dte": 30,
      "earnings_count": 0,
      "calls": [
        {
          "strike": 190.0, "bid": 3.10, "ask": 3.30,
          "iv": 0.28, "iv_fitted": 0.24, "iv_excess": 0.04,
          "volume": 1200, "open_interest": 8400,
          "delta": 0.48, "gamma": 0.042, "theta": -0.067, "vega": 0.19
        }
      ],
      "puts": [...]
    },
    {
      "expiry": "2026-07-18",
      "dte": 58,
      "earnings_count": 1,
      "calls": [...],
      "puts": [...]
    }
  ]
}
```

Within each expiry, calls and puts are sorted descending by `iv_excess` (richest IV first).

---

Full input/output specifications for each tool are in [`docs/tools.md`](tools.md#tool-specifications).

---

## 5. State Store (v0.5+)

### Purpose

`theta/state.py` provides cross-session memory for a given ticker. It stores two things:

1. **Position** — the user's current holdings in the ticker, free-text. Updated interactively at session start; persisted on exit. Injected into the research prompt so Claude can factor it into every strategy suggestion.
2. **Session history** — a compact record of past sessions (date + truncated research summary, capped at 10 entries). The most recent 3 are injected as prior context into the research prompt on the next run.

### File format

`state/AAPL.json`:
```json
{
  "ticker": "AAPL",
  "last_updated": "2026-05-09T14:30:00Z",
  "position": "Long 100 shares @ $178, sold 1x Jun $190 covered call",
  "sessions": [
    {
      "date": "2026-05-09",
      "summary": "AAPL trading at $189. Bullish thesis on product cycle, IV compressed. Bull Call Spread $190/$195 Jun 20 recommended..."
    }
  ]
}
```

### API

| Function | Signature | What it does |
|---|---|---|
| `load` | `load(ticker) → dict` | Reads `state/{ticker}.json`; returns blank template if absent |
| `save` | `save(ticker, position, session_summary)` | Updates position, appends session record, trims to 10 entries, writes file |
| `prior_context` | `prior_context(state, max_sessions=3) → str \| None` | Formats last N sessions into a plain-text block for prompt injection; returns None if no history |

### Design decisions

- **JSON, not SQLite** — single-ticker files are human-readable, git-diffable, and require no dependencies. Cross-ticker queries are not a current use case.
- **Append-only sessions list** — each session appends rather than overwrites, preserving history up to the cap. The position field is a mutable single value since the user has one current position per ticker.
- **500-char summary truncation** — keeps the state file compact and the injected prior-context block within a predictable token budget.
- **`state/` directory** — auto-created on first save. Add to `.gitignore` if position data is sensitive.

---

## 6. Conversation Flow

### Phase 0 — Startup (v0.5+)

Before research begins, `theta.py` runs a state-load and position prompt:

1. `state_store.load(ticker)` reads `state/AAPL.json` (blank template if file absent)
2. If previous sessions exist, prints `[state] N previous session(s) found for AAPL`
3. If a stored position exists, shows it and asks: keep / update / clear
4. If no stored position, asks: enter position or press Enter to skip
5. `state_store.prior_context(state)` formats the last 3 session summaries into a block that will be appended to the research prompt

### Phase 1 — Autonomous Research (no user input)

1. `ThetaAgent.run_research()` builds the initial prompt:
   - Base: *"Research AAPL and suggest one options strategy."*
   - If position provided: appended as *"Current position: … Factor this into your analysis."*
   - If prior sessions exist: appended as *"Prior sessions (most recent first): …"*
2. **API call 1:** Claude receives prompt + tool schemas → responds with `tool_use` blocks (all four tools requested in a single response)
3. Agent executes tools, collects JSON results, appends as `tool_result` user message
4. **API call 2:** Claude synthesises all data → responds with `end_turn` and the research summary
5. Summary + full `messages[]` list returned to `theta.py`; session JSONL log written to `logs/`

**Target duration:** under 20 seconds (2 API round-trips + 4 yfinance calls)

**Structured output at end of Phase 1:**
```
Research summary (3-5 sentences covering price action, key stats, sentiment)

Strategy recommendation:
  Strategy: [name]
  Outlook:  [bullish/bearish/neutral]
  Trade:    [specific contracts with strikes and expiry]
  Max profit: $X | Max loss: $Y
  Breakeven: $Z
  Rationale: [2-3 sentences]

⚠ Not financial advice.
```

---

### Phase 2 — Interactive Session

Once Phase 1 completes, `chat_loop()` starts.

**v0.1 (stateless):** `messages[]` is seeded with the original prompt and Phase 1 summary as the first assistant turn. Each new user question appends to this list and gets a response, but the list grows without bound — there is no summarisation or truncation. The research data is not re-fetched mid-chat; Claude reasons from what is already in the context window.

**v0.5 (stateful):** The full message history from `run_research()` — including raw tool results (price JSON, news JSON, options chain, financials) — is carried forward into `chat_loop()`. Claude has access to every data point fetched during Phase 1 without re-fetching.

**On exit** (any of `exit`, `quit`, `q`, `/exit`, Ctrl-C), `state_store.save()` writes the updated position and a truncated session summary to `state/AAPL.json`. This record is injected as prior context on the next session for the same ticker.

**Supported slash commands (v0.5+):**

| Command | Behaviour |
|---|---|
| `/summary` | Claude prints a one-paragraph recap of the thesis and recommended strategy so far |
| `/strategy` | Claude re-states the current recommended strategy in the standard format (strikes, expiry, max profit/loss) |
| `/position` | Claude re-states the user's declared position and how it interacts with the recommended strategy |
| `/exit` | Saves state and exits (alias for `exit`, `quit`, `q`) |

**Off-topic questions:** Claude should acknowledge the question is outside its scope, redirect to options analysis, and offer to continue with the ticker at hand. It should not answer general coding questions, give news on unrelated tickers, or discuss topics unrelated to the session's thesis.

---

### Sample Terminal Session

```
$ python theta.py AAPL

Researching AAPL...

  [tool] get_price_data(AAPL)
  [tool] get_news(AAPL)

  [log] logs/20260508T143012Z_AAPL.jsonl

============================================================
  THETA-AGENT  |  AAPL
============================================================
Apple (AAPL) is trading at $189.42, up 2.1% on the day and
near its 52-week high of $192.13, with a beta of 1.07 and
no current implied volatility reading from spot data. Recent
news is broadly constructive: three bullish analyst upgrades
and a well-received product announcement.

Strategy: Bull Call Spread
  Outlook:  Bullish, low-IV environment
  Trade:    Buy $190 call / Sell $195 call, expiry Jun 20
  Max profit: $320 | Max loss: $180 per contract
  Breakeven: $191.80
  Rationale: IV is moderate, limiting long premium cost; the
  spread caps risk while expressing a measured bullish bias
  into the product cycle.

⚠ Not financial advice.

------------------------------------------------------------
Ask follow-up questions, or type 'exit' to quit.
------------------------------------------------------------

You: What happens if AAPL drops 5% after earnings?

Claude: A 5% drop from $189 would put AAPL around $179.55,
well below the $190 long strike. Both legs of the bull call
spread would expire worthless, and you'd lose the full $180
premium paid. The key risk here is IV crush after the
earnings event — even if the stock holds flat, the implied
volatility collapse that follows earnings typically reduces
option value significantly in the first hours post-print.
If earnings risk is your concern, consider waiting until
after the event to enter, when IV is lower and the
directional move is already priced in.

You: exit
Goodbye!
```

---

## 7. Analysis Architecture (v0.7+)

### The Reasoning Chain

The core design principle: Claude should follow an explicit, ordered reasoning chain rather than synthesizing all data simultaneously. Each step has a specific question, specific inputs, and a specific output that feeds the next step. The system prompt enforces this chain.

```
Step 1: Directional Thesis
    Inputs:  get_price_data, get_financials
    Question: Is the stock trending up, down, or sideways? Is the valuation stretched?
    Output:  Bullish / Bearish / Neutral + conviction level

Step 2: Event Clarity Assessment
    Inputs:  get_earnings_dates, get_news, search_web
    Question: Is there a known binary event? Which expiries span it?
    Output:  Event timeline + which expiry dates are earnings-exposed

Step 3: IV Regime
    Inputs:  get_options_chain (iv_excess, iv_surface r²)
    Question: Are options currently rich or cheap relative to the modeled surface?
    Output:  IV rich / cheap / neutral — per expiry and per strike

Step 4: Strategy Family
    Inputs:  Step 1 output × Step 3 output → strategy matrix (Section 8)
    Question: Which strategy family fits this thesis + IV environment?
    Output:  One strategy family (e.g. bull put spread, iron condor)

Step 5: Contract Selection
    Inputs:  get_options_chain (iv_excess ranking, OI, Greeks)
    Question: Which specific strikes and expiry best express the strategy?
    Output:  Exact contracts — strike, expiry, bid/ask, max profit/loss, breakeven
```

### Why This Order Matters

Steps 1 and 2 are computed before touching the options chain. This prevents the common failure mode where Claude anchors on a high-IV contract and reverse-engineers a directional thesis to justify selling it. The thesis is derived from fundamentals and price action; the options chain is used only to express it efficiently.

Step 3 uses `iv_excess` rather than raw IV. Raw IV of 45% is ambiguous — whether it is elevated or compressed depends on the stock's normal range, its term structure, and current skew. `iv_excess` normalises this: a contract 8 vol points above the modeled surface is rich regardless of its absolute IV level.

Step 5 uses `iv_excess` ranking for contract selection within the chosen strategy family:
- **Sell strategies** (credit spreads, covered calls, cash-secured puts): pick legs with the highest `iv_excess` — these contracts are the most overpriced by the surface model
- **Buy strategies** (debit spreads, long calls/puts): pick legs with the lowest `iv_excess` — these contracts are the cheapest relative to the surface
- **Spread strategies**: sell the rich leg, buy the cheap leg — `iv_excess` difference between legs is the mispricing captured

### Earnings-Aware Expiry Selection

When `earnings_count > 0` on an expiry, that contract spans a known binary event. The strategy choice should be deliberate, not accidental:

```
Earnings in the expiry window:
  → IV is typically inflated (event premium baked in)
  → Selling: attractive premium but binary outcome risk — prefer defined-risk spreads
  → Buying: IV crush post-earnings will erode value even if direction is correct

No earnings in the expiry window:
  → IV reflects ongoing vol; iv_excess is a cleaner signal
  → Pre-earnings expiry + upcoming earnings: IV may still be elevated in sympathy
  → Recommend flagging which scenario applies and letting the user decide
```

### IV Surface Reliability

The surface fit produces an `r_squared` value. Below 0.70, the model has poor fit (too few data points, wide bid-ask spreads making IV noisy, or a genuinely unusual skew profile). When `r_squared < 0.70`, treat `iv_excess` as directional guidance only and fall back to raw IV comparisons and OI as primary signals.

### Data Flow for v0.7 Research Phase

All five tools are called in the first Claude API turn (parallel tool use). Claude should then reason through steps 1-5 sequentially in its synthesis turn:

```
Tool calls (parallel, API Turn 1):
  get_price_data(ticker)
  get_news(ticker)
  get_financials(ticker)
  get_earnings_dates(ticker)   ← new in v0.7
  get_options_chain(ticker)    ← now returns multi-expiry + iv_excess

Synthesis (API Turn 2):
  1. Directional thesis from price + financials
  2. Event timeline from earnings_dates + news
  3. IV regime from iv_surface r² and per-contract iv_excess
  4. Strategy family from thesis × IV regime matrix
  5. Specific contracts using iv_excess ranking + OI + Greeks
  6. Formatted recommendation with all required fields
```

---

## 8. System Prompt Versioning

### v0.1 System Prompt

Stored as `SYSTEM_PROMPT` constant in `theta/prompts.py`. Under 200 words. Covers:
- Agent identity: concise options trading research assistant
- Tool use instruction: fetch price data and news first, then synthesise
- Output format: 3-5 sentence summary + ONE named strategy with rationale and rough parameters
- Reasoning directive: base suggestions on actual data (IV, trend, sentiment), not priors
- Follow-up instruction: reason about options mechanics (delta, theta, IV crush, risk/reward)
- Financial disclaimer: never make price predictions; focus on probabilities and risk management

### System Prompt Additions by Version

| Version | What is added |
|---|---|
| v0.2 | Instructions for reasoning about IV levels and open interest when selecting strategy type; guidance on ATM vs OTM strike selection |
| v0.3 | Instructions for interpreting Greeks: use delta for directional exposure, theta decay for calendar positioning, vega for IV sensitivity |
| v0.4 | Instructions for using financial metrics (valuation ratios, margins, growth, analyst consensus) to qualify or challenge the options thesis |
| v0.5 | `/summary` and `/strategy` slash command definitions and expected output format |
| v0.6 | Instructions for prioritising web search results over yfinance news when both are available |
| v0.7 | Signal scorecard format (5 signals, For/Against/Confidence per signal, COMPOSITE block); scoring rubrics with explicit anchor points for each signal; strategy family matrix from Directional × IV Regime; Event Clarity / Conviction / Liquidity modifiers; "Why not" and Sensitivity fields in recommendation; `/scorecard` slash command |

### Prompt File Migration (v0.6)

In v0.1–v0.5, the system prompt lives as a string constant in `theta/prompts.py`. In v0.6, when the codebase is restructured, it should move to `prompts/system.md` and be loaded at startup with `Path("prompts/system.md").read_text()`. This enables editing the prompt without touching Python files and makes prompt diffs legible in git history.

### Non-Negotiable Prompt Elements

These must appear in every version of the system prompt:

1. **Agent identity:** "You are theta-agent, a concise options trading research assistant."
2. **Tool usage instruction:** fetch data with available tools before reasoning
3. **Output format:** named strategy + strikes + expiry + max profit/loss + breakeven
4. **Financial disclaimer:** "This is not financial advice. Options trading involves significant risk of loss."

---

## 8. Options Strategy Framework

### Per-Suggestion Required Fields

For every options strategy suggestion, Claude must state all of the following:

| Field | Example |
|---|---|
| Strategy name | Bull Call Spread |
| Market outlook | Bullish (moderate conviction) |
| Contracts | Buy $190 call / Sell $195 call, expiry Jun 20 |
| Max profit | $320 per contract |
| Max loss | $180 per contract |
| Breakeven at expiry | $191.80 |
| Ideal conditions | Low IV, gradual upward drift, no near-term binary events |
| Failure conditions | Earnings miss, IV spike triggering vol crush, sharp reversal below $189 |
| Risk/reward ratio | 1.78:1 |

### Strategy Selection Logic

Given the directional thesis and IV environment derived from data, Claude should select from:

| Signal | Strategy family |
|---|---|
| Bullish + low IV | Long call OR bull call spread |
| Bullish + high IV | Cash-secured put OR bull put spread |
| Bearish + low IV | Long put OR bear put spread |
| Bearish + high IV | Covered call (if holding shares) OR bear call spread |
| Neutral + high IV | Iron condor OR short strangle |
| Neutral + low IV | Long straddle OR long strangle |
| Event-driven (earnings) | Flag IV crush risk explicitly; prefer defined-risk spreads over naked long options |

### IV Environment Thresholds

**v0.7+ (preferred):** Use `iv_excess` from the options chain surface fit as the primary IV signal:
- `iv_excess > 0.04` (4+ vol points rich): IV is elevated at this strike relative to the surface — favors premium selling
- `iv_excess < -0.04` (4+ vol points cheap): IV is compressed — favors buying
- `|iv_excess| ≤ 0.02`: no strong mispricing; use raw IV level, OI, and Greeks as primary signals
- If `iv_surface.r_squared < 0.70`: surface fit is unreliable; fall back to the raw IV proxies below

**Raw IV proxies (fallback when iv_excess is unavailable or unreliable):**
- **Low IV:** `atm_iv < 0.30`, OR beta < 0.8
- **High IV:** `atm_iv > 0.50`, OR earnings within 2 weeks
- When IV data is entirely unavailable, default to defined-risk spreads and note the limitation

### Contract Selection Using IV Surface (v0.7+)

For every strategy, use `iv_excess` to select the most favorable specific contracts within the chosen strategy family:

| Strategy type | Selection rule |
|---|---|
| Sell single-leg (CSP, covered call) | Highest `iv_excess` within delta constraints |
| Buy single-leg (long call/put) | Lowest `iv_excess` within delta constraints |
| Credit spread | Sell leg: highest `iv_excess`; buy leg: lowest `iv_excess` available for the wing |
| Debit spread | Buy leg: lowest `iv_excess`; sell leg: highest `iv_excess` available for the wing |
| Iron condor | Both short legs: highest `iv_excess` on each side; wings: lowest available |

If multiple contracts have similar `iv_excess`, break ties by open interest (higher OI = better liquidity).

### Earnings Calendar

When `get_earnings_dates` returns upcoming dates, Claude must evaluate each recommended expiry against those dates:

1. If `earnings_count > 0` on the recommended expiry: explicitly state which earnings event(s) fall within the window, the approximate date, and the strategy implication (long vega benefits from the event premium; short vega risks IV crush post-print)
2. If `earnings_count = 0` but earnings is within 14 days of the expiry: note that IV in adjacent expiries may still be elevated in sympathy
3. Always state whether the recommended strategy is long or short vega
4. If the user has not expressed a preference on earnings exposure: suggest the pre-earnings expiry for defined-risk structures and flag the post-earnings expiry as an alternative if they want to capture the event premium

---

### Signal Scorecard Framework (v0.7+)

Every Phase 1 output begins with a scored signal scorecard before the strategy recommendation. The scorecard is Claude's judgment, not a mechanical calculation — but it must follow three discipline rules:

1. **Evidence first, score second.** List the supporting and contrary evidence for each signal, then assign the score. The number should feel like a conclusion, not an assertion.
2. **Counterargument required.** Every signal must name the strongest piece of evidence pointing against its score. This prevents cherry-picking.
3. **Confidence qualifier.** Each signal carries High / Medium / Low data confidence based on how complete the underlying data is.

#### The Five Signals

Displayed order: Directional Bias → Event Clarity → IV Regime → Conviction → Liquidity (matches reasoning chain).
A one-line directional verdict (`DIRECTIONAL BIAS: Bullish  7 / 10`) is printed before the full scorecard.

| Signal | What it measures | Primary inputs | Score anchor |
|---|---|---|---|
| **Directional Bias** | Bull / bear / neutral conviction | Price trend, RSI-14, financials, analyst consensus, news | 1=strong bear, 5=neutral, 10=strong bull |
| **Event Clarity** | Cleanliness of the expiry window | `earnings_dates`, `earnings_count` on target expiry | 10=no near-term catalyst, 1=earnings in <7 days spanning expiry |
| **IV Regime** | Whether options are rich or cheap | `iv_excess`, skew (OTM put IV − call IV), `iv_surface.r_squared`, ATM IV | 1=very cheap, 5=fair value, 10=very rich |
| **Conviction** | Internal signal agreement | Price, RSI, news, fundamentals, analyst consensus, short interest | 1=all signals diverge, 10=all signals aligned |
| **Liquidity** | Execution quality at target strikes | Bid-ask as % of mid, open interest | 1=illiquid, 10=tight spreads and deep OI |

#### Scoring Anchors

**Directional Bias**
Sub-inputs: price trend (return_1mo_pct), RSI-14, financials (growth, valuation), analyst consensus, news sentiment
- 9-10: Price trending strongly, RSI 50–70 (momentum without overbought), analyst consensus Buy/Strong Buy, positive earnings growth, news broadly constructive — all sub-signals aligned
- 7-8: Most signals bullish; one neutral or mildly contradictory data point; RSI > 75 caps bullish score at 8
- 5-6: Genuinely mixed — one bullish, one bearish, or all neutral; no clear edge
- 3-4: Most signals bearish; one neutral or mildly constructive
- 1-2: All sub-signals bearish and aligned

**IV Regime**
- 9-10: `iv_excess ≥ 0.08` AND `r² ≥ 0.70`
- 7-8: `iv_excess` 0.04–0.08 AND `r² ≥ 0.70`
- 5-6: `|iv_excess| < 0.04`, OR `r² < 0.70` (note poor surface fit inline in Against field)
- 3-4: `iv_excess` −0.08 to −0.04
- 1-2: `iv_excess ≤ −0.08`
- Skew enrichment: state `skew` (OTM put IV − OTM call IV at ~0.25 delta) alongside `iv_excess`; positive skew = elevated downside hedging demand

**Event Clarity** (higher = cleaner expiry window; all five signals now read higher = better)
- 9-10: No upcoming earnings, or next event > 90 days out
- 7-8: Earnings 45–90 days, does not span target expiry
- 5-6: Earnings 22–45 days AND spans expiry; OR earnings <21 days but pre-expiry
- 3-4: Earnings 8–21 days AND spans the target expiry
- 1-2: Earnings within 7 days AND `earnings_count > 0` on target expiry

**Conviction**
Sub-signals: price trend, RSI, news sentiment, earnings growth, analyst consensus, short interest
- 9-10: 4+ directional sub-signals aligned with no contradictions
- 7-8: 3 sub-signals aligned, 1 neutral or ambiguous
- 5-6: 2 aligned, 1–2 directly contradictory (genuinely uncertain)
- 3-4: More sub-signals contra the directional score than supporting it
- 1-2: Score is driven by a single data point; all others point the other way
- Short interest: always named explicitly when `short_ratio` or `short_pct_of_float` is available; `short_ratio > 5` or `short_pct_of_float > 0.10` = one contra sub-signal for a bullish thesis

**Liquidity**
- 9-10: Bid-ask < 2% of mid AND OI > 5,000
- 7-8: Bid-ask 2–5% of mid OR OI 1,000–5,000
- 5-6: Bid-ask 5–10% of mid OR OI 500–1,000
- 3-4: Bid-ask 10–20% of mid OR OI 100–500
- 1-2: Bid-ask > 20% of mid AND OI < 100

#### Strategy Selection from Scores

**Step 1 — Strategy family** from Directional × IV Regime:

| | IV Cheap (1–4) | IV Fair (5–6) | IV Rich (7–10) |
|---|---|---|---|
| **Bullish (7–10)** | Long call / Bull call spread | Bull call spread | Bull put spread / CSP |
| **Neutral (4–6)** | Long straddle / strangle | Skip / wait | Iron condor / short strangle |
| **Bearish (1–3)** | Long put / Bear put spread | Bear put spread | Bear call spread / Covered call |

**Step 2 — Structure modifier** from Event Clarity (lower score = more event risk = stricter structure):
- Event Clarity ≤ 3: mandatory defined-risk structure (no naked short legs), flag IV crush risk explicitly
- Event Clarity 4–5: prefer defined-risk; flag if naked leg is considered
- Event Clarity ≥ 6: defined-risk still preferred for retail; naked legs permissible if user has stated comfort

**Step 3 — Width and delta** from Conviction:
- Conviction ≥ 8: standard width, ATM-adjacent strikes (delta 0.35–0.50)
- Conviction 6–7: moderate width, slightly OTM (delta 0.25–0.35)
- Conviction ≤ 5: narrow width, further OTM (delta 0.15–0.25); note the uncertainty explicitly

**Step 4 — Execution check** from Liquidity:
- Liquidity ≤ 4: warn that fills may be at worse-than-theoretical prices; suggest checking the order book before placing
- Liquidity ≤ 2: flag explicitly; consider a nearby expiry or strike with better liquidity

#### Terminal Display Format

```
DIRECTIONAL BIAS:  Bullish  7 / 10

SIGNAL SCORECARD  |  AAPL  |  2026-06-20

DIRECTIONAL BIAS                                          7 / 10  Bullish
  For:    Price +2.1% 1-month, RSI-14 = 58 (momentum, not overbought);
          analyst avg target $210 (+11%); EPS growth +12% YoY
  Against: One analyst downgrade last week; tariff headwinds cited in supply chain news

EVENT CLARITY                                             8 / 10  Clear
  Earnings Jul 31 (71 days) — outside Jun expiry window; Jun expiry is pre-earnings
  Against: Earnings season proximity may keep sector IV elevated in sympathy

IV REGIME                                                 8 / 10  Rich
  For:    iv_excess +0.06 (ATM call IV 0.28 vs surface fit 0.22); skew +0.04 (puts richer)
          Surface fit r² = 0.87 across 42 contracts — reliable
  Against: IV is rich vs the surface but not extreme in absolute terms for AAPL

CONVICTION                                                7 / 10  Aligned
  Price, RSI, analyst, and fundamental signals all bullish; news 80% constructive
  Short interest: short_ratio 1.8 days — no meaningful bearish signal from short sellers
  Against: Supply chain headline is a real risk, not noise

LIQUIDITY                                                 8 / 10  Good
  ATM spread 3.2% of mid  |  OI 8,400 contracts
  Against: Spreads widen materially after hours — place orders during market hours

COMPOSITE:  Bullish (7) + Rich IV (8)  →  Bull Put Spread
  Event Clarity 8/10: Jun expiry is pre-earnings — no event modifier required
  Conviction 7/10: Standard width, ATM-adjacent strikes
  Liquidity 8/10: No execution concern

STRATEGY:   Bull Put Spread
OUTLOOK:    Bullish (moderate conviction)
TRADE:      Sell $185 put / Buy $180 put, expiry Jun 20
MAX PROFIT: $180 per contract  |  MAX LOSS: $320 per contract
BREAKEVEN:  $183.20
RATIONALE:  [2-3 sentences]

Why not bull call spread:  IV is rich — buying calls is expensive; selling puts
  captures the same bullish thesis while collecting elevated premium
Why not naked CSP:         Defines maximum loss; same premium capture with downside floor

Sensitivity:  If directional bias falls to 5 (neutral), iron condor becomes preferred
              If earnings move to Jun window (event risk >7), widen wings or shift to Jul expiry
```

#### Design Principles Behind the Format

**Evidence-first scoring:** By requiring `For:` and `Against:` before the number, Claude cannot produce a convenient score and fill in justification afterward. The evidence is the reasoning; the number is the summary.

**Counterargument per signal:** The `Against:` field prevents confirmation bias. If a bullish directional score has no credible against-case, that is itself a signal the data may be incomplete. Claude should push itself to find the strongest contrary evidence even when the primary signal is clear.

**"Why not X":** Strategy selection is not just choosing the winner — it is eliminating the alternatives. Naming rejected strategies and their reasons gives the user a mental model of the decision space, making it easier to challenge the recommendation in the follow-up chat.

**Sensitivity line:** The recommendation is a point estimate. The sensitivity line tells the user which score is closest to a decision boundary and what would change. This converts a static recommendation into a watch list — the user knows which data point to monitor.

---

## 9. Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────┐
│  USER INPUT                                                   │
│  $ python theta.py AAPL                                       │
└──────────────────────────────┬───────────────────────────────┘
                               │ sys.argv[1] = "AAPL"
                               ▼
┌──────────────────────────────────────────────────────────────┐
│  theta.py                                                     │
│  - validates ticker, checks ANTHROPIC_API_KEY                 │
│  - creates anthropic.Anthropic(api_key=...)                   │
│  - creates ThetaAgent(ticker="AAPL", client=client)           │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│  ThetaAgent.run_research()                                    │
│                                                               │
│  messages = [                                                 │
│    {"role": "user",                                           │
│     "content": "Research AAPL and suggest one strategy."}    │
│  ]                                                            │
└──────────────────────────────┬───────────────────────────────┘
                               │ client.messages.create(
                               │   model="claude-sonnet-4-6",
                               │   system=SYSTEM_PROMPT,
                               │   tools=TOOLS,
                               │   messages=messages
                               │ )
                               ▼
┌──────────────────────────────────────────────────────────────┐
│  CLAUDE API — Turn 1                                          │
│                                                               │
│  Response: stop_reason = "tool_use"                          │
│  content = [                                                  │
│    ToolUseBlock(id="toolu_01A",                               │
│                 name="get_price_data",                        │
│                 input={"ticker": "AAPL"}),                    │
│    ToolUseBlock(id="toolu_01B",                               │
│                 name="get_news",                              │
│                 input={"ticker": "AAPL"})                     │
│  ]                                                            │
└──────────────────────────────┬───────────────────────────────┘
                               │ append assistant turn to messages
                               │ for each ToolUseBlock:
                               ▼
┌──────────────────────────────────────────────────────────────┐
│  process_tool_call(name, input)                               │
│                                                               │
│  "get_price_data" → get_price_data("AAPL")                    │
│      → yf.Ticker("AAPL").info + .history()                    │
│      → PriceData.model_dump() → JSON string                   │
│                                                               │
│  "get_news" → get_news("AAPL")                                │
│      → yf.Ticker("AAPL").news[:10]                            │
│      → [NewsItem, ...] → JSON string                          │
└──────────────────────────────┬───────────────────────────────┘
                               │ tool_results = [
                               │   {"type": "tool_result",
                               │    "tool_use_id": "toolu_01A",
                               │    "content": "{...price JSON...}"},
                               │   {"type": "tool_result",
                               │    "tool_use_id": "toolu_01B",
                               │    "content": "[...news JSON...]"}
                               │ ]
                               │ messages.append({"role": "user",
                               │                  "content": tool_results})
                               ▼
┌──────────────────────────────────────────────────────────────┐
│  CLAUDE API — Turn 2                                          │
│                                                               │
│  Response: stop_reason = "end_turn"                           │
│  content = [                                                  │
│    TextBlock(text="Apple is trading at $189.42...            │
│              Strategy: Bull Call Spread...")                  │
│  ]                                                            │
└──────────────────────────────┬───────────────────────────────┘
                               │ return block.text
                               │ (SessionLogger writes .jsonl)
                               ▼
┌──────────────────────────────────────────────────────────────┐
│  ThetaAgent.chat_loop(summary)                                │
│                                                               │
│  messages = [                                                  │
│    {"role": "user",    "content": "Research AAPL..."},        │
│    {"role": "assistant","content": summary}                   │
│  ]                                                            │
│                                                               │
│  loop:                                                        │
│    user_input = input("You: ")                                │
│    if exit command → break                                    │
│    messages.append({"role": "user", "content": user_input})  │
│    response = client.messages.create(                         │
│      system=SYSTEM_PROMPT, messages=messages)   # no tools   │
│    reply = response.content[0].text                           │
│    print(f"Claude: {reply}")                                  │
│    messages.append({"role": "assistant", "content": reply})  │
└──────────────────────────────────────────────────────────────┘
```

---

## 10. Textual TUI (v0.9)

### Overview

v0.9 adds `theta_ui.py` — a [Textual](https://textual.textualize.io/) terminal UI that wraps the same `ThetaAgent` used by the CLI. The CLI (`theta.py`) continues to work unchanged. Textual is a Python-native TUI framework; `pip install textual` is the only new dependency.

### Layout

```
┌─── THETA-AGENT  |  AAPL ───────────────────────────────────────┐
│ Ticker: [____]  [Research ▶]                                    │
├──── RESEARCH / SCORECARD (40%) ────┬──── CHAT (60%) ───────────┤
│                                    │                            │
│  SIGNAL SCORECARD                  │  Claude: AAPL trading at   │
│  DIRECTIONAL  7/10 Bullish         │  $189. Bull Put Spread...  │
│  IV REGIME    8/10 Rich            │                            │
│  EVENT RISK   4/10 Low             │  You: What if IV spikes?   │
│  CONVICTION   7/10 Aligned         │                            │
│  LIQUIDITY    8/10 Good            │  Claude: IV spike would... │
│                                    │                            │
│  STRATEGY: Bull Put Spread         │  ─────────────────────     │
│  TRADE: Sell $185p / Buy $180p     │  > [input bar]        [↵]  │
└────────────────────────────────────┴────────────────────────────┘
│ ✓ get_price_data  ✓ get_financials  ⟳ get_options_chain ...     │
└────────────────────────────────────────────────────────────────┘
```

### Architecture

**New file:** `theta_ui.py` — `ThetaApp(App)` with three widgets:
- `ResearchPanel` — `ScrollableContainer` + `RichLog`; receives research output and scorecard
- `ChatPanel` — scrollable message list + `Input` widget; handles the follow-up REPL
- `StatusBar` — footer showing live tool call progress and log path

**Agent changes:** `ThetaAgent.__init__()` gains an optional `callbacks: dict | None` parameter. When set, `run_research()` and `chat_loop()` call the hooks instead of `print()`/`input()`:

```python
callbacks = {
    "on_tool_call":      fn(name: str, preview: str),   # tool progress → StatusBar
    "on_research_done":  fn(summary: str),               # Phase 1 complete → ResearchPanel
    "on_log_path":       fn(path: str),                  # log path → StatusBar
    "on_chat_reply":     fn(reply: str),                 # chat reply → ChatPanel
    "on_save_start":     fn(),                           # saving state...
    "on_save_done":      fn(),                           # state saved
}
```

When `callbacks` is `None` (default), all paths fall back to the existing `print()`/`input()` behaviour — the CLI is unaffected.

**Threading:** Textual runs its own event loop on the main thread. The agent's blocking work (API calls, yfinance fetches) runs in Textual worker threads via `@work(thread=True)`. Workers push updates to the UI with `self.app.call_from_thread(...)`. Chat submissions each spawn a short-lived worker; research spawns one worker for the full Phase 1 loop.

**State and position:** Position input is a `TextArea` in the TUI's startup screen (replaces the `input()` prompt in `theta.py`). State load/save logic is identical to the CLI.

### Files added / changed

| File | Change |
|---|---|
| `theta_ui.py` | New — `ThetaApp` entry point |
| `theta/agent.py` | Add `callbacks` param; replace `print`/`input` with callback dispatch |
| `pyproject.toml` | Add `textual` dependency |
| `CLAUDE.md` | Update component map and increment plan |

---

## 11. Extension Guide

### Recipe A — Adding a new native Python tool

1. **Write the function** in `theta/tools.py` (or a new file in `tools/` from v0.6):
   ```python
   def get_options_chain(ticker: str) -> dict:
       ...
       return result
   ```

2. **Add a Pydantic model** in `theta/models.py` if the return shape is non-trivial (optional but recommended).

3. **Add the JSON schema** to the `TOOLS` list in `theta/tools.py`:
   ```python
   {
       "name": "get_options_chain",
       "description": "Fetch near-the-money options chain...",
       "input_schema": {
           "type": "object",
           "properties": {"ticker": {"type": "string"}},
           "required": ["ticker"],
       },
   }
   ```

4. **Register in the dispatcher**: add an entry to `_DISPATCH` in `theta/tools.py`:
   ```python
   _DISPATCH = {
       "get_price_data": get_price_data,
       "get_news": get_news,
       "get_options_chain": get_options_chain,   # ← add here
   }
   ```

5. **Update the system prompt** in `theta/prompts.py` if Claude needs guidance on how to interpret the new data.

6. **Test manually**: run `python theta.py AAPL` and confirm the tool appears in the `[tool]` output line and that Claude uses the new data in its summary.

---

### Recipe B — Adding a new MCP server (v0.7+)

1. **Install the MCP server** and verify it runs locally:
   ```bash
   npx @modelcontextprotocol/server-brave-search
   ```

2. **Add MCP config** to `.mcp.json` at the project root:
   ```json
   {
     "mcpServers": {
       "brave-search": {
         "command": "npx",
         "args": ["-y", "@modelcontextprotocol/server-brave-search"],
         "env": {"BRAVE_API_KEY": "${BRAVE_API_KEY}"}
       }
     }
   }
   ```

3. **Create the MCP client** in `theta/mcp_client.py` that wraps the MCP transport and exposes a `call_tool(name, input)` interface.

4. **Register MCP tools** in the unified tool registry (to be designed in v0.7): add the Brave Search tool schema to `TOOLS` exactly as a native tool — same name, description, input_schema format.

5. **Add a dispatcher branch** that routes to `mcp_client.call_tool()` instead of a local function.

6. **Add API key check** at startup: warn if `BRAVE_API_KEY` is missing and skip registering MCP tools gracefully (don't crash).

---

### Recipe C — Adding a new slash command to the chat loop

1. **Define the command string** (e.g. `/strategy`).

2. **Add a handler branch** in `ThetaAgent.chat_loop()` in `theta/agent.py`, before the `messages.append` call:
   ```python
   if user_input.startswith("/strategy"):
       # build a specific prompt asking Claude to re-state the strategy
       messages.append({"role": "user",
                        "content": "Re-state your current strategy recommendation..."})
       # then call client.messages.create() as normal
       continue
   ```

3. **Update the session header** (the printed intro text in `chat_loop`) to list the new command.

4. **Update the system prompt** if Claude needs to know the command exists (usually not required for simple recap commands).

5. **Document** the new command in the `Slash commands` table in this file (Section 6).

---

## 12. Open Questions

These decisions are deliberately deferred. Resolve them at the version where they become necessary.

| Question | Deferred to | What's needed to decide |
|---|---|---|
| **Greeks library:** py_vollib_vectorized vs mibian vs manual BSM implementation | v0.3 | Benchmark accuracy and install friction; py_vollib_vectorized is fastest but has C dependencies. **Resolved v0.3:** manual BSM in `tools/options.py` — no C dependencies, sufficient accuracy for retail use |
| **IV percentile / regime signal:** raw IV is ambiguous without historical context | v0.7 | **Resolved v0.7:** `iv_excess` from OLS surface fit replaces raw IV percentile — cross-sectional signal across the current chain, no historical data required |
| **News source quality:** yfinance news is shallow and sometimes stale | v0.6 | **Resolved v0.6:** native `search_web` via Brave Search REST API; system prompt instructs Claude to prefer web search over yfinance news |
| **Earnings awareness:** no structured way to know if an expiry spans an earnings event | v0.7 | **Resolved v0.7:** `get_earnings_dates` + `earnings_count` annotation on each expiry |
| **Persistence format:** JSON files vs SQLite for saved analyses | v1.0 | JSON files are simpler and git-diffable; SQLite enables queries across sessions — decide based on whether cross-session analysis is a real use case |
| **Rate limiting strategy:** yfinance has undocumented rate limits | v1.0 | Measure in practice; add exponential backoff + per-session cache before adding a formal rate limiter |
| **IV surface for multi-expiry chain:** fetching wider chain increases yfinance request count and response size | v0.7 | Monitor token usage in practice; if context is a problem, trim to top 3 contracts per expiry after surface fitting, not before |
| **Multi-ticker support:** side-by-side comparison or pairs trade suggestion | post-v1.0 | Requires rethinking the single-ticker thesis structure; defer until v1.0 is stable |
| **Authentication for web deployment:** if exposed as a web app, how do users supply their own API keys? | post-v1.0 | Requires a separate auth model; out of scope for CLI-first design |
| **Context window management:** long sessions will eventually overflow the context | v1.0 | With multi-expiry options chain, raw tool output is larger; monitor token usage and add sliding window or summarisation if needed |
