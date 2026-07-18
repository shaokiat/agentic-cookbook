import math
from datetime import date, timedelta
from typing import Any, Optional

import numpy as np
import yfinance as yf

from theta.models import (
    IVSurface,
    OptionContract,
    OptionsChain,
    OptionsExpiry,
)

SCHEMA = {
    "name": "get_options_chain",
    "description": (
        "Fetch the options chain for the 3 nearest expiries (each >= 14 days out), "
        "strikes within 15% of current price. Fits an IV surface via OLS across all "
        "contracts to compute iv_excess (positive = IV rich, negative = IV cheap) per "
        "contract. Each expiry is annotated with earnings_count (number of upcoming "
        "earnings events within the expiry window). Contracts within each expiry are "
        "sorted by iv_excess descending (richest IV first)."
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


def _norm_cdf(x: float) -> float:
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _bsm_greeks(flag: str, S: float, K: float, t: float, sigma: float, r: float = 0.045) -> dict[str, float]:
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


def _fit_iv_surface(
    surface_rows: list[tuple[float, float, float]],
) -> tuple[Optional[np.ndarray], Optional[IVSurface]]:
    """OLS fit: IV ≈ a + b·m + c·m² + d·√T + e·m·√T"""
    if len(surface_rows) < 5:
        return None, None
    m = np.array([r[0] for r in surface_rows])
    sqt = np.array([r[1] for r in surface_rows])
    iv = np.array([r[2] for r in surface_rows])
    A = np.column_stack([np.ones(len(m)), m, m ** 2, sqt, m * sqt])
    coeffs, _, _, _ = np.linalg.lstsq(A, iv, rcond=None)
    iv_fitted = A @ coeffs
    ss_res = np.sum((iv - iv_fitted) ** 2)
    ss_tot = np.sum((iv - np.mean(iv)) ** 2)
    r_squared = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0
    return coeffs, IVSurface(r_squared=round(r_squared, 3), n_points=len(surface_rows))


def _predict_iv(coeffs: np.ndarray, log_moneyness: float, sqrt_t: float) -> float:
    return float(
        coeffs[0]
        + coeffs[1] * log_moneyness
        + coeffs[2] * log_moneyness ** 2
        + coeffs[3] * sqrt_t
        + coeffs[4] * log_moneyness * sqrt_t
    )


def _fetch_earnings_dates(stock: yf.Ticker) -> list[date]:
    """3-tier fallback — mirrors tools/earnings.py without the Pydantic layer."""
    today = date.today()
    future: list[date] = []

    try:
        df = stock.get_earnings_dates(limit=8)
        if df is not None and not df.empty:
            for idx in df.index:
                d = idx.date() if hasattr(idx, "date") else idx
                if isinstance(d, date) and d >= today:
                    future.append(d)
    except Exception:
        pass

    if not future:
        try:
            cal = stock.calendar
            if isinstance(cal, dict) and "Earnings Date" in cal:
                val = cal["Earnings Date"]
                candidates = val if hasattr(val, "__iter__") and not isinstance(val, str) else [val]
                for c in candidates:
                    d = c.date() if hasattr(c, "date") else c
                    if isinstance(d, date) and d >= today:
                        future.append(d)
        except Exception:
            pass

    if not future:
        try:
            df = stock.earnings_dates
            if df is not None and not df.empty:
                for idx in list(df.index)[:8]:
                    d = idx.date() if hasattr(idx, "date") else idx
                    if isinstance(d, date) and d >= today:
                        future.append(d)
        except Exception:
            pass

    return sorted(set(future))


def get_options_chain(ticker: str) -> dict[str, Any]:
    """Fetch multi-expiry options chain with IV surface fit and earnings annotation."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        if not current_price:
            return OptionsChain(current_price=0, error="Could not determine current price").model_dump(exclude_none=True)

        all_expiries = stock.options
        if not all_expiries:
            return OptionsChain(current_price=current_price, error="No options expiries available").model_dump(exclude_none=True)

        today = date.today()
        min_date = today + timedelta(days=14)
        valid_expiries = [d for d in all_expiries if date.fromisoformat(d) >= min_date][:3]
        if not valid_expiries:
            return OptionsChain(current_price=current_price, error="No expiries >= 14 days out").model_dump(exclude_none=True)

        earnings_dates = _fetch_earnings_dates(stock)

        low = current_price * 0.85
        high = current_price * 1.15

        # Collect all contracts across all expiries for surface fitting
        # Structure: {expiry: {"calls": [...raw rows...], "puts": [...raw rows...], "dte": int}}
        raw_by_expiry: dict[str, dict] = {}
        surface_rows: list[tuple[float, float, float]] = []  # (log_moneyness, sqrt_t, iv)

        for expiry_str in valid_expiries:
            expiry_date = date.fromisoformat(expiry_str)
            dte = (expiry_date - today).days
            t = dte / 365.0
            sqrt_t = math.sqrt(t)

            chain = stock.option_chain(expiry_str)
            raw_by_expiry[expiry_str] = {"dte": dte, "t": t, "sqrt_t": sqrt_t, "calls": [], "puts": []}

            for flag, df in (("c", chain.calls), ("p", chain.puts)):
                filtered = df[(df["strike"] >= low) & (df["strike"] <= high)].copy()
                for _, row in filtered.iterrows():
                    strike = float(row["strike"])
                    iv_raw = row["impliedVolatility"]
                    iv = float(iv_raw) if iv_raw == iv_raw and iv_raw is not None else None

                    contract_data = {
                        "strike": strike,
                        "flag": flag,
                        "iv": iv,
                        "bid": float(row["bid"]) if row["bid"] == row["bid"] else None,
                        "ask": float(row["ask"]) if row["ask"] == row["ask"] else None,
                        "volume": int(row["volume"]) if row["volume"] == row["volume"] else None,
                        "open_interest": int(row["openInterest"]) if row["openInterest"] == row["openInterest"] else None,
                        "t": t,
                        "sqrt_t": sqrt_t,
                    }
                    raw_by_expiry[expiry_str]["calls" if flag == "c" else "puts"].append(contract_data)

                    # Accumulate surface fit data points
                    if iv and iv > 0.02 and strike > 0:
                        log_moneyness = math.log(strike / current_price)
                        surface_rows.append((log_moneyness, sqrt_t, iv))

        # Fit IV surface across all expiries
        coeffs, iv_surface = _fit_iv_surface(surface_rows)

        # Build output expiries with iv_excess annotated and sorted
        output_expiries: list[OptionsExpiry] = []

        for expiry_str in valid_expiries:
            expiry_date = date.fromisoformat(expiry_str)
            raw = raw_by_expiry[expiry_str]
            dte = raw["dte"]
            t = raw["t"]
            sqrt_t = raw["sqrt_t"]

            earnings_count = sum(1 for d in earnings_dates if today < d <= expiry_date)

            def build_contracts(rows: list[dict], flag: str) -> list[OptionContract]:
                contracts = []
                for r in rows:
                    strike = r["strike"]
                    iv = r["iv"]
                    greeks = _bsm_greeks(flag, current_price, strike, t, iv) if iv else {}

                    iv_fitted = None
                    iv_excess = None
                    if coeffs is not None and iv and strike > 0:
                        log_moneyness = math.log(strike / current_price)
                        iv_fitted_val = _predict_iv(coeffs, log_moneyness, sqrt_t)
                        iv_fitted = round(iv_fitted_val, 4)
                        iv_excess = round(iv - iv_fitted_val, 4)

                    bid = round(r["bid"], 2) if r["bid"] is not None else None
                    ask = round(r["ask"], 2) if r["ask"] is not None else None
                    mid = (bid + ask) / 2 if bid is not None and ask is not None else None
                    spread_pct = round((ask - bid) / mid * 100, 2) if mid and mid > 0 else None

                    contracts.append(OptionContract(
                        strike=round(strike, 2),
                        bid=bid,
                        ask=ask,
                        spread_pct=spread_pct,
                        iv=round(iv, 4) if iv else None,
                        iv_fitted=iv_fitted,
                        iv_excess=iv_excess,
                        volume=r["volume"],
                        open_interest=r["open_interest"],
                        **greeks,
                    ))

                # Sort by iv_excess descending (richest IV first); contracts without iv_excess go last
                contracts.sort(key=lambda c: c.iv_excess if c.iv_excess is not None else -999, reverse=True)
                return contracts

            calls = build_contracts(raw["calls"], "c")
            puts = build_contracts(raw["puts"], "p")

            # ATM spread: nearest call + nearest put to current price, averaged
            atm_spread_pct = None
            atm_samples = []
            for leg in (calls, puts):
                if leg:
                    nearest = min(leg, key=lambda c: abs(c.strike - current_price))
                    if nearest.spread_pct is not None:
                        atm_samples.append(nearest.spread_pct)
            if atm_samples:
                atm_spread_pct = round(sum(atm_samples) / len(atm_samples), 2)

            output_expiries.append(OptionsExpiry(
                expiry=expiry_str,
                dte=dte,
                earnings_count=earnings_count,
                atm_spread_pct=atm_spread_pct,
                calls=calls,
                puts=puts,
            ))

        # Skew: avg OTM put IV minus avg OTM call IV at ~0.25 delta, first expiry
        skew = None
        if output_expiries:
            first = output_expiries[0]
            otm_put_ivs = [
                c.iv for c in first.puts
                if c.delta is not None and -0.30 <= c.delta <= -0.15 and c.iv
            ]
            otm_call_ivs = [
                c.iv for c in first.calls
                if c.delta is not None and 0.15 <= c.delta <= 0.30 and c.iv
            ]
            if otm_put_ivs and otm_call_ivs:
                skew = round(
                    sum(otm_put_ivs) / len(otm_put_ivs)
                    - sum(otm_call_ivs) / len(otm_call_ivs),
                    4,
                )

        return OptionsChain(
            current_price=round(current_price, 2),
            iv_surface=iv_surface,
            skew=skew,
            expiries=output_expiries,
        ).model_dump(exclude_none=True)

    except Exception as e:
        return OptionsChain(current_price=0, error=str(e)).model_dump(exclude_none=True)
