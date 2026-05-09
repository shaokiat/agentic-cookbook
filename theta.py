#!/usr/bin/env python3
"""theta-agent: options strategy research via Claude."""

import os
import sys

from dotenv import load_dotenv
import anthropic

from theta.agent import ThetaAgent
from theta import state as state_store

load_dotenv()


def _prompt_position(ticker: str, stored: str | None) -> str | None:
    """Ask the user to confirm, update, or clear their stored position."""
    if stored:
        print(f"\nStored position for {ticker}: {stored}")
        print("  Press Enter to keep, type a new position to update, or 'clear' to remove:")
        raw = input("  > ").strip()
        if raw.lower() == "clear":
            return None
        return raw if raw else stored
    else:
        print(f"\nCurrent position in {ticker} (optional — press Enter to skip):")
        raw = input("  > ").strip()
        return raw if raw else None


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python theta.py <TICKER>")
        print("Example: python theta.py AAPL")
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set.")
        sys.exit(1)

    ticker = sys.argv[1].upper()
    stored_state = state_store.load(ticker)
    prior_ctx = state_store.prior_context(stored_state)

    if prior_ctx:
        sessions = stored_state.get("sessions", [])
        print(f"\n  [state] {len(sessions)} previous session(s) found for {ticker}")

    positions = _prompt_position(ticker, stored_state.get("position"))

    client = anthropic.Anthropic(api_key=api_key)
    agent = ThetaAgent(
        ticker=ticker,
        client=client,
        positions=positions,
        prior_context=prior_ctx,
    )

    summary, messages = agent.run_research()
    agent.chat_loop(summary, messages)


if __name__ == "__main__":
    main()
