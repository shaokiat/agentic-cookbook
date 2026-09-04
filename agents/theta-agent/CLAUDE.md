# theta-agent

A LangGraph options screener: pick tickers and a strategy, get a ranked, thesis-tagged candidate
table with a mandatory human approval step.

**Domain language and resolved decisions:** [`CONTEXT.md`](CONTEXT.md) — read it first.

## How to run

theta-agent lives at `agents/theta-agent/` in the `agentic-cookbook` monorepo with its own
`pyproject.toml`. Dependencies belong in that file, **not** the repo root's.

```bash
cd agents/theta-agent
uv venv && uv pip install -e .
chainlit run ui/app.py
```

Tests run from the repo root against the root venv:

```bash
PYTHONPATH=agents/theta-agent .venv/bin/python -m pytest agents/theta-agent/tests/ -q
```

## Component map

```
theta-agent/
├── graph/
│   ├── state.py          ← ScreenerState, STRATEGY_DEFAULTS, LIQUIDITY_DEFAULTS
│   ├── nodes.py          ← screen_chain_leaps/_csp, fetch_iv_context (stub), tag_thesis
│   └── build.py          ← validate_selection, route_by_strategy, build_graph()
├── config/
│   └── themes.py         ← WATCHLIST + static per-ticker thematic tags (pure data)
├── tools/
│   ├── options.py        ← fetch_chain(): flat contract list in a DTE/moneyness window + BSM Greeks
│   └── price|news|financials|earnings|search.py
│                         ← pre-pivot data fetchers, still working, not yet wired into the graph
├── theta/
│   └── models.py         ← Pydantic models for the fetchers above
└── tests/
```

## Graph

```
validate_selection → <route_by_strategy> ─┬→ screen_chain_leaps ─┐
                                          └→ screen_chain_csp   ─┴→ fetch_iv_context
    → tag_thesis → human_review [interrupt()] → present_summary → END
```

`build_graph()` takes the screening nodes as arguments so routing can be tested with stubs and no
network. `compiled_graph` is the default wiring.

## Conventions

- **Nodes return a partial dict** of updated keys, never a mutated full state.
- **No thresholds inside nodes.** DTE, delta, OI, and spread limits come from `ScreenerState`,
  seeded by `STRATEGY_DEFAULTS` / `LIQUIDITY_DEFAULTS` in `validate_selection`. Caller-supplied
  values override defaults.
- **Never raise on a single ticker.** Append `{ticker, node, message}` to `state["errors"]` and
  continue.
- **Rendering belongs in `ui/app.py`**, never in a graph node.
- `THETA_ACCOUNT_SIZE` env var sets the CSP collateral ceiling (default 50000).
- Both screening nodes share `_screen()` in `graph/nodes.py`; strategy divergence is confined to
  `right`, `moneyness`, and a per-contract annotation callback. Do not fork it.
- `fetch_iv_context` is a **stub** marking every ticker favourable until #5/#9/#10 land.

## Status

| Issue | State |
|---|---|
| #2 docs purge, #3 `fetch_chain`, #4 state + routing | done |
| #7/#8 screening nodes, #11 `tag_thesis` | done |
| #6/#12/#14 Chainlit UI + `interrupt()` | next |
| #5 IV spike, #9/#10 `fetch_iv_context`, #13 checkpointing | blocked on a historical-IV API key |
