"""Screener state schema and per-strategy parameter defaults."""

from typing import Literal, Optional, TypedDict

StrategyType = Literal["long_leaps", "csp"]


class ScreenerState(TypedDict, total=False):
    # Input
    selected_tickers: list[str]
    strategy_type: StrategyType

    # Strategy parameters — applied by validate_selection, never hardcoded in nodes.
    # Keeping these in state is what lets a third strategy reuse the downstream nodes.
    dte_min: int
    dte_max: Optional[int]
    delta_range: tuple[float, float]
    min_open_interest: int
    max_spread_pct: float
    account_size: float

    # Accumulated
    raw_chains: dict[str, list[dict]]
    iv_annotated: dict[str, dict]
    thesis_tagged: list[dict]
    errors: list[dict]

    # Human-in-the-loop
    human_decision: Optional[Literal["approve", "reject", "resubmit"]]
    human_selected_subset: Optional[list[str]]

    # Output
    final_candidates: list[dict]


STRATEGY_DEFAULTS: dict[str, dict] = {
    "long_leaps": {
        "dte_min": 500,
        "dte_max": None,
        "delta_range": (0.70, 0.85),
    },
    "csp": {
        "dte_min": 30,
        "dte_max": 45,
        "delta_range": (0.15, 0.30),
    },
}

# Starting values — long-dated LEAPS are thin, expect to loosen these against live data.
LIQUIDITY_DEFAULTS = {
    "min_open_interest": 100,
    "max_spread_pct": 0.08,
}

DEFAULT_ACCOUNT_SIZE = 50_000.0
