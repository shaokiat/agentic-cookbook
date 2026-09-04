"""Screening and annotation nodes. Each returns a partial state dict."""

from langgraph.types import interrupt

from config.themes import WATCHLIST_THEMES
from tools.options import fetch_chain

from .state import ScreenerState


def _liquid(contract: dict, state: ScreenerState) -> bool:
    if contract["open_interest"] < state["min_open_interest"]:
        return False
    spread = contract["spread_pct"]
    # spread_pct is None when there is no valid mid — unquotable, not tight
    return spread is not None and spread <= state["max_spread_pct"]


def _screen(state: ScreenerState, node: str, right: str, moneyness: tuple[float, float], per_contract=None) -> dict:
    """Shared tier-1 filter. Strategy divergence lives in `right`, `moneyness`, `per_contract`."""
    lo, hi = state["delta_range"]
    raw_chains: dict[str, list[dict]] = {}
    errors: list[dict] = []

    for ticker in state["selected_tickers"]:
        result = fetch_chain(
            ticker,
            dte_min=state["dte_min"],
            dte_max=state.get("dte_max"),
            right=right,
            moneyness=moneyness,
        )
        if result["error"]:
            errors.append({"ticker": ticker, "node": node, "message": result["error"]})
            raw_chains[ticker] = []
            continue

        candidates = []
        for c in result["contracts"]:
            delta = c.get("delta")
            if delta is None or not (lo <= abs(delta) <= hi):
                continue
            if not _liquid(c, state):
                continue
            if per_contract:
                per_contract(c, state)
            candidates.append(c)
        raw_chains[ticker] = candidates

    return {"raw_chains": raw_chains, "errors": errors}


def screen_chain_leaps(state: ScreenerState) -> dict:
    def annotate(c: dict, _state: ScreenerState) -> None:
        c["breakeven"] = round(c["strike"] + c["mid"], 2)

    return _screen(state, "screen_chain_leaps", "C", (0.5, 1.05), annotate)


def screen_chain_csp(state: ScreenerState) -> dict:
    def annotate(c: dict, s: ScreenerState) -> None:
        c["collateral_required"] = c["strike"] * 100
        if c["collateral_required"] > s["account_size"]:
            # Flagged, not dropped — you may want to trim another position to fit it.
            c["collateral_flag"] = "insufficient_capital"

    return _screen(state, "screen_chain_csp", "P", (0.7, 1.0), annotate)


def fetch_iv_context(state: ScreenerState) -> dict:
    """Stub until a historical-IV source lands (#5, #9, #10). Marks every ticker favourable."""
    return {
        "iv_annotated": {
            ticker: {"iv_rank": None, "iv_percentile": None, "favorable": True,
                     "reason": "iv_source_not_configured"}
            for ticker, contracts in state["raw_chains"].items() if contracts
        }
    }


def tag_thesis(state: ScreenerState) -> dict:
    tagged = []
    for ticker, iv in state["iv_annotated"].items():
        if not iv.get("favorable"):
            continue
        for c in state["raw_chains"].get(ticker, []):
            tagged.append({**c,
                           "theme": WATCHLIST_THEMES.get(ticker, "untagged"),
                           "iv_rank": iv["iv_rank"]})

    # Sorted here so the presentation layer stays dumb. Cheap premium first for LEAPS,
    # rich premium first for CSP; None iv_rank sorts last either way.
    ascending = state["strategy_type"] == "long_leaps"
    tagged.sort(key=lambda c: (c["iv_rank"] is None,
                               c["iv_rank"] if ascending else -(c["iv_rank"] or 0)))
    return {"thesis_tagged": tagged}


def human_review(state: ScreenerState) -> dict:
    """Pauses the graph. Kept free of side effects — interrupt() re-runs the node on resume."""
    decision = interrupt({
        "candidates": state["thesis_tagged"],
        "strategy_type": state["strategy_type"],
        "errors": state.get("errors", []),
        "message": "Review candidates before finalizing.",
    })
    return {
        "human_decision": decision.get("action"),
        "human_selected_subset": decision.get("selected_subset"),
    }


def present_summary(state: ScreenerState) -> dict:
    if state.get("human_decision") != "approve":
        return {"final_candidates": []}
    subset = state.get("human_selected_subset")
    candidates = state["thesis_tagged"]
    if subset:
        candidates = [c for c in candidates if c["ticker"] in set(subset)]
    return {"final_candidates": candidates}
