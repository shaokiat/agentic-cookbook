"""Screener graph: strategy selection routes to a strategy-specific screening node."""

import os

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from .nodes import (
    fetch_iv_context,
    human_review,
    present_summary,
    screen_chain_csp,
    screen_chain_leaps,
    tag_thesis,
)
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


def build_graph(
    leaps_node=screen_chain_leaps,
    csp_node=screen_chain_csp,
    iv_node=fetch_iv_context,
    checkpointer=None,
):
    """Nodes are injectable so routing and wiring can be tested with stubs and no network."""
    g = StateGraph(ScreenerState)
    g.add_node("validate_selection", validate_selection)
    g.add_node("screen_chain_leaps", leaps_node)
    g.add_node("screen_chain_csp", csp_node)
    g.add_node("fetch_iv_context", iv_node)
    g.add_node("tag_thesis", tag_thesis)
    g.add_node("human_review", human_review)
    g.add_node("present_summary", present_summary)

    g.set_entry_point("validate_selection")
    g.add_conditional_edges(
        "validate_selection",
        route_by_strategy,
        {"long_leaps": "screen_chain_leaps", "csp": "screen_chain_csp"},
    )
    g.add_edge("screen_chain_leaps", "fetch_iv_context")
    g.add_edge("screen_chain_csp", "fetch_iv_context")
    g.add_edge("fetch_iv_context", "tag_thesis")
    g.add_edge("tag_thesis", "human_review")
    # reject ends the run without a summary; approve and resubmit fall through
    g.add_conditional_edges(
        "human_review",
        lambda s: "reject" if s.get("human_decision") == "reject" else "present_summary",
        {"reject": END, "present_summary": "present_summary"},
    )
    g.add_edge("present_summary", END)
    return g.compile(checkpointer=checkpointer)


# interrupt() needs a checkpointer to resume; MemorySaver is per-process (see #13).
compiled_graph = build_graph(checkpointer=MemorySaver())
