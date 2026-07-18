from typing import Any
import yfinance as yf

from theta.models import Financials

SCHEMA = {
    "name": "get_financials",
    "description": (
        "Fetch fundamental financial metrics for a ticker symbol. "
        "Returns valuation ratios (P/E, P/B, EV/EBITDA), profitability margins, "
        "YoY revenue and earnings growth, balance sheet health (debt/equity, current ratio), "
        "free cash flow, analyst consensus (target price, recommendation, analyst count), "
        "and short interest (short_ratio = days-to-cover, short_pct_of_float). "
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
}


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
            short_ratio=info.get("shortRatio"),
            short_pct_of_float=info.get("shortPercentOfFloat"),
        )
        return data.model_dump(exclude_none=True)
    except Exception as e:
        return Financials(ticker=ticker, error=str(e)).model_dump(exclude_none=True)
