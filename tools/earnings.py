from datetime import date
from typing import Any

import yfinance as yf

from theta.models import EarningsDate, EarningsDates

SCHEMA = {
    "name": "get_earnings_dates",
    "description": (
        "Fetch upcoming earnings dates for a ticker. Returns up to 4 future earnings dates "
        "with the number of days until each. Returns an empty list for tickers with no "
        "earnings data (ETFs, SPACs, etc.). Use this to assess event risk before selecting "
        "an options expiry."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol, e.g. AAPL, TSLA, SPY",
            }
        },
        "required": ["ticker"],
    },
}


def get_earnings_dates(ticker: str) -> dict[str, Any]:
    """Fetch upcoming earnings dates via 3-tier yfinance fallback."""
    try:
        stock = yf.Ticker(ticker)
        today = date.today()
        future_dates: list[date] = []

        # Tier 1: get_earnings_dates() — most reliable in recent yfinance
        try:
            df = stock.get_earnings_dates(limit=8)
            if df is not None and not df.empty:
                for idx in df.index:
                    d = idx.date() if hasattr(idx, "date") else idx
                    if isinstance(d, date) and d >= today:
                        future_dates.append(d)
        except Exception:
            pass

        # Tier 2: calendar dict/DataFrame
        if not future_dates:
            try:
                cal = stock.calendar
                if isinstance(cal, dict) and "Earnings Date" in cal:
                    val = cal["Earnings Date"]
                    candidates = val if hasattr(val, "__iter__") and not isinstance(val, str) else [val]
                    for c in candidates:
                        d = c.date() if hasattr(c, "date") else c
                        if isinstance(d, date) and d >= today:
                            future_dates.append(d)
            except Exception:
                pass

        # Tier 3: earnings_dates property
        if not future_dates:
            try:
                df = stock.earnings_dates
                if df is not None and not df.empty:
                    for idx in list(df.index)[:8]:
                        d = idx.date() if hasattr(idx, "date") else idx
                        if isinstance(d, date) and d >= today:
                            future_dates.append(d)
            except Exception:
                pass

        future_dates = sorted(set(future_dates))[:4]
        return EarningsDates(
            ticker=ticker.upper(),
            earnings_dates=[
                EarningsDate(date=str(d), days_until=(d - today).days)
                for d in future_dates
            ],
        ).model_dump(exclude_none=True)

    except Exception as e:
        return EarningsDates(ticker=ticker.upper(), error=str(e)).model_dump(exclude_none=True)
