# How Tools Work in theta-agent

Tools are the mechanism that lets Claude fetch real-world data during a conversation. Without them, Claude can only reason from its training data — it would have no idea what AAPL is trading at today or what news broke this morning. Tools bridge that gap.

## The core idea

When you pass `tools=TOOLS` to `client.messages.create()`, you're not giving Claude the ability to run code directly. You're giving it a menu of functions it can *request* — and your Python code is what actually executes them. Claude decides *when* and *with what arguments* to call a tool; you decide *how* that call is executed and what gets returned.

This is a deliberate design: Claude never touches your filesystem, your network, or your API keys directly. It just signals intent, and your code acts on it.

## The three pieces

### 1. The tool definition (`TOOLS` list, `theta.py:102`)

Each tool is a dict with three keys:

```python
{
    "name": "get_price_data",
    "description": "Fetch current stock price and key statistics...",
    "input_schema": {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol, e.g. AAPL, TSLA, SPY",
            }
        },
        "required": ["ticker"],
    },
}
```

The `description` is not documentation for you — it's the instruction Claude reads to decide whether and how to use the tool. A vague description produces vague tool use. The `input_schema` is a JSON Schema object that constrains what arguments Claude can pass; `required` tells Claude which fields it must always supply.

Both definitions are passed to the API on every `messages.create()` call in `run_research()`.

### 2. The Python functions (`theta.py:30–95`)

These are plain Python functions that do the actual work:

- `get_price_data(ticker)` — calls `yf.Ticker(ticker).info` and `.history(period="1mo")`, assembles a dict of price stats, strips `None` values, returns it
- `get_news(ticker)` — calls `yf.Ticker(ticker).news`, normalises the shape across yfinance versions (the `content` key was added in a newer release), returns a list of up to 10 articles

Both return native Python objects (dict / list). The dispatcher serialises them to JSON strings before handing them back to Claude.

### 3. The dispatcher (`process_tool_call`, `theta.py:145`)

```python
def process_tool_call(tool_name: str, tool_input: dict) -> str:
    if tool_name == "get_price_data":
        result = get_price_data(tool_input["ticker"])
    elif tool_name == "get_news":
        result = get_news(tool_input["ticker"])
    else:
        result = {"error": f"Unknown tool: {tool_name}"}
    return json.dumps(result, indent=2, default=str)
```

This is the switchboard. It receives the tool name and input dict that Claude chose, routes to the right Python function, and returns a JSON string. The string format matters: Claude reads it as text, so it needs to be human-readable enough for the model to parse and reason about.

## The agentic loop (`run_research`, `theta.py:177`)

This is where the three pieces come together. The loop keeps calling the API until Claude is done.

```
User prompt
    │
    ▼
messages.create(tools=TOOLS)
    │
    ├─ stop_reason == "tool_use"
    │       │
    │       ├── append assistant response to messages
    │       ├── execute each tool_use block → get result strings
    │       ├── append tool_results as a user message
    │       └── loop back → messages.create() again
    │
    └─ stop_reason == "end_turn"
            │
            └── extract text block → return summary
```

In detail, each iteration:

**Step 1 — Claude responds with tool calls.**
When `stop_reason == "tool_use"`, `response.content` contains one or more `ToolUseBlock` objects. Each has:
- `block.id` — a unique ID for this specific call (e.g. `toolu_01XYZ`)
- `block.name` — which tool (`"get_price_data"` or `"get_news"`)
- `block.input` — a dict matching the schema (e.g. `{"ticker": "AAPL"}`)

**Step 2 — Append the assistant turn.**
The full `response.content` (including the tool call blocks) is appended to `messages` as the assistant turn. This is required — Claude needs to see its own tool calls in the history to correctly interpret the results that follow.

**Step 3 — Execute and collect results.**
For each `ToolUseBlock`, `process_tool_call()` runs the Python function and returns a JSON string. Each result is wrapped as:

```python
{
    "type": "tool_result",
    "tool_use_id": block.id,   # must match the ToolUseBlock that requested it
    "content": result_str,
}
```

The `tool_use_id` linkage is how Claude knows which result answers which request. If you omit it or mismatch it, Claude gets confused about what data belongs to what question.

**Step 4 — Send results back as a user message.**
All `tool_result` dicts are bundled into a single user message and appended to `messages`. The API requires that tool results travel in a `user` role message — not `assistant`.

**Step 5 — Loop.**
`messages.create()` fires again with the full history: original user prompt → assistant tool calls → user tool results. Claude now has the data it needs and typically responds with `stop_reason == "end_turn"` and a text block containing the research summary.

## Why Claude calls both tools in one turn

In the AAPL run, you saw:

```
[tool] get_price_data(AAPL)
[tool] get_news(AAPL)
```

Both appeared before Claude wrote anything. That's parallel tool use — Claude emitted two `ToolUseBlock` objects in a single response, and the loop collected both results before the next API call. This is the default behaviour when Claude determines it needs multiple pieces of data and neither depends on the other. It's more efficient than two sequential round trips.

## What Claude actually sees

After the tool calls complete, the `messages` list looks like this before the final API call:

```python
[
    # Turn 1 — original user prompt
    {"role": "user", "content": "Research AAPL and suggest one options strategy."},

    # Turn 2 — Claude's tool requests
    {"role": "assistant", "content": [
        TextBlock(text="I'll fetch the data..."),   # optional preamble
        ToolUseBlock(id="toolu_01A", name="get_price_data", input={"ticker": "AAPL"}),
        ToolUseBlock(id="toolu_01B", name="get_news",       input={"ticker": "AAPL"}),
    ]},

    # Turn 3 — our tool results
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "toolu_01A", "content": "{...price JSON...}"},
        {"type": "tool_result", "tool_use_id": "toolu_01B", "content": "[...news JSON...]"},
    ]},
]
```

Claude reads all of this as context, treats the tool results as ground truth, and writes the final summary grounded in that data.

## What the tools actually return

**`get_price_data("AAPL")` — example output:**
```json
{
  "ticker": "AAPL",
  "current_price": 289.33,
  "previous_close": 280.14,
  "52_week_high": 292.13,
  "52_week_low": 193.46,
  "market_cap": 4393872703488,
  "pe_ratio": 35.07,
  "beta": 1.07,
  "volume": 17847392,
  "avg_volume": 44203400,
  "sector": "Technology",
  "industry": "Consumer Electronics",
  "1mo_return_pct": 14.15
}
```

Note: `implied_volatility` from `yf.Ticker.info` is often `None` for equities (it's more relevant for options themselves). This is why v0.2 will pull the actual options chain.

**`get_news("AAPL")` — example output (truncated):**
```json
[
  {
    "title": "Apple's restrained AI strategy gains investor confidence",
    "publisher": "Reuters",
    "summary": "Apple is taking a measured approach to AI...",
    "published": "2026-05-07T09:30:00Z"
  },
  ...
]
```

## Chat loop vs research loop

The chat loop (`chat_loop`, `theta.py:227`) does **not** use tools. Once the research summary exists, follow-up questions are answered purely from Claude's reasoning — the price data and news are already baked into the conversation history as the initial assistant turn. Adding tools to the chat loop would be v0.2 territory (e.g. re-fetching a fresh quote mid-conversation).

## Adding a new tool

See `CLAUDE.md` — the pattern is: write the function → add a schema entry to `TOOLS` → add a branch to `process_tool_call`. The loop picks it up automatically with no other changes.

---

## Tool specifications

Full input/output contracts for every tool. The Quick Reference table in `OVERVIEW.md §4` lists source, API key, and cache TTL.

```
Tool: get_price_data  [v0.1]
  Input:  ticker (str) — stock symbol, e.g. "AAPL"
  Output: {
    ticker, current_price, previous_close,
    high_52w, low_52w, market_cap, pe_ratio,
    implied_volatility, beta, volume, avg_volume,
    sector, industry, return_1mo_pct
  }
  Source: yfinance Ticker.info + Ticker.history(period="1mo")
  Notes:  Call once per session; cache result in agent state.
          implied_volatility from .info is often None for equities —
          v0.2 options chain provides contract-level IV.
```

```
Tool: get_news  [v0.1]
  Input:  ticker (str), max_items (int, default 8)
  Output: list of {
    title, publisher, summary, published_at, url
  }
  Source: yfinance Ticker.news
  Notes:  yfinance .news shape differs across versions — normalise
          both the legacy flat shape and the newer content{} shape.
          Summarise to 1 sentence per item before sending to Claude
          to keep token cost low.
```

```
Tool: get_options_chain  [v0.2]
  Input:  ticker (str)
  Output: {
    expiry (str, nearest expiry >= 14 days out),
    current_price (float),
    atm_iv (float),
    calls: [{strike, bid, ask, iv, volume, open_interest, delta, gamma, theta, vega}],  — top 5 by OI
    puts:  [{strike, bid, ask, iv, volume, open_interest, delta, gamma, theta, vega}]   — top 5 by OI
  }
  Source: yfinance Ticker.option_chain(expiry)
  Notes:  Filter to strikes within 10% of spot price before ranking by OI.
          Greeks computed via BSM using each contract's IV and DTE.
          Theta is per calendar day; vega is per 1% change in IV.
```

```
Tool: get_financials  [v0.4]
  Input:  ticker (str)
  Output: {
    valuation:     {pe_trailing, pe_forward, price_to_book, price_to_sales, ev_to_ebitda},
    profitability: {gross_margin, operating_margin, profit_margin, roe, roa},
    growth:        {revenue_growth_yoy, earnings_growth_yoy},
    balance_sheet: {debt_to_equity, current_ratio, quick_ratio},
    cash_flow:     {free_cash_flow, ebitda},
    dividends:     {yield, payout_ratio},
    analyst:       {target_price, recommendation, num_analysts}
  }
  Source: yfinance Ticker.info
  Notes:  All fields are optional — yfinance returns None for fields the
          exchange doesn't publish. Omit None fields before sending to Claude.
          Call once per session alongside get_price_data.
```

```
Tool: [MCP — brave_search]  [v0.7, planned]
  Input:  query (str), max_results (int, default 5)
  Output: list of {
    title, url, snippet, published_at
  }
  Source: Brave Search MCP server
  Key:    Brave API key (free tier: 2,000 queries/month)
  Notes:  Supplements yfinance news with broader web context.
          Useful for pre-earnings sentiment, analyst commentary, macro news.
          MCP server config lives in .mcp.json at project root.
```

```
Tool: get_ibkr_positions  [v0.8, planned]
  Input:
    account_id (str | None)  — if None, auto-fetched from /portfolio/accounts
    gateway_url (str)        — default: "https://localhost:5000"
  Output: {
    "account_id": "U1234567",
    "net_liquidation": 45230.50,
    "cash_balance": 8420.00,
    "positions": [
      {
        "symbol": "AAPL",
        "asset_class": "STK",
        "size": 100,
        "avg_cost": 178.40,
        "market_value": 19080.00,
        "unrealised_pnl": 1240.00
      },
      {
        "symbol": "AAPL",
        "asset_class": "OPT",
        "size": -1,
        "underlying": "AAPL",
        "expiry": "2025-06-20",
        "strike": 190.0,
        "right": "C",
        "avg_cost": 3.20,
        "market_value": -500.00,
        "unrealised_pnl": -180.00
      }
    ]
  }
  Source:    IBKR Client Portal Web API
  Endpoints: GET /v1/api/portfolio/accounts
             GET /v1/api/portfolio/{accountId}/positions/0
             GET /v1/api/portfolio/{accountId}/summary
  Auth:      CP Gateway session (localhost:5000) — no API key needed
  Fallback:  If gateway unreachable → return None, log warning, continue
  Notes:     Read-only; does not interrupt a live TWS/Client Portal session.
             gateway_url stored in config.py, never hardcoded.
             verify=False for localhost (self-signed cert).
             Run once per session and cache — positions don't change mid-analysis.
```
