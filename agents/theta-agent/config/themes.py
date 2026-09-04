"""Static thematic tags. Pure data — extending it requires no code change elsewhere."""

WATCHLIST_THEMES: dict[str, str] = {
    "MU":   "memory_supercycle_bullish",
    # MUU is Direxion Daily MU Bull 2X. Options exist but only out to ~200 DTE,
    # so it can never produce a LEAPS candidate — CSP only.
    "MUU":  "memory_supercycle_bullish_leveraged",
    "TSM":  "ai_infra_bullish",
    "AVGO": "ai_infra_bullish",
    "ASML": "ai_infra_bullish",
    "AMAT": "ai_infra_bullish",
    "NVDA": "ai_infra_bullish",
    "META": "ai_capex_bullish",
    "MSFT": "ai_capex_bullish",
    "GOOG": "ai_capex_bullish",
    "AMZN": "ai_capex_bullish",
    "NFLX": "streaming_margin_expansion",
    "NOW":  "enterprise_ai_software_bullish",
    "PANW": "cybersecurity_consolidation_bullish",
    "AXON": "public_safety_recurring_revenue_bullish",
    "PLTR": "enterprise_ai_software_bullish",
    "CEG":  "nuclear_near_term_bullish",
    "OKLO": "smr_long_duration_bullish",
    "SMR":  "smr_long_duration_bullish",
}

WATCHLIST: list[str] = list(WATCHLIST_THEMES)
