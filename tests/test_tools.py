"""
Unit tests for theta/tools.py — no network calls.

Coverage:
  - get_options_chain: strike filtering, top-5-by-OI ranking, atm_iv selection, Greeks
  - get_news: legacy flat shape and newer content{} shape
  - get_financials: field mapping, None exclusion, error handling
  - process_tool_call: known tool dispatch and unknown tool error handling
"""

import json
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from theta.tools import get_financials, get_news, get_options_chain, process_tool_call


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chain(calls_rows: list[dict], puts_rows: list[dict]) -> SimpleNamespace:
    """Return a fake option_chain result with .calls and .puts DataFrames."""
    cols = ["strike", "bid", "ask", "impliedVolatility", "volume", "openInterest"]
    return SimpleNamespace(
        calls=pd.DataFrame(calls_rows, columns=cols),
        puts=pd.DataFrame(puts_rows, columns=cols),
    )


def _expiry_days_out(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# get_options_chain — strike filtering
# ---------------------------------------------------------------------------

class TestStrikeFiltering:
    """Strikes outside 10% of spot must be excluded."""

    def test_out_of_range_strikes_excluded(self):
        spot = 100.0
        # strike at 80 (20% below) and 125 (25% above) should both be dropped
        calls = [
            {"strike": 80.0,  "bid": 1.0, "ask": 1.1, "impliedVolatility": 0.25, "volume": 500, "openInterest": 1000},
            {"strike": 100.0, "bid": 2.0, "ask": 2.1, "impliedVolatility": 0.25, "volume": 300, "openInterest": 800},
            {"strike": 125.0, "bid": 0.5, "ask": 0.6, "impliedVolatility": 0.25, "volume": 200, "openInterest": 600},
        ]
        puts = []

        mock_ticker = MagicMock()
        mock_ticker.info = {"currentPrice": spot}
        mock_ticker.options = [_expiry_days_out(30)]
        mock_ticker.option_chain.return_value = _make_chain(calls, puts)

        with patch("theta.tools.yf.Ticker", return_value=mock_ticker):
            result = get_options_chain("FAKE")

        strikes = [c["strike"] for c in result["calls"]]
        assert 80.0 not in strikes
        assert 125.0 not in strikes
        assert 100.0 in strikes

    def test_boundary_strikes_included(self):
        """Strikes exactly at 90% and 110% of spot are within range."""
        spot = 100.0
        calls = [
            {"strike": 90.0,  "bid": 1.0, "ask": 1.1, "impliedVolatility": 0.3, "volume": 100, "openInterest": 500},
            {"strike": 110.0, "bid": 1.0, "ask": 1.1, "impliedVolatility": 0.3, "volume": 100, "openInterest": 400},
        ]
        puts = []

        mock_ticker = MagicMock()
        mock_ticker.info = {"currentPrice": spot}
        mock_ticker.options = [_expiry_days_out(30)]
        mock_ticker.option_chain.return_value = _make_chain(calls, puts)

        with patch("theta.tools.yf.Ticker", return_value=mock_ticker):
            result = get_options_chain("FAKE")

        strikes = [c["strike"] for c in result["calls"]]
        assert 90.0 in strikes
        assert 110.0 in strikes


# ---------------------------------------------------------------------------
# get_options_chain — top-5-by-OI ranking
# ---------------------------------------------------------------------------

class TestOpenInterestRanking:
    """Only the top 5 contracts by open interest should be returned."""

    def test_returns_at_most_five_contracts(self):
        spot = 100.0
        calls = [
            {"strike": 95.0 + i, "bid": 1.0, "ask": 1.1, "impliedVolatility": 0.25,
             "volume": 100, "openInterest": 1000 - i * 10}
            for i in range(8)  # 8 valid strikes, only top 5 should survive
        ]
        puts = []

        mock_ticker = MagicMock()
        mock_ticker.info = {"currentPrice": spot}
        mock_ticker.options = [_expiry_days_out(30)]
        mock_ticker.option_chain.return_value = _make_chain(calls, puts)

        with patch("theta.tools.yf.Ticker", return_value=mock_ticker):
            result = get_options_chain("FAKE")

        assert len(result["calls"]) == 5

    def test_highest_oi_contracts_are_kept(self):
        spot = 100.0
        calls = [
            {"strike": 98.0, "bid": 1.0, "ask": 1.1, "impliedVolatility": 0.25, "volume": 100, "openInterest": 5000},
            {"strike": 99.0, "bid": 1.0, "ask": 1.1, "impliedVolatility": 0.25, "volume": 100, "openInterest": 4000},
            {"strike": 100.0,"bid": 1.0, "ask": 1.1, "impliedVolatility": 0.25, "volume": 100, "openInterest": 3000},
            {"strike": 101.0,"bid": 1.0, "ask": 1.1, "impliedVolatility": 0.25, "volume": 100, "openInterest": 2000},
            {"strike": 102.0,"bid": 1.0, "ask": 1.1, "impliedVolatility": 0.25, "volume": 100, "openInterest": 1000},
            {"strike": 103.0,"bid": 1.0, "ask": 1.1, "impliedVolatility": 0.25, "volume": 100, "openInterest": 10},
        ]
        puts = []

        mock_ticker = MagicMock()
        mock_ticker.info = {"currentPrice": spot}
        mock_ticker.options = [_expiry_days_out(30)]
        mock_ticker.option_chain.return_value = _make_chain(calls, puts)

        with patch("theta.tools.yf.Ticker", return_value=mock_ticker):
            result = get_options_chain("FAKE")

        kept_strikes = {c["strike"] for c in result["calls"]}
        assert 103.0 not in kept_strikes  # lowest OI, must be dropped
        assert 98.0 in kept_strikes        # highest OI, must be kept


# ---------------------------------------------------------------------------
# get_options_chain — atm_iv selection
# ---------------------------------------------------------------------------

class TestAtmIv:
    """atm_iv must reflect the call with strike closest to the current price."""

    def test_atm_iv_picks_closest_strike(self):
        spot = 100.0
        calls = [
            {"strike": 95.0, "bid": 3.0, "ask": 3.1, "impliedVolatility": 0.40, "volume": 200, "openInterest": 900},
            {"strike": 100.0,"bid": 2.0, "ask": 2.1, "impliedVolatility": 0.25, "volume": 300, "openInterest": 1200},
            {"strike": 105.0,"bid": 1.0, "ask": 1.1, "impliedVolatility": 0.30, "volume": 150, "openInterest": 700},
        ]
        puts = []

        mock_ticker = MagicMock()
        mock_ticker.info = {"currentPrice": spot}
        mock_ticker.options = [_expiry_days_out(30)]
        mock_ticker.option_chain.return_value = _make_chain(calls, puts)

        with patch("theta.tools.yf.Ticker", return_value=mock_ticker):
            result = get_options_chain("FAKE")

        # strike 100 is ATM; its IV is 0.25
        assert result["atm_iv"] == pytest.approx(0.25, abs=1e-4)

    def test_atm_iv_picks_nearest_when_no_exact_match(self):
        spot = 102.0  # between 100 and 105 — closer to 100
        calls = [
            {"strike": 100.0,"bid": 2.0, "ask": 2.1, "impliedVolatility": 0.22, "volume": 300, "openInterest": 1200},
            {"strike": 105.0,"bid": 1.0, "ask": 1.1, "impliedVolatility": 0.35, "volume": 150, "openInterest": 700},
        ]
        puts = []

        mock_ticker = MagicMock()
        mock_ticker.info = {"currentPrice": spot}
        mock_ticker.options = [_expiry_days_out(30)]
        mock_ticker.option_chain.return_value = _make_chain(calls, puts)

        with patch("theta.tools.yf.Ticker", return_value=mock_ticker):
            result = get_options_chain("FAKE")

        assert result["atm_iv"] == pytest.approx(0.22, abs=1e-4)


# ---------------------------------------------------------------------------
# get_news — shape normalisation
# ---------------------------------------------------------------------------

class TestGetNewsShapes:
    """get_news must handle both yfinance payload shapes without error."""

    def test_legacy_flat_shape(self):
        raw = [
            {
                "title": "Apple beats earnings",
                "publisher": "Reuters",
                "summary": "Apple reported record Q2 revenue.",
                "providerPublishTime": 1714000000,
            }
        ]
        mock_ticker = MagicMock()
        mock_ticker.news = raw

        with patch("theta.tools.yf.Ticker", return_value=mock_ticker):
            result = get_news("AAPL")

        assert len(result) == 1
        assert result[0]["title"] == "Apple beats earnings"
        assert result[0]["publisher"] == "Reuters"

    def test_content_dict_shape(self):
        raw = [
            {
                "content": {
                    "title": "Apple Vision Pro ships",
                    "provider": {"displayName": "Bloomberg"},
                    "summary": "Apple began shipping its mixed reality headset.",
                    "pubDate": "2024-02-02T10:00:00Z",
                }
            }
        ]
        mock_ticker = MagicMock()
        mock_ticker.news = raw

        with patch("theta.tools.yf.Ticker", return_value=mock_ticker):
            result = get_news("AAPL")

        assert len(result) == 1
        assert result[0]["title"] == "Apple Vision Pro ships"
        assert result[0]["publisher"] == "Bloomberg"

    def test_empty_news_returns_message(self):
        mock_ticker = MagicMock()
        mock_ticker.news = []

        with patch("theta.tools.yf.Ticker", return_value=mock_ticker):
            result = get_news("AAPL")

        assert len(result) == 1
        assert "message" in result[0]


# ---------------------------------------------------------------------------
# process_tool_call — dispatch
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# get_options_chain — Greeks
# ---------------------------------------------------------------------------

class TestGreeks:
    """Each contract must carry BSM Greeks when IV is present; omit them when IV is absent."""

    def _run(self, calls_rows, puts_rows, spot=100.0):
        mock_ticker = MagicMock()
        mock_ticker.info = {"currentPrice": spot}
        mock_ticker.options = [_expiry_days_out(30)]
        mock_ticker.option_chain.return_value = _make_chain(calls_rows, puts_rows)
        with patch("theta.tools.yf.Ticker", return_value=mock_ticker):
            return get_options_chain("FAKE")

    def test_call_greeks_present(self):
        calls = [{"strike": 100.0, "bid": 2.0, "ask": 2.1, "impliedVolatility": 0.25, "volume": 100, "openInterest": 500}]
        result = self._run(calls, [])
        contract = result["calls"][0]
        for greek in ("delta", "gamma", "theta", "vega"):
            assert greek in contract, f"{greek} missing from call contract"

    def test_put_greeks_present(self):
        puts = [{"strike": 100.0, "bid": 2.0, "ask": 2.1, "impliedVolatility": 0.25, "volume": 100, "openInterest": 500}]
        result = self._run([], puts)
        contract = result["puts"][0]
        for greek in ("delta", "gamma", "theta", "vega"):
            assert greek in contract, f"{greek} missing from put contract"

    def test_call_delta_positive(self):
        calls = [{"strike": 100.0, "bid": 2.0, "ask": 2.1, "impliedVolatility": 0.25, "volume": 100, "openInterest": 500}]
        result = self._run(calls, [])
        assert result["calls"][0]["delta"] > 0

    def test_put_delta_negative(self):
        puts = [{"strike": 100.0, "bid": 2.0, "ask": 2.1, "impliedVolatility": 0.25, "volume": 100, "openInterest": 500}]
        result = self._run([], puts)
        assert result["puts"][0]["delta"] < 0

    def test_atm_call_delta_near_half(self):
        """ATM call delta should be close to 0.5."""
        calls = [{"strike": 100.0, "bid": 2.0, "ask": 2.1, "impliedVolatility": 0.25, "volume": 100, "openInterest": 500}]
        result = self._run(calls, [], spot=100.0)
        assert 0.4 < result["calls"][0]["delta"] < 0.6

    def test_theta_negative(self):
        """Theta must be negative for both calls and puts (time decay costs the holder)."""
        calls = [{"strike": 100.0, "bid": 2.0, "ask": 2.1, "impliedVolatility": 0.25, "volume": 100, "openInterest": 500}]
        puts  = [{"strike": 100.0, "bid": 2.0, "ask": 2.1, "impliedVolatility": 0.25, "volume": 100, "openInterest": 500}]
        result = self._run(calls, puts)
        assert result["calls"][0]["theta"] < 0
        assert result["puts"][0]["theta"] < 0

    def test_vega_positive(self):
        """Vega must be positive for both calls and puts (IV increase benefits holder)."""
        calls = [{"strike": 100.0, "bid": 2.0, "ask": 2.1, "impliedVolatility": 0.25, "volume": 100, "openInterest": 500}]
        puts  = [{"strike": 100.0, "bid": 2.0, "ask": 2.1, "impliedVolatility": 0.25, "volume": 100, "openInterest": 500}]
        result = self._run(calls, puts)
        assert result["calls"][0]["vega"] > 0
        assert result["puts"][0]["vega"] > 0

    def test_missing_iv_omits_greeks(self):
        """Contracts with no IV should not have Greek fields."""
        import math
        calls = [{"strike": 100.0, "bid": 2.0, "ask": 2.1, "impliedVolatility": float("nan"), "volume": 100, "openInterest": 500}]
        result = self._run(calls, [])
        contract = result["calls"][0]
        for greek in ("delta", "gamma", "theta", "vega"):
            assert greek not in contract, f"{greek} should be absent when IV is NaN"


# ---------------------------------------------------------------------------
# get_financials
# ---------------------------------------------------------------------------

class TestGetFinancials:
    """get_financials must map yfinance info fields correctly and exclude None values."""

    def _mock_info(self, overrides=None):
        base = {
            "trailingPE": 28.5,
            "forwardPE": 24.0,
            "priceToBook": 12.3,
            "priceToSalesTrailing12Months": 7.1,
            "enterpriseToEbitda": 20.0,
            "grossMargins": 0.45,
            "operatingMargins": 0.30,
            "profitMargins": 0.25,
            "returnOnEquity": 0.80,
            "returnOnAssets": 0.18,
            "revenueGrowth": 0.12,
            "earningsGrowth": 0.15,
            "debtToEquity": 55.0,
            "currentRatio": 1.5,
            "quickRatio": 1.2,
            "freeCashflow": 50_000_000_000,
            "ebitda": 90_000_000_000,
            "dividendYield": 0.005,
            "payoutRatio": 0.15,
            "targetMeanPrice": 220.0,
            "recommendationKey": "buy",
            "numberOfAnalystOpinions": 35,
        }
        if overrides:
            base.update(overrides)
        return base

    def test_all_fields_mapped(self):
        mock_ticker = MagicMock()
        mock_ticker.info = self._mock_info()
        with patch("theta.tools.yf.Ticker", return_value=mock_ticker):
            result = get_financials("FAKE")

        assert result["pe_trailing"] == pytest.approx(28.5)
        assert result["pe_forward"] == pytest.approx(24.0)
        assert result["gross_margin"] == pytest.approx(0.45)
        assert result["roe"] == pytest.approx(0.80)
        assert result["revenue_growth_yoy"] == pytest.approx(0.12)
        assert result["debt_to_equity"] == pytest.approx(55.0)
        assert result["free_cash_flow"] == 50_000_000_000
        assert result["analyst_recommendation"] == "buy"
        assert result["analyst_count"] == 35

    def test_none_fields_excluded(self):
        """Fields absent from yfinance (returns None) must not appear in output."""
        mock_ticker = MagicMock()
        mock_ticker.info = self._mock_info({"dividendYield": None, "payoutRatio": None})
        with patch("theta.tools.yf.Ticker", return_value=mock_ticker):
            result = get_financials("FAKE")

        assert "dividend_yield" not in result
        assert "payout_ratio" not in result

    def test_ticker_uppercased(self):
        mock_ticker = MagicMock()
        mock_ticker.info = self._mock_info()
        with patch("theta.tools.yf.Ticker", return_value=mock_ticker):
            result = get_financials("aapl")
        assert result["ticker"] == "AAPL"

    def test_yfinance_exception_returns_error(self):
        mock_ticker = MagicMock()
        mock_ticker.info = MagicMock(side_effect=RuntimeError("network error"))
        with patch("theta.tools.yf.Ticker", return_value=mock_ticker):
            result = get_financials("FAKE")
        assert "error" in result

    def test_get_financials_dispatched_by_process_tool_call(self):
        mock_ticker = MagicMock()
        mock_ticker.info = self._mock_info()
        with patch("theta.tools.yf.Ticker", return_value=mock_ticker):
            raw = process_tool_call("get_financials", {"ticker": "FAKE"})
        parsed = json.loads(raw)
        assert "error" not in parsed
        assert parsed["ticker"] == "FAKE"


# ---------------------------------------------------------------------------
# process_tool_call — dispatch
# ---------------------------------------------------------------------------

class TestProcessToolCall:
    """process_tool_call must route known tools and gracefully reject unknown ones."""

    def test_unknown_tool_returns_error_json(self):
        result = process_tool_call("nonexistent_tool", {"ticker": "AAPL"})
        parsed = json.loads(result)
        assert "error" in parsed
        assert "nonexistent_tool" in parsed["error"]

    def test_known_tool_is_dispatched(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "currentPrice": 150.0,
            "previousClose": 148.0,
            "fiftyTwoWeekHigh": 200.0,
            "fiftyTwoWeekLow": 120.0,
        }
        mock_ticker.history.return_value = pd.DataFrame(
            {"Close": [145.0, 150.0]},
            index=pd.date_range("2024-01-01", periods=2),
        )

        with patch("theta.tools.yf.Ticker", return_value=mock_ticker):
            result = process_tool_call("get_price_data", {"ticker": "FAKE"})

        parsed = json.loads(result)
        assert "error" not in parsed
        assert parsed["ticker"] == "FAKE"
