---
name: theta-agent-context
description: Domain language and resolved design decisions for the theta-agent screener
metadata:
  type: project
---

# theta-agent — Domain Context

## Core purpose

theta-agent is a **multi-ticker options screener**. The user picks a watchlist subset and one
strategy; the screener filters every name's chain against that strategy's DTE, delta, and
liquidity profile, annotates survivors with an IV regime read and a thematic tag, and presents
a ranked table for human approval. It is an ideation tool, not a trade executor.

It replaced a single-ticker conversational agent that derived one strategy from a five-signal
Signal Scorecard. That product is gone; see `CHANGELOG.md` v1.0.0.

## Key terms

**strategy_type**
`long_leaps` or `csp`. Chosen by the user *before* the graph runs — it selects the branch taken
at the `route_by_strategy` conditional edge, and the DTE/delta parameter set applied to every
downstream node.

**Long ITM LEAPS**
DTE > 500, delta 0.70–0.85 calls. A stock substitute: high delta, low time decay per day,
less capital than shares. Favourable when IV is **low** — you are buying vega.

**Cash-Secured Put (CSP)**
DTE 30–45, delta 0.15–0.30 puts, fully collateralised. Favourable when IV is **high** — you are
selling vega. Collateral is `strike × 100` per contract.

**iv_rank / iv_percentile**
Where a name's current IV sits against its own trailing IV history. Rank is position within the
min–max range; percentile is the fraction of history below today. Time-series measures, computed
from an external historical-IV source — not derivable from a single day's chain.

**favorable**
Per-ticker boolean from `fetch_iv_context`. Direction depends on `strategy_type`: low IV is
favourable for `long_leaps`, high IV for `csp`. The same node computes both — only the threshold
comparison flips.

**theme**
A static, human-authored thematic tag per ticker (`config/themes.py`), e.g. `MU →
memory_supercycle_bullish`. The screener tags candidates with a *pre-existing* view; it does not
generate one. No LLM call is involved.

**collateral_flag**
Set on a CSP candidate whose collateral exceeds the configured account size. Flagged, never
dropped — you may want to see it in order to trim another position first.

**Human approval checkpoint**
A LangGraph `interrupt()` after `tag_thesis`. The graph pauses, surfaces candidates, and resumes
only on an explicit approve / reject / resubmit. Nothing is auto-approved, including a single
surviving candidate.

## Resolved design decisions

- **Chain data is yfinance**, via `tools/options.py::fetch_chain`. IBKR is out of scope: the IBKR
  tools available inside a Claude chat are MCP connectors, not importable Python. Consequence —
  no live buying power; CSP collateral is checked against a static configured account size.
- **IV rank replaced `iv_excess`.** The old cross-sectional measure (contract IV minus an OLS
  surface fit) answered "is this contract rich relative to its neighbours today". Screening needs
  "is this name's IV high relative to its own history", which is a different question.
- **Strategy is selected, not derived.** The scorecard's job was choosing a strategy for one
  ticker. The screener inverts this: the strategy is the input, and the output is which names fit it.
- **Strategy parameters live in `ScreenerState`, not in nodes.** `dte_min`, `dte_max`,
  `delta_range`, and the liquidity thresholds are state fields so both branches share the
  downstream nodes. This is the mechanism for adding a third strategy.
- **Nodes return partial state dicts**, never a mutated full state — required for correctness
  once any two nodes run in parallel.
- **Per-ticker failures accumulate in `state["errors"]`** and are surfaced with the results. A
  sweep of 19 names must not die on one delisted ticker, and must not silently hide six failures.
