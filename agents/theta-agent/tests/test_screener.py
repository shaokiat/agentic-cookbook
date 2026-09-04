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
            screen_chain_leaps=lambda s: seen.append("leaps") or {},
            screen_chain_csp=lambda s: seen.append("csp") or {},
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
