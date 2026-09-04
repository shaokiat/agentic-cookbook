# theta-agent

A multi-ticker options screener. Pick a watchlist subset and one strategy; get back a ranked,
thesis-tagged candidate table with a mandatory human approval step before anything is finalised.

Two strategies ship:

| Strategy | Window | Delta | Favourable IV |
|---|---|---|---|
| Long ITM LEAPS | DTE > 500 | 0.70–0.85 calls | Low — buying vega |
| Cash-Secured Put | DTE 30–45 | 0.15–0.30 puts | High — selling vega |

Orchestrated with LangGraph: a conditional edge routes on the selected strategy, and an
`interrupt()` pauses the graph for human review before the final table.

> **v1.0 is a pivot.** theta-agent was previously a single-ticker conversational agent that
> derived one strategy from a five-signal Signal Scorecard. That product and its CLI/TUI entry
> points were removed — see `CHANGELOG.md`.

## Quickstart

theta-agent lives inside the [agentic-cookbook](../../) monorepo's `agents/` directory as a
standalone example, with its own dependencies and virtualenv.

```bash
git clone https://github.com/shaokiat/agentic-cookbook.git
cd agentic-cookbook/agents/theta-agent
uv venv && uv pip install -e .
source .venv/bin/activate
chainlit run ui/app.py
```

From the monorepo root, `make theta-ui` does the same on port 8001 — it uses this project's
venv when one exists and the cookbook's root venv otherwise.

Requires Python ≥ 3.11.

## Pipeline

```
validate_selection → <route_by_strategy> ─┬→ screen_chain_leaps ─┐
                                          └→ screen_chain_csp   ─┴→ fetch_iv_context
    → tag_thesis → human_review [interrupt()] → present_summary → END
```

| Node | Does |
|---|---|
| `validate_selection` | Normalises tickers, applies the strategy's DTE/delta/liquidity defaults |
| `screen_chain_leaps` / `screen_chain_csp` | Tier-1 filter: DTE, delta, open interest, bid-ask spread |
| `fetch_iv_context` | IV rank/percentile per ticker; flags each favourable or not for the strategy |
| `tag_thesis` | Annotates survivors with a static thematic tag from `config/themes.py` |
| `human_review` | Pauses for approve / reject / resubmit — nothing is auto-approved |

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `THETA_ACCOUNT_SIZE` | Collateral ceiling for CSP candidates | `50000` |
| `BRAVE_API_KEY` | Optional — enables the `search_web` fetcher | unset |

Chain data comes from yfinance. There is no live brokerage connection, so CSP collateral is
checked against `THETA_ACCOUNT_SIZE` rather than real buying power.

## Tests

```bash
# from the repo root
PYTHONPATH=agents/theta-agent .venv/bin/python -m pytest agents/theta-agent/tests/ -q
```

## Known limitations

- Ticker selection is a validated comma-separated list, not a multi-select widget — Chainlit's
  `AskActionMessage` is single-select and a custom element wasn't worth it for v1.
- `Re-screen` at the approval step is not implemented; it currently ends the run.
- No live buying power — collateral is checked against a static configured account size.
- `MemorySaver` is per-process: restarting the server loses an in-flight run.
- IV rank requires an external historical-IV source; until that lands, `fetch_iv_context` is a
  pass-through stub that marks every ticker favourable.
