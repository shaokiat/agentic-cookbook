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


class EarningsDate(BaseModel):
    date: str
    days_until: int


class EarningsDates(BaseModel):
    ticker: str
    earnings_dates: list[EarningsDate] = []
    error: Optional[str] = None


class OptionContract(BaseModel):
    strike: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread_pct: Optional[float] = None   # bid-ask as % of mid; None if no valid mid
    iv: Optional[float] = None
    iv_fitted: Optional[float] = None
    iv_excess: Optional[float] = None
    volume: Optional[int] = None
    open_interest: Optional[int] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None


class IVSurface(BaseModel):
    r_squared: float
    n_points: int


class OptionsExpiry(BaseModel):
    expiry: str
    dte: int
    earnings_count: int = 0
    atm_spread_pct: Optional[float] = None   # avg spread_pct of the 2 nearest ATM contracts (1 call + 1 put)
    calls: list[OptionContract] = []
    puts: list[OptionContract] = []


class OptionsChain(BaseModel):
    current_price: float
    iv_surface: Optional[IVSurface] = None
    expiries: list[OptionsExpiry] = []
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
    # Short interest
    short_ratio: Optional[float] = None          # days-to-cover
    short_pct_of_float: Optional[float] = None   # short interest as % of float
    error: Optional[str] = None
