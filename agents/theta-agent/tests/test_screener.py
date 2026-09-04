"""Unit tests for the screener chain fetch and graph routing — no network calls."""

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from graph.build import build_graph, validate_selection
from graph.state import STRATEGY_DEFAULTS
from tools.options import fetch_chain

COLS = ["strike", "bid", "ask", "impliedVolatility", "volume", "openInterest"]


def _row(strike, bid=1.0, ask=1.1, iv=0.30, vol=10, oi=500):
    return {"strike": strike, "bid": bid, "ask": ask,
            "impliedVolatility": iv, "volume": vol, "openInterest": oi}


def _mock_ticker(spot, calls, puts, dtes=(600,)):
    t = MagicMock()
    t.info = {"currentPrice": spot}
    t.options = [(date.today() + timedelta(days=d)).isoformat() for d in dtes]
    t.option_chain.return_value = SimpleNamespace(
        calls=pd.DataFrame(calls, columns=COLS),
        puts=pd.DataFrame(puts, columns=COLS),
    )
    return t


class TestFetchChain:
    def test_deep_itm_leaps_strikes_are_reachable(self):
        """The old ±15% moneyness band excluded 0.70-0.85 delta calls entirely."""
        with patch("tools.options.yf.Ticker", return_value=_mock_ticker(100.0, [_row(60.0)], [])):
            r = fetch_chain("FAKE", dte_min=500, right="C", moneyness=(0.5, 1.05))
        assert [c["strike"] for c in r["contracts"]] == [60.0]
        assert r["contracts"][0]["delta"] > 0.85  # 60 strike on a 100 spot is deep ITM

    def test_dte_window_excludes_out_of_range_expiries(self):
        with patch("tools.options.yf.Ticker",
                   return_value=_mock_ticker(100.0, [_row(100.0)], [], dtes=(10, 35, 600))):
            r = fetch_chain("FAKE", dte_min=30, dte_max=45, right="C")
        assert {c["dte"] for c in r["contracts"]} == {35}

    def test_right_filter_returns_puts_only(self):
        with patch("tools.options.yf.Ticker",
                   return_value=_mock_ticker(100.0, [_row(100.0)], [_row(90.0)], dtes=(35,))):
            r = fetch_chain("FAKE", dte_min=30, dte_max=45, right="P")
        assert [c["right"] for c in r["contracts"]] == ["P"]
        assert r["contracts"][0]["delta"] < 0  # put delta is negative

    def test_zero_bid_contract_does_not_raise(self):
        with patch("tools.options.yf.Ticker",
                   return_value=_mock_ticker(100.0, [_row(60.0, bid=0.0, ask=0.0)], [])):
            r = fetch_chain("FAKE", dte_min=500, moneyness=(0.5, 1.05))
        assert r["error"] is None
        assert r["contracts"][0]["spread_pct"] is None

    def test_nan_fields_become_none_or_zero(self):
        with patch("tools.options.yf.Ticker",
                   return_value=_mock_ticker(100.0, [_row(100.0, iv=float("nan"), oi=float("nan"))], [], dtes=(35,))):
            r = fetch_chain("FAKE", dte_min=30, dte_max=45)
        c = r["contracts"][0]
        assert c["iv"] is None and c["open_interest"] == 0 and "delta" not in c

    def test_no_expiries_in_window_returns_empty_not_raise(self):
        with patch("tools.options.yf.Ticker",
                   return_value=_mock_ticker(100.0, [_row(100.0)], [], dtes=(10,))):
            r = fetch_chain("FAKE", dte_min=500)
        assert r["contracts"] == [] and "DTE window" in r["error"]

    def test_invalid_ticker_returns_error_not_raise(self):
        with patch("tools.options.yf.Ticker", side_effect=Exception("no such ticker")):
            r = fetch_chain("NOPE", dte_min=500)
        assert r["contracts"] == [] and "no such ticker" in r["error"]


class TestGraphRouting:
    def _graph(self):
        seen = []
        g = build_graph(
            leaps_node=lambda s: seen.append("leaps") or {"raw_chains": {}},
            csp_node=lambda s: seen.append("csp") or {"raw_chains": {}},
        )
        return g, seen

    @pytest.mark.parametrize("strategy,expected", [("long_leaps", "leaps"), ("csp", "csp")])
    def test_routes_to_correct_branch(self, strategy, expected):
        g, seen = self._graph()
        g.invoke({"selected_tickers": ["MU"], "strategy_type": strategy})
        assert seen == [expected]

    def test_applies_per_strategy_defaults(self):
        for strategy, defaults in STRATEGY_DEFAULTS.items():
            out = validate_selection({"selected_tickers": ["MU"], "strategy_type": strategy})
            for k, v in defaults.items():
                assert out[k] == v

    def test_caller_override_wins_over_default(self):
        out = validate_selection({"selected_tickers": ["MU"], "strategy_type": "csp", "dte_min": 7})
        assert "dte_min" not in out  # left untouched, caller's value survives the merge

    def test_tickers_uppercased_and_deduped(self):
        out = validate_selection({"selected_tickers": [" mu ", "MU", "nvda"], "strategy_type": "csp"})
        assert out["selected_tickers"] == ["MU", "NVDA"]

    @pytest.mark.parametrize("bad", [
        {"selected_tickers": [], "strategy_type": "csp"},
        {"selected_tickers": ["MU"], "strategy_type": "straddle"},
    ])
    def test_rejects_invalid_input(self, bad):
        with pytest.raises(ValueError):
            validate_selection(bad)


# ---------------------------------------------------------------------------
# Screening nodes
# ---------------------------------------------------------------------------

from graph.nodes import fetch_iv_context, screen_chain_csp, screen_chain_leaps, tag_thesis

BASE = {
    "selected_tickers": ["FAKE"],
    "min_open_interest": 100,
    "max_spread_pct": 0.08,
    "account_size": 50_000.0,
    "dte_max": None,
}
LEAPS_STATE = {**BASE, "strategy_type": "long_leaps", "dte_min": 500, "delta_range": (0.70, 0.85)}
CSP_STATE = {**BASE, "strategy_type": "csp", "dte_min": 30, "dte_max": 45, "delta_range": (0.15, 0.30)}


def _contract(**over):
    c = {"ticker": "FAKE", "strike": 100.0, "expiry": "2027-01-15", "dte": 500, "right": "C",
         "bid": 10.0, "ask": 10.2, "mid": 10.1, "spread_pct": 0.02, "iv": 0.3,
         "open_interest": 500, "volume": 10, "delta": 0.80}
    c.update(over)
    return c


def _chain(*contracts, error=None):
    return {"ticker": "FAKE", "current_price": 100.0, "contracts": list(contracts), "error": error}


class TestScreeningNodes:
    def test_leaps_keeps_in_delta_liquid_contract_and_adds_breakeven(self):
        with patch("graph.nodes.fetch_chain", return_value=_chain(_contract())):
            out = screen_chain_leaps(LEAPS_STATE)
        assert out["raw_chains"]["FAKE"][0]["breakeven"] == 110.1

    @pytest.mark.parametrize("over", [
        {"delta": 0.50},                      # out of delta range
        {"open_interest": 5},                 # illiquid
        {"spread_pct": 0.40},                 # wide spread
        {"spread_pct": None},                 # no valid mid — unquotable, not tight
        {"delta": None},                      # no IV, so no Greeks
    ])
    def test_leaps_rejects(self, over):
        with patch("graph.nodes.fetch_chain", return_value=_chain(_contract(**over))):
            out = screen_chain_leaps(LEAPS_STATE)
        assert out["raw_chains"]["FAKE"] == []

    def test_csp_handles_negative_put_delta(self):
        """Comparing a raw negative delta against (0.15, 0.30) silently returns nothing."""
        put = _contract(right="P", delta=-0.20, strike=90.0, dte=35)
        with patch("graph.nodes.fetch_chain", return_value=_chain(put)):
            out = screen_chain_csp(CSP_STATE)
        assert len(out["raw_chains"]["FAKE"]) == 1

    def test_csp_flags_rather_than_drops_unaffordable_collateral(self):
        put = _contract(right="P", delta=-0.20, strike=900.0, dte=35)
        with patch("graph.nodes.fetch_chain", return_value=_chain(put)):
            out = screen_chain_csp(CSP_STATE)
        c = out["raw_chains"]["FAKE"][0]
        assert c["collateral_required"] == 90_000.0
        assert c["collateral_flag"] == "insufficient_capital"

    def test_affordable_collateral_is_unflagged(self):
        put = _contract(right="P", delta=-0.20, strike=90.0, dte=35)
        with patch("graph.nodes.fetch_chain", return_value=_chain(put)):
            out = screen_chain_csp(CSP_STATE)
        assert "collateral_flag" not in out["raw_chains"]["FAKE"][0]

    def test_fetch_failure_is_collected_not_raised(self):
        with patch("graph.nodes.fetch_chain", return_value=_chain(error="delisted")):
            out = screen_chain_leaps({**LEAPS_STATE, "selected_tickers": ["FAKE", "OK"]})
        assert out["raw_chains"] == {"FAKE": [], "OK": []}
        assert [e["message"] for e in out["errors"]] == ["delisted", "delisted"]

    def test_both_nodes_read_the_same_liquidity_keys(self):
        """Guards against the thresholds drifting apart across the two branches."""
        tight = {"min_open_interest": 10_000, "max_spread_pct": 0.001}
        put = _contract(right="P", delta=-0.20, dte=35)
        with patch("graph.nodes.fetch_chain", return_value=_chain(_contract())):
            assert screen_chain_leaps({**LEAPS_STATE, **tight})["raw_chains"]["FAKE"] == []
        with patch("graph.nodes.fetch_chain", return_value=_chain(put)):
            assert screen_chain_csp({**CSP_STATE, **tight})["raw_chains"]["FAKE"] == []


class TestTagThesis:
    def _state(self, **over):
        s = {"strategy_type": "long_leaps",
             "raw_chains": {"MU": [_contract(ticker="MU")], "ZZZZ": [_contract(ticker="ZZZZ")]},
             "iv_annotated": {"MU": {"favorable": True, "iv_rank": 20.0},
                              "ZZZZ": {"favorable": True, "iv_rank": 40.0}}}
        s.update(over)
        return s

    def test_known_ticker_gets_its_theme(self):
        out = tag_thesis(self._state())
        assert {c["ticker"]: c["theme"] for c in out["thesis_tagged"]}["MU"] == "memory_supercycle_bullish"

    def test_unknown_ticker_is_untagged_not_dropped(self):
        out = tag_thesis(self._state())
        assert {c["ticker"]: c["theme"] for c in out["thesis_tagged"]}["ZZZZ"] == "untagged"

    def test_unfavorable_ticker_excluded(self):
        s = self._state()
        s["iv_annotated"]["ZZZZ"]["favorable"] = False
        assert [c["ticker"] for c in tag_thesis(s)["thesis_tagged"]] == ["MU"]

    def test_sort_direction_flips_with_strategy(self):
        assert [c["iv_rank"] for c in tag_thesis(self._state())["thesis_tagged"]] == [20.0, 40.0]
        assert [c["iv_rank"] for c in tag_thesis(self._state(strategy_type="csp"))["thesis_tagged"]] == [40.0, 20.0]

    def test_none_iv_rank_sorts_last_and_does_not_raise(self):
        s = self._state()
        s["iv_annotated"]["MU"]["iv_rank"] = None
        assert [c["iv_rank"] for c in tag_thesis(s)["thesis_tagged"]] == [40.0, None]

    def test_no_favorable_tickers_returns_empty(self):
        s = self._state()
        for v in s["iv_annotated"].values():
            v["favorable"] = False
        assert tag_thesis(s)["thesis_tagged"] == []


class TestIVStub:
    def test_stub_marks_tickers_with_candidates_favorable(self):
        out = fetch_iv_context({"raw_chains": {"MU": [_contract()], "NONE": []}})
        assert out["iv_annotated"]["MU"]["favorable"] is True
        assert "NONE" not in out["iv_annotated"]
