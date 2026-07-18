---
name: theta-agent-context
description: Domain language and resolved design decisions for theta-agent
metadata:
  type: project
---

# theta-agent — Domain Context

## Core purpose

theta-agent is a research head-start tool for retail options traders. Given a ticker, it produces a directional verdict, a signal scorecard, and one concrete strategy recommendation, then opens a free-form chat for the user to explore that strategy. It is an ideation tool, not a trade executor.

## Key terms

**Signal Scorecard**
The structured output of the research phase. Five signals scored 1–10, displayed in reasoning-chain order: Directional Bias → Event Clarity → IV Regime → Conviction → Liquidity. All five signals read higher = better setup. A one-line directional verdict is printed before the scorecard as a headline.

**Directional Bias**
Signal 1. Measures bull/bear/neutral conviction from price trend, RSI-14, financials, analyst consensus, and news. 1=strong bear, 5=neutral, 10=strong bull. RSI > 75 is an overbought warning; caps bullish score at 8 unless all other signals are exceptionally strong.

**Event Clarity**
Signal 2. Measures how clean the target expiry window is from binary events. 10=no near-term catalyst, 1=earnings imminent inside expiry. Higher = better (deliberately inverted from the intuitive "Event Risk" framing to match the other four signals). Low Event Clarity (≤ 3) mandates defined-risk structures.

**IV Regime**
Signal 3. Measures whether options are rich or cheap via `iv_excess` (contract IV minus OLS surface fit), enriched by `skew` (OTM put IV − OTM call IV at ~0.25 delta). Positive skew = puts richer than calls = elevated downside hedging demand. 1=very cheap, 10=very rich.

**Conviction**
Signal 4. Measures internal signal agreement — how many sub-signals (price, RSI, news, fundamentals, analyst consensus, short interest) align with the directional score. Short interest is always named explicitly as a sub-signal when data is available. Controls strike width and delta: high conviction → ATM-adjacent; low conviction → further OTM.

**Liquidity**
Signal 5. Execution quality at target strikes — bid-ask spread as % of mid and open interest. Controls whether to warn about fill slippage.

**iv_excess**
A contract's actual IV minus the OLS-fitted IV from the surface model (`IV ≈ a + b·m + c·m² + d·√T + e·m·√T`). Positive = IV rich (favours selling); negative = IV cheap (favours buying). Primary signal for contract selection within the chosen strategy family.

**skew**
Average IV of OTM puts (~0.25 delta) minus average IV of OTM calls (~0.25 delta), computed from the first expiry. Positive skew = downside hedging demand elevated. Reported alongside `iv_excess` in the IV Regime signal.

**RSI-14**
14-period Wilder RSI computed from 3 months of daily closes. Reported in Directional Bias as a momentum/overbought-oversold sub-signal. > 75 = overbought warning; < 25 = oversold support.

**HITL chat**
Phase 2 of a theta-agent session. After the scorecard and strategy recommendation, the user enters a free-form REPL to interrogate the recommended strategy — stress-test scenarios, adjust parameters, ask about mechanics. The chat carries the full research context (tool results, scorecard, recommendation) without re-fetching data. It is for depth on the chosen strategy, not for selecting between alternatives.

**one strategy**
theta-agent always recommends exactly one strategy per session. The scorecard eliminates alternatives; the "Why not X" fields record the rejected strategies and their reasons. The chat loop is the mechanism for challenging the recommendation, not for picking between options.

## Resolved design decisions

- **One strategy, not multiple candidates** — the scorecard framework does the selection work; surfacing multiple strategies shifts the cognitive load back to the user without adding value.
- **Event Risk renamed to Event Clarity, scale inverted** — all five signals now read higher = better setup; prevents misreading a low Event Risk score as "low quality."
- **Signal display order** — Directional → Event Clarity → IV Regime → Conviction → Liquidity, matching the reasoning chain so readers see event context before interpreting IV numbers.
- **Confidence qualifier dropped** — data quality caveats appear inline in the Against field only when genuinely low; "High" confidence on every signal added noise without value.
- **Enrich existing signals rather than add a 6th** — RSI added to Directional Bias; short interest promoted to named sub-signal in Conviction; skew added to IV Regime. No new signals, no new data sources.
