"""
Unit tests for the tools/ package — no network calls.

Coverage:
  - get_price_data: field mapping, RSI-14 computation
  - get_news: legacy flat shape and newer content{} shape
  - get_financials: field mapping, None exclusion, error handling
"""

import json
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tools.financials import get_financials
from tools.news import get_news
from tools.price import get_price_data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chain(calls_rows: list[dict], puts_rows: list[dict]) -> SimpleNamespace:
    cols = ["strike", "bid", "ask", "impliedVolatility", "volume", "openInterest"]
    return SimpleNamespace(
        calls=pd.DataFrame(calls_rows, columns=cols),
        puts=pd.DataFrame(puts_rows, columns=cols),
    )


def _expiry_days_out(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _mock_options_ticker(spot: float, calls: list, puts: list, expiry_days: int = 30):
    mock_ticker = MagicMock()
    mock_ticker.info = {"currentPrice": spot}
    mock_ticker.options = [_expiry_days_out(expiry_days)]
    mock_ticker.option_chain.return_value = _make_chain(calls, puts)
    mock_ticker.get_earnings_dates.return_value = None
    mock_ticker.calendar = {}
    mock_ticker.earnings_dates = None
    return mock_ticker


class TestPriceData:
    """get_price_data must compute RSI-14 when sufficient history is available."""

    def _make_history(self, closes: list[float]) -> pd.DataFrame:
        idx = pd.date_range("2024-01-01", periods=len(closes))
        return pd.DataFrame({"Close": closes}, index=idx)

    def test_rsi_present_with_sufficient_history(self):
        closes = [100.0 + i * 0.5 for i in range(20)]  # steady uptrend — 20 days
        mock_ticker = MagicMock()
        mock_ticker.info = {"currentPrice": 110.0}
        mock_ticker.history.return_value = self._make_history(closes)
        with patch("tools.price.yf.Ticker", return_value=mock_ticker):
            result = get_price_data("FAKE")
        assert "rsi_14" in result
        assert 0 <= result["rsi_14"] <= 100

    def test_rsi_absent_with_insufficient_history(self):
        closes = [100.0, 101.0]  # only 2 days — not enough for RSI-14
        mock_ticker = MagicMock()
        mock_ticker.info = {"currentPrice": 101.0}
        mock_ticker.history.return_value = self._make_history(closes)
        with patch("tools.price.yf.Ticker", return_value=mock_ticker):
            result = get_price_data("FAKE")
        assert "rsi_14" not in result

    def test_rsi_near_100_for_steady_uptrend(self):
        closes = [100.0 + i for i in range(20)]  # strong uptrend
        mock_ticker = MagicMock()
        mock_ticker.info = {"currentPrice": 119.0}
        mock_ticker.history.return_value = self._make_history(closes)
        with patch("tools.price.yf.Ticker", return_value=mock_ticker):
            result = get_price_data("FAKE")
        assert result.get("rsi_14", 0) > 70

    def test_rsi_near_0_for_steady_downtrend(self):
        closes = [120.0 - i for i in range(20)]  # strong downtrend
        mock_ticker = MagicMock()
        mock_ticker.info = {"currentPrice": 101.0}
        mock_ticker.history.return_value = self._make_history(closes)
        with patch("tools.price.yf.Ticker", return_value=mock_ticker):
            result = get_price_data("FAKE")
        assert result.get("rsi_14", 100) < 30


# ---------------------------------------------------------------------------
# get_news — shape normalisation
# ---------------------------------------------------------------------------

class TestGetNewsShapes:
    """get_news must handle both yfinance payload shapes without error."""

    def test_legacy_flat_shape(self):
        raw = [{"title": "Apple beats earnings", "publisher": "Reuters",
                "summary": "Apple reported record Q2 revenue.", "providerPublishTime": 1714000000}]
        mock_ticker = MagicMock()
        mock_ticker.news = raw
        with patch("tools.news.yf.Ticker", return_value=mock_ticker):
            result = get_news("AAPL")
        assert len(result) == 1
        assert result[0]["title"] == "Apple beats earnings"
        assert result[0]["publisher"] == "Reuters"

    def test_content_dict_shape(self):
        raw = [{"content": {"title": "Apple Vision Pro ships",
                            "provider": {"displayName": "Bloomberg"},
                            "summary": "Apple began shipping its mixed reality headset.",
                            "pubDate": "2024-02-02T10:00:00Z"}}]
        mock_ticker = MagicMock()
        mock_ticker.news = raw
        with patch("tools.news.yf.Ticker", return_value=mock_ticker):
            result = get_news("AAPL")
        assert len(result) == 1
        assert result[0]["title"] == "Apple Vision Pro ships"
        assert result[0]["publisher"] == "Bloomberg"

    def test_empty_news_returns_message(self):
        mock_ticker = MagicMock()
        mock_ticker.news = []
        with patch("tools.news.yf.Ticker", return_value=mock_ticker):
            result = get_news("AAPL")
        assert len(result) == 1
        assert "message" in result[0]


# ---------------------------------------------------------------------------
# get_financials
# ---------------------------------------------------------------------------

class TestGetFinancials:
    """get_financials must map yfinance info fields correctly and exclude None values."""

    def _mock_info(self, overrides=None):
        base = {
            "trailingPE": 28.5, "forwardPE": 24.0, "priceToBook": 12.3,
            "priceToSalesTrailing12Months": 7.1, "enterpriseToEbitda": 20.0,
            "grossMargins": 0.45, "operatingMargins": 0.30, "profitMargins": 0.25,
            "returnOnEquity": 0.80, "returnOnAssets": 0.18,
            "revenueGrowth": 0.12, "earningsGrowth": 0.15,
            "debtToEquity": 55.0, "currentRatio": 1.5, "quickRatio": 1.2,
            "freeCashflow": 50_000_000_000, "ebitda": 90_000_000_000,
            "dividendYield": 0.005, "payoutRatio": 0.15,
            "targetMeanPrice": 220.0, "recommendationKey": "buy",
            "numberOfAnalystOpinions": 35,
        }
        if overrides:
            base.update(overrides)
        return base

    def test_all_fields_mapped(self):
        mock_ticker = MagicMock()
        mock_ticker.info = self._mock_info()
        with patch("tools.financials.yf.Ticker", return_value=mock_ticker):
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
        mock_ticker = MagicMock()
        mock_ticker.info = self._mock_info({"dividendYield": None, "payoutRatio": None})
        with patch("tools.financials.yf.Ticker", return_value=mock_ticker):
            result = get_financials("FAKE")
        assert "dividend_yield" not in result
        assert "payout_ratio" not in result

    def test_ticker_uppercased(self):
        mock_ticker = MagicMock()
        mock_ticker.info = self._mock_info()
        with patch("tools.financials.yf.Ticker", return_value=mock_ticker):
            result = get_financials("aapl")
        assert result["ticker"] == "AAPL"

    def test_yfinance_exception_returns_error(self):
        mock_ticker = MagicMock()
        mock_ticker.info = MagicMock(side_effect=RuntimeError("network error"))
        with patch("tools.financials.yf.Ticker", return_value=mock_ticker):
            result = get_financials("FAKE")
        assert "error" in result
