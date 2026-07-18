"""Per-ticker persistent state: current position and structured session history."""

import json
from datetime import datetime, timezone
from pathlib import Path

_STATE_DIR = Path("state")
_MAX_SESSIONS = 10


def _path(ticker: str) -> Path:
    return _STATE_DIR / f"{ticker}.json"


def load(ticker: str) -> dict:
    """Return stored state for ticker, or a blank template if none exists."""
    p = _path(ticker.upper())
    if p.exists():
        return json.loads(p.read_text())
    return {"ticker": ticker.upper(), "position": None, "sessions": []}


def save(ticker: str, position: str | None, record: dict) -> None:
    """Persist position and append a structured session record. Keeps the last _MAX_SESSIONS entries."""
    _STATE_DIR.mkdir(exist_ok=True)
    state = load(ticker)
    now = datetime.now(timezone.utc)
    state["last_updated"] = now.isoformat()
    state["position"] = position
    record.setdefault("date", now.strftime("%Y-%m-%d"))
    record.setdefault("outcome", None)
    state["sessions"].append(record)
    state["sessions"] = state["sessions"][-_MAX_SESSIONS:]
    _path(ticker.upper()).write_text(json.dumps(state, indent=2))


def prior_context(state: dict, max_sessions: int = 3) -> str | None:
    """
    Format the last N sessions into a plain-text block for prompt injection.
    Handles both structured records (v0.5+) and legacy plain-text summaries.
    Returns None when there are no previous sessions.
    """
    sessions = state.get("sessions", [])
    if not sessions:
        return None

    recent = sessions[-max_sessions:]
    lines = ["Prior sessions (most recent first):"]

    for s in reversed(recent):
        # Legacy format: session was saved as a plain string under "summary"
        if "summary" in s and not isinstance(s.get("strategy_name"), str):
            lines.append(f"  {s.get('date', 'unknown')}: {s['summary']}")
            continue

        # Structured format
        date = s.get("date", "unknown")
        price = s.get("price_at_analysis")
        bias = s.get("directional_bias", "unknown")
        strategy = s.get("strategy_name", "")
        trade = s.get("trade", "")
        max_profit = s.get("max_profit", "")
        max_loss = s.get("max_loss", "")
        breakeven = s.get("breakeven", "")
        iv_env = s.get("iv_environment", "")
        themes = s.get("key_themes", [])
        thesis = s.get("thesis", "")
        outcome = s.get("outcome")

        block = [f"  {date}:"]
        if price:
            block.append(f"    Price at analysis: ${price}")
        if bias:
            block.append(f"    Bias: {bias}")
        if thesis:
            block.append(f"    Thesis: {thesis}")
        if strategy:
            block.append(f"    Strategy: {strategy}")
        if trade:
            block.append(f"    Trade: {trade}")
        if max_profit or max_loss:
            block.append(f"    Max profit: {max_profit}  |  Max loss: {max_loss}  |  Breakeven: {breakeven}")
        if iv_env:
            block.append(f"    IV environment: {iv_env}")
        if themes:
            block.append(f"    Key themes: {', '.join(themes)}")
        if outcome:
            block.append(f"    Outcome: {outcome}")

        lines.append("\n".join(block))

    return "\n".join(lines)
