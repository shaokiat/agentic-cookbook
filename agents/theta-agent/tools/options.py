"""Option chain fetch for the screener: a flat contract list within a DTE/moneyness window."""

import math
from datetime import date
from typing import Any, Optional

import yfinance as yf

RISK_FREE_RATE = 0.045


def _norm_cdf(x: float) -> float:
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _bsm_greeks(flag: str, S: float, K: float, t: float, sigma: float, r: float = RISK_FREE_RATE) -> dict[str, float]:
    if t <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return {}
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    nd1 = _norm_pdf(d1)
    gamma = nd1 / (S * sigma * math.sqrt(t))
    vega = S * nd1 * math.sqrt(t) / 100.0
    if flag == "C":
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


def _f(v) -> Optional[float]:
    """yfinance emits NaN for missing numerics; NaN != NaN is the cheapest test."""
    return float(v) if v is not None and v == v else None


def fetch_chain(
    ticker: str,
    *,
    dte_min: int,
    dte_max: Optional[int] = None,
    right: str = "C",
    moneyness: tuple[float, float] = (0.5, 1.5),
    max_expiries: Optional[int] = None,
) -> dict[str, Any]:
    """Contracts in a DTE/moneyness window with BSM Greeks attached.

    Returns {"ticker", "current_price", "contracts": [...], "error": str|None}.
    Never raises — a failed ticker returns an empty list and an error string.
    """
    right = right.upper()
    if right not in ("C", "P"):
        return {"ticker": ticker, "current_price": None, "contracts": [], "error": f"Invalid right: {right}"}

    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        spot = info.get("currentPrice") or info.get("regularMarketPrice")
        if not spot:
            return {"ticker": ticker, "current_price": None, "contracts": [], "error": "Could not determine current price"}

        all_expiries = stock.options
        if not all_expiries:
            return {"ticker": ticker, "current_price": spot, "contracts": [], "error": "No options expiries available"}

        today = date.today()
        window = []
        for e in all_expiries:
            dte = (date.fromisoformat(e) - today).days
            if dte >= dte_min and (dte_max is None or dte <= dte_max):
                window.append((e, dte))
        if not window:
            bound = f"{dte_min}-{dte_max}" if dte_max else f">{dte_min}"
            return {"ticker": ticker, "current_price": spot, "contracts": [], "error": f"No expiries in DTE window {bound}"}
        if max_expiries:
            window = window[:max_expiries]

        low, high = spot * moneyness[0], spot * moneyness[1]
        contracts = []

        for expiry_str, dte in window:
            t = dte / 365.0
            df = stock.option_chain(expiry_str)
            df = df.calls if right == "C" else df.puts
            for _, row in df[(df["strike"] >= low) & (df["strike"] <= high)].iterrows():
                strike = float(row["strike"])
                iv = _f(row["impliedVolatility"])
                bid, ask = _f(row["bid"]), _f(row["ask"])
                mid = (bid + ask) / 2 if bid is not None and ask is not None else None
                oi, vol = _f(row["openInterest"]), _f(row["volume"])
                contracts.append({
                    "ticker": ticker.upper(),
                    "strike": round(strike, 2),
                    "expiry": expiry_str,
                    "dte": dte,
                    "right": right,
                    "bid": bid,
                    "ask": ask,
                    "mid": round(mid, 4) if mid else None,
                    # None rather than 0 when mid is absent: a missing spread is unknown, not tight
                    "spread_pct": round((ask - bid) / mid, 4) if mid and mid > 0 else None,
                    "iv": round(iv, 4) if iv else None,
                    "open_interest": int(oi) if oi is not None else 0,
                    "volume": int(vol) if vol is not None else 0,
                    **(_bsm_greeks(right, spot, strike, t, iv) if iv else {}),
                })

        return {"ticker": ticker.upper(), "current_price": round(spot, 2), "contracts": contracts, "error": None}

    except Exception as e:
        return {"ticker": ticker, "current_price": None, "contracts": [], "error": str(e)}
