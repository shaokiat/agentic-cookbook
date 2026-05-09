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
| v0.6 | Modular tools | `tools/` directory with one file per tool; thin theta.py | refactored, no new tools | Low (refactor) |
| v0.7 | MCP integration | Brave Search MCP server; unified tool registry for native + MCP | `[mcp] brave_search` | Medium |
| v0.8 | IBKR positions | Read live account positions from IBKR Client Portal Web API; context-aware strategy suggestions against existing holdings | `get_ibkr_positions` | Medium |
| v1.0 | Production baseline | Error handling, rate limiting, response caching, `analyses/` JSON output, polished README | none new | Medium-high |

**Backlog (deferred, not scheduled):**
- SEC filings (`get_sec_filing`): 10-K/10-Q/8-K via EDGAR free API — parsing complexity and token cost outweigh marginal value over yfinance financial metrics
- Deep financial analysis: structured multi-dimensional analysis using data already retrieved by existing tools — cross-referencing valuation, growth, margins, analyst consensus, and options metrics into a comparative breakdown (e.g. vs sector peers, vs historical ranges); prompt engineering deferred
- Prompt/instruction evaluation: as each version adds richer context (Greeks, financial metrics, analyst data), evaluate whether the system prompt is using that context effectively — candidate approaches include: (1) LLM-as-judge scoring strategy outputs against a rubric (correct strategy family for IV regime, Greeks cited in rationale, financials used to qualify thesis); (2) golden-set regression — a small set of saved ticker snapshots with expected strategy fields, run after each prompt change to detect regressions; (3) ablation — compare outputs with and without a new context block to confirm Claude actually uses it rather than ignoring it

---

## 4. Tool Catalogue

### Quick Reference

| Tool | Introduced | Source | API Key | Cache TTL |
|---|---|---|---|---|
| `get_price_data` | v0.1 | yfinance | None | Session (once) |
| `get_news` | v0.1 | yfinance `.news` | None | 15 min |
| `get_options_chain` | v0.2 | yfinance `.option_chain` | None | 5 min |
| `get_financials` | v0.4 | yfinance `.info` | None | Session (once) |
| `[mcp] brave_search` | v0.7 | Brave Search MCP | Brave API key | 15 min |
| `get_ibkr_positions` | v0.8 | IBKR Client Portal Web API | None (CP Gateway session) | Session (once) |

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

## 7. System Prompt Versioning

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
| v0.7 | Instructions for prioritising Brave Search results over yfinance news when both are available |

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

Until a proper IV percentile calculation is available (requires historical data):
- **Low IV proxy:** implied_volatility from yfinance < 0.30, OR beta < 0.8
- **High IV proxy:** implied_volatility > 0.50, OR recent earnings/catalyst within 2 weeks
- When IV data is unavailable, Claude should note the limitation and default to defined-risk spreads

### Earnings Calendar Note

When news mentions an upcoming earnings report, Claude must:
1. Flag that IV crush risk exists post-earnings
2. Note whether the proposed strategy is long or short vega
3. Suggest the user evaluate whether to enter before or after the event

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

## 10. Extension Guide

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

## 11. Open Questions

These decisions are deliberately deferred. Resolve them at the version where they become necessary.

| Question | Deferred to | What's needed to decide |
|---|---|---|
| **Greeks library:** py_vollib_vectorized vs mibian vs manual BSM implementation | v0.3 | Benchmark accuracy and install friction; py_vollib_vectorized is fastest but has C dependencies |
| **News source quality:** yfinance news is shallow and sometimes stale | v0.7 | Evaluate Brave Search MCP vs NewsAPI vs Benzinga; key criteria are recency, summary quality, and cost at ~50 sessions/day |
| **Persistence format:** JSON files vs SQLite for saved analyses | v1.0 | JSON files are simpler and git-diffable; SQLite enables queries across sessions — decide based on whether cross-session analysis is a real use case |
| **Rate limiting strategy:** yfinance has undocumented rate limits | v1.0 | Measure in practice; add exponential backoff + per-session cache before adding a formal rate limiter |
| **Multi-ticker support:** side-by-side comparison or pairs trade suggestion | post-v1.0 | Requires rethinking the single-ticker thesis structure; defer until v1.0 is stable |
| **Authentication for web deployment:** if exposed as a web app, how do users supply their own API keys? | post-v1.0 | Requires a separate auth model; out of scope for CLI-first design |
| **Context window management:** long sessions will eventually overflow the context | v0.5 | Implement a sliding window or summarisation step in `chat_loop`; decide max token budget at that point |
