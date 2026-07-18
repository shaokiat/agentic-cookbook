from typing import Any
import yfinance as yf

from theta.models import PriceData

SCHEMA = {
    "name": "get_price_data",
    "description": (
        "Fetch current stock price and key statistics for a ticker symbol. "
        "Returns price, 52-week range, P/E ratio, beta, implied volatility, "
        "sector, and 1-month return."
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


def get_price_data(ticker: str) -> dict[str, Any]:
    """Fetch current stock price and key statistics for a ticker symbol."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="3mo")

        data = PriceData(
            ticker=ticker.upper(),
            current_price=info.get("currentPrice") or info.get("regularMarketPrice"),
            previous_close=info.get("previousClose"),
            high_52w=info.get("fiftyTwoWeekHigh"),
            low_52w=info.get("fiftyTwoWeekLow"),
            market_cap=info.get("marketCap"),
            pe_ratio=info.get("trailingPE"),
            implied_volatility=info.get("impliedVolatility"),
            beta=info.get("beta"),
            volume=info.get("volume"),
            avg_volume=info.get("averageVolume"),
            sector=info.get("sector"),
            industry=info.get("industry"),
        )

        if len(hist) >= 2:
            data.return_1mo_pct = round(
                (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100, 2
            )

        if len(hist) >= 15:
            closes = hist["Close"]
            delta = closes.diff().dropna()
            gains = delta.clip(lower=0)
            losses = (-delta).clip(lower=0)
            avg_gain = gains.iloc[:14].mean()
            avg_loss = losses.iloc[:14].mean()
            for i in range(14, len(gains)):
                avg_gain = (avg_gain * 13 + gains.iloc[i]) / 14
                avg_loss = (avg_loss * 13 + losses.iloc[i]) / 14
            if avg_loss > 0:
                data.rsi_14 = round(100 - 100 / (1 + avg_gain / avg_loss), 1)
            else:
                data.rsi_14 = 100.0

        return data.model_dump(exclude_none=True)
    except Exception as e:
        return PriceData(ticker=ticker, error=str(e)).model_dump(exclude_none=True)
