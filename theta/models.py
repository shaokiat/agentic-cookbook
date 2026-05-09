from typing import Optional
from pydantic import BaseModel


class PriceData(BaseModel):
    ticker: str
    current_price: Optional[float] = None
    previous_close: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    market_cap: Optional[int] = None
    pe_ratio: Optional[float] = None
    implied_volatility: Optional[float] = None
    beta: Optional[float] = None
    volume: Optional[int] = None
    avg_volume: Optional[int] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    return_1mo_pct: Optional[float] = None
    error: Optional[str] = None


class NewsItem(BaseModel):
    title: str = ""
    publisher: str = ""
    summary: str = ""
    published: str = ""
    message: Optional[str] = None
    error: Optional[str] = None


class OptionContract(BaseModel):
    strike: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    iv: Optional[float] = None
    volume: Optional[int] = None
    open_interest: Optional[int] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None


class OptionsChain(BaseModel):
    expiry: str
    current_price: float
    atm_iv: Optional[float] = None
    calls: list[OptionContract] = []
    puts: list[OptionContract] = []
    error: Optional[str] = None


class Financials(BaseModel):
    ticker: str
    # Valuation
    pe_trailing: Optional[float] = None
    pe_forward: Optional[float] = None
    price_to_book: Optional[float] = None
    price_to_sales: Optional[float] = None
    ev_to_ebitda: Optional[float] = None
    # Profitability
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    profit_margin: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None
    # Growth
    revenue_growth_yoy: Optional[float] = None
    earnings_growth_yoy: Optional[float] = None
    # Balance sheet
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    # Cash flow
    free_cash_flow: Optional[int] = None
    ebitda: Optional[int] = None
    # Dividends
    dividend_yield: Optional[float] = None
    payout_ratio: Optional[float] = None
    # Analyst
    analyst_target_price: Optional[float] = None
    analyst_recommendation: Optional[str] = None
    analyst_count: Optional[int] = None
    error: Optional[str] = None
