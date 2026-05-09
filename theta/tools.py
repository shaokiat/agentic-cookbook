import json
import math
from datetime import date, timedelta
from typing import Any
import yfinance as yf

from .models import PriceData, NewsItem, OptionContract, OptionsChain, Financials


# ---------------------------------------------------------------------------
# BSM Greeks (pure Python, no extra dependencies)
# ---------------------------------------------------------------------------

def _norm_cdf(x: float) -> float:
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)

def _bsm_greeks(flag: str, S: float, K: float, t: float, sigma: float, r: float = 0.045) -> dict[str, float]:
    """Return delta, gamma, theta (per day), vega (per 1% IV) for a European option."""
    if t <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return {}
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    nd1 = _norm_pdf(d1)

    gamma = nd1 / (S * sigma * math.sqrt(t))
    vega = S * nd1 * math.sqrt(t) / 100.0

    if flag == "c":
        delta = _norm_cdf(d1)
        theta = (-S * nd1 * sigma / (2.0 * math.sqrt(t)) - r * K * math.exp(-r * t) * _norm_cdf(d2)) / 365.0
    else:
        delta = _norm_cdf(d1) - 1.0
        theta = (-S * nd1 * sigma / (2.0 * math.sqrt(t)) + r * K * math.exp(-r * t) * _norm_cdf(-d2)) / 365.0

    return {
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "theta": round(theta, 4),
        "vega": round(vega, 4),
    }

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def get_price_data(ticker: str) -> dict[str, Any]:
    """Fetch current stock price and key statistics for a ticker symbol."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="1mo")

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

        return data.model_dump(exclude_none=True)
    except Exception as e:
        return PriceData(ticker=ticker, error=str(e)).model_dump(exclude_none=True)


def get_news(ticker: str) -> list[dict[str, Any]]:
    """Fetch recent news headlines and summaries for a ticker symbol."""
    try:
        stock = yf.Ticker(ticker)
        raw_news = stock.news or []

        items: list[NewsItem] = []
        for item in raw_news[:10]:
            content = item.get("content", {})
            if content:
                items.append(NewsItem(
                    title=content.get("title", ""),
                    publisher=content.get("provider", {}).get("displayName", ""),
                    summary=content.get("summary", ""),
                    published=content.get("pubDate", ""),
                ))
            else:
                items.append(NewsItem(
                    title=item.get("title", ""),
                    publisher=item.get("publisher", ""),
                    summary=item.get("summary", ""),
                    published=str(item.get("providerPublishTime", "")),
                ))

        if not items:
            return [NewsItem(message="No recent news found").model_dump(exclude_none=True)]
        return [i.model_dump(exclude_none=True) for i in items]
    except Exception as e:
        return [NewsItem(error=str(e)).model_dump(exclude_none=True)]


def get_options_chain(ticker: str) -> dict[str, Any]:
    """Fetch near-the-money options chain for the expiry closest to 30 days out."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        if not current_price:
            return OptionsChain(expiry="", current_price=0, error="Could not determine current price").model_dump(exclude_none=True)

        expiries = stock.options
        if not expiries:
            return OptionsChain(expiry="", current_price=current_price, error="No options expiries available").model_dump(exclude_none=True)

        today = date.today()
        min_date = today + timedelta(days=14)
        target_date = today + timedelta(days=30)

        valid = [d for d in expiries if date.fromisoformat(d) >= min_date]
        if not valid:
            return OptionsChain(expiry="", current_price=current_price, error="No expiries >= 14 days out").model_dump(exclude_none=True)

        expiry = min(valid, key=lambda d: abs(date.fromisoformat(d) - target_date))

        chain = stock.option_chain(expiry)
        calls_df = chain.calls
        puts_df = chain.puts

        low = current_price * 0.90
        high = current_price * 1.10

        dte = (date.fromisoformat(expiry) - today).days
        t = dte / 365.0

        def filter_and_rank(df, flag: str):
            filtered = df[(df["strike"] >= low) & (df["strike"] <= high)].copy()
            filtered = filtered.sort_values("openInterest", ascending=False).head(5)
            result = []
            for _, row in filtered.iterrows():
                strike = round(float(row["strike"]), 2)
                iv = round(float(row["impliedVolatility"]), 4) if row["impliedVolatility"] == row["impliedVolatility"] else None
                greeks = _bsm_greeks(flag, current_price, strike, t, iv) if iv else {}
                result.append(OptionContract(
                    strike=strike,
                    bid=round(float(row["bid"]), 2) if row["bid"] == row["bid"] else None,
                    ask=round(float(row["ask"]), 2) if row["ask"] == row["ask"] else None,
                    iv=iv,
                    volume=int(row["volume"]) if row["volume"] == row["volume"] else None,
                    open_interest=int(row["openInterest"]) if row["openInterest"] == row["openInterest"] else None,
                    **greeks,
                ))
            return result

        calls = filter_and_rank(calls_df, "c")
        puts = filter_and_rank(puts_df, "p")

        # ATM IV: IV of the call with strike closest to current price
        atm_iv = None
        if calls:
            atm_call = min(calls, key=lambda c: abs(c.strike - current_price))
            atm_iv = atm_call.iv

        return OptionsChain(
            expiry=expiry,
            current_price=round(current_price, 2),
            atm_iv=atm_iv,
            calls=calls,
            puts=puts,
        ).model_dump(exclude_none=True)
    except Exception as e:
        return OptionsChain(expiry="", current_price=0, error=str(e)).model_dump(exclude_none=True)


def get_financials(ticker: str) -> dict[str, Any]:
    """Fetch fundamental financial metrics for a ticker symbol."""
    try:
        info = yf.Ticker(ticker).info
        data = Financials(
            ticker=ticker.upper(),
            pe_trailing=info.get("trailingPE"),
            pe_forward=info.get("forwardPE"),
            price_to_book=info.get("priceToBook"),
            price_to_sales=info.get("priceToSalesTrailing12Months"),
            ev_to_ebitda=info.get("enterpriseToEbitda"),
            gross_margin=info.get("grossMargins"),
            operating_margin=info.get("operatingMargins"),
            profit_margin=info.get("profitMargins"),
            roe=info.get("returnOnEquity"),
            roa=info.get("returnOnAssets"),
            revenue_growth_yoy=info.get("revenueGrowth"),
            earnings_growth_yoy=info.get("earningsGrowth"),
            debt_to_equity=info.get("debtToEquity"),
            current_ratio=info.get("currentRatio"),
            quick_ratio=info.get("quickRatio"),
            free_cash_flow=info.get("freeCashflow"),
            ebitda=info.get("ebitda"),
            dividend_yield=info.get("dividendYield"),
            payout_ratio=info.get("payoutRatio"),
            analyst_target_price=info.get("targetMeanPrice"),
            analyst_recommendation=info.get("recommendationKey"),
            analyst_count=info.get("numberOfAnalystOpinions"),
        )
        return data.model_dump(exclude_none=True)
    except Exception as e:
        return Financials(ticker=ticker, error=str(e)).model_dump(exclude_none=True)


# ---------------------------------------------------------------------------
# Anthropic tool schemas
# ---------------------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    {
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
    },
    {
        "name": "get_news",
        "description": (
            "Fetch recent news headlines and summaries for a ticker symbol. "
            "Returns up to 10 recent articles with title, publisher, and summary."
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
    },
    {
        "name": "get_financials",
        "description": (
            "Fetch fundamental financial metrics for a ticker symbol. "
            "Returns valuation ratios (P/E, P/B, EV/EBITDA), profitability margins, "
            "YoY revenue and earnings growth, balance sheet health (debt/equity, current ratio), "
            "free cash flow, and analyst consensus (target price, recommendation, analyst count). "
            "Use this to qualify or challenge the options thesis with fundamental context."
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
    },
    {
        "name": "get_options_chain",
        "description": (
            "Fetch the near-the-money options chain for the expiry closest to 30 days out "
            "(minimum 14 days). Returns top 5 calls and puts by open interest, filtered to "
            "strikes within 10% of current price. Each contract includes strike, bid, ask, IV, "
            "volume, open interest, delta, gamma, theta (per day), and vega (per 1% IV move)."
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
    },
]

_DISPATCH = {
    "get_price_data": get_price_data,
    "get_news": get_news,
    "get_financials": get_financials,
    "get_options_chain": get_options_chain,
}


def process_tool_call(tool_name: str, tool_input: dict[str, Any]) -> str:
    fn = _DISPATCH.get(tool_name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    return json.dumps(fn(**tool_input), indent=2, default=str)
