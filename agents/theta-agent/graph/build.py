"""Screener graph: strategy selection routes to a strategy-specific screening node."""

import os

from langgraph.graph import END, StateGraph

from .state import (
    DEFAULT_ACCOUNT_SIZE,
    LIQUIDITY_DEFAULTS,
    STRATEGY_DEFAULTS,
    ScreenerState,
)


def validate_selection(state: ScreenerState) -> dict:
    tickers = [t.strip().upper() for t in state.get("selected_tickers", []) if t.strip()]
    if not tickers:
        raise ValueError("No tickers selected")

    strategy = state.get("strategy_type")
    if strategy not in STRATEGY_DEFAULTS:
        raise ValueError(f"Unknown strategy_type: {strategy!r}")

    defaults = {
        **STRATEGY_DEFAULTS[strategy],
        **LIQUIDITY_DEFAULTS,
        "account_size": float(os.environ.get("THETA_ACCOUNT_SIZE", DEFAULT_ACCOUNT_SIZE)),
    }
    # Caller-supplied overrides win; defaults only fill what is absent.
    return {
        "selected_tickers": list(dict.fromkeys(tickers)),
        **{k: v for k, v in defaults.items() if k not in state},
        "raw_chains": {},
        "errors": [],
    }


def route_by_strategy(state: ScreenerState) -> str:
    return state["strategy_type"]


def _stub(state: ScreenerState) -> dict:
    return {}


def build_graph(
    screen_chain_leaps=_stub,
    screen_chain_csp=_stub,
    checkpointer=None,
):
    g = StateGraph(ScreenerState)
    g.add_node("validate_selection", validate_selection)
    g.add_node("screen_chain_leaps", screen_chain_leaps)
    g.add_node("screen_chain_csp", screen_chain_csp)

    g.set_entry_point("validate_selection")
    g.add_conditional_edges(
        "validate_selection",
        route_by_strategy,
        {"long_leaps": "screen_chain_leaps", "csp": "screen_chain_csp"},
    )
    g.add_edge("screen_chain_leaps", END)
    g.add_edge("screen_chain_csp", END)
    return g.compile(checkpointer=checkpointer)


compiled_graph = build_graph()
