import json

import anthropic

from .logger import SessionLogger
from .prompts import SYSTEM_PROMPT
from .tools import TOOLS, process_tool_call
from . import state as state_store

MODEL = "claude-sonnet-4-6"

_SLASH_COMMANDS = "/summary, /strategy, /position, /exit"

_EXTRACTION_PROMPT = """\
Extract a structured session record from this research session. \
Return ONLY a valid JSON object — no prose, no markdown, no explanation — with exactly these fields:

{
  "price_at_analysis": <current price as a float, from the price data tool result>,
  "directional_bias": <"bullish" | "bearish" | "neutral">,
  "strategy_name": <name of the recommended strategy, e.g. "Bull Call Spread">,
  "trade": <specific contracts, e.g. "Buy $190 call / Sell $195 call, expiry Jun 20">,
  "max_profit": <e.g. "$320 per contract">,
  "max_loss": <e.g. "$180 per contract">,
  "breakeven": <e.g. "$191.80">,
  "iv_environment": <"low" | "high" | "unknown">,
  "key_themes": <list of 2-3 short strings summarising the main drivers, \
e.g. ["analyst upgrades", "IV compressed", "earnings beat"]>,
  "thesis": <one sentence directional argument>
}

If a field cannot be determined from the session data, use null."""

_SUMMARY_PROMPT = (
    "Summarise the research session so far in one paragraph: ticker, current price, "
    "directional thesis, key supporting data points, and the recommended strategy with strikes and expiry."
)
_STRATEGY_PROMPT = (
    "Re-state the current recommended strategy in the standard format:\n"
    "STRATEGY / OUTLOOK / TRADE / MAX PROFIT / MAX LOSS / BREAKEVEN / RATIONALE"
)
_POSITION_PROMPT = (
    "Re-state the user's current position in {ticker} as you understand it from this session, "
    "then comment on how it interacts with the recommended strategy (hedge, double-down, conflict, etc.)."
)


class ThetaAgent:
    """Research agent that fetches stock data and suggests options strategies."""

    def __init__(
        self,
        ticker: str,
        client: anthropic.Anthropic,
        positions: str | None = None,
        prior_context: str | None = None,
    ):
        self.ticker = ticker.upper()
        self.client = client
        self.positions = positions
        self.prior_context = prior_context  # compact summary of past sessions from state file

    def run_research(self) -> tuple[str, list]:
        """Run the agentic tool-use loop; return (summary, full_messages)."""
        print(f"\nResearching {self.ticker}...\n")
        logger = SessionLogger(self.ticker)

        initial_content = f"Research {self.ticker} and suggest one options strategy."
        if self.positions:
            initial_content += (
                f"\n\nCurrent position: {self.positions}\n"
                "Factor this existing position into your analysis — note whether the suggested "
                "strategy hedges, complements, or conflicts with it."
            )
        if self.prior_context:
            initial_content += f"\n\n{self.prior_context}"

        messages: list = [{"role": "user", "content": initial_content}]

        summary = "Research incomplete. Please try again."
        try:
            while True:
                logger.api_request(messages)
                response = self.client.messages.create(
                    model=MODEL,
                    max_tokens=2048,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                    messages=messages,
                )
                logger.api_response(response.stop_reason, response.content)

                if response.stop_reason == "end_turn":
                    messages.append({"role": "assistant", "content": response.content})
                    for block in response.content:
                        if hasattr(block, "text"):
                            summary = block.text
                            break
                    break

                if response.stop_reason == "tool_use":
                    messages.append({"role": "assistant", "content": response.content})

                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            print(f"  [tool] {block.name}({block.input.get('ticker', '')})")
                            result_str = process_tool_call(block.name, block.input)
                            logger.tool_call(block.name, block.input, result_str)
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_str,
                            })

                    messages.append({"role": "user", "content": tool_results})
                else:
                    break
        finally:
            logger.session_end()
            print(f"\n  [log] {logger.path}")

        return summary, messages

    def _save_session(self, messages: list) -> None:
        """Extract a structured record from the session and persist it."""
        print("  [state] extracting session record...")
        record = self._extract_session_record(messages)
        state_store.save(self.ticker, self.positions, record)
        print(f"  [state] state/{self.ticker}.json updated")

    def _extract_session_record(self, messages: list) -> dict:
        """
        Ask Claude to distil the session into a structured JSON record for state persistence.
        Uses the full in-memory message history so no data is re-fetched.
        Falls back to a minimal record on any error.
        """
        try:
            extraction_messages = list(messages) + [
                {"role": "user", "content": _EXTRACTION_PROMPT}
            ]
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=512,
                messages=extraction_messages,
            )
            raw = next(
                (block.text for block in response.content if hasattr(block, "text")),
                "{}",
            )
            # Strip accidental markdown fences if the model adds them
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip())
        except Exception:
            return {}

    def chat_loop(self, initial_summary: str, research_messages: list) -> None:
        """Run an interactive REPL for follow-up questions using full session context."""
        print("\n" + "=" * 60)
        print(f"  THETA-AGENT  |  {self.ticker}")
        print("=" * 60)
        print(initial_summary)
        print("\n" + "-" * 60)
        print(f"Commands: {_SLASH_COMMANDS}  |  or ask any follow-up question.")
        print("-" * 60)

        # Carry the full research history (including raw tool results) into the chat loop.
        messages = list(research_messages)

        while True:
            try:
                user_input = input("\nYou: ").strip()
            except (EOFError, KeyboardInterrupt):
                self._save_session(messages)
                print("Goodbye!")
                break

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit", "q", "/exit"):
                self._save_session(messages)
                print("Goodbye!")
                break

            # Slash command: inject a structured prompt instead of the raw user text.
            if user_input == "/summary":
                prompt = _SUMMARY_PROMPT
            elif user_input == "/strategy":
                prompt = _STRATEGY_PROMPT
            elif user_input == "/position":
                prompt = _POSITION_PROMPT.format(ticker=self.ticker)
            else:
                prompt = user_input

            messages.append({"role": "user", "content": prompt})
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=messages,
            )

            reply = next(
                (block.text for block in response.content if hasattr(block, "text")),
                "",
            )
            print(f"\nClaude: {reply}")
            messages.append({"role": "assistant", "content": reply})
