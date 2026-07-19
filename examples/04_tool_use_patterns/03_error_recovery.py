"""
Tool Error Recovery

Two layers of resilience for flaky tools:

  Layer 1 — Tool-level retry: a decorator retries the raw function up to N
    times with exponential backoff before giving up. Transient failures
    (network blips, rate limits) are invisible to the agent.

  Layer 2 — Agent-level reasoning: if the tool still fails after retries,
    the error string becomes a tool observation. The agent reads it and
    reasons around it — falling back to a different tool, rephrasing, or
    gracefully degrading.

Key insight: returning a descriptive error string is always better than
raising an exception out of the tool. The agent can act on a string;
an uncaught exception just crashes the turn.

Docs: examples/04_tool_use_patterns/03_error_recovery.md
Reference: Nanobot research/nanobot/nanobot/agent/runner.py (provider retry + checkpoint restore)
"""
import random
import time
import functools
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from core.agent import Agent
from core.memory import Memory
from core.model import ModelProvider
from core.registry import ToolRegistry

load_dotenv()

console = Console()


# --- Layer 1: retry decorator ------------------------------------------------

def with_retry(max_attempts: int = 3, base_delay: float = 0.5):
    """
    Decorator that retries a tool function on exception with exponential backoff.
    After max_attempts failures the last error is returned as a string.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    delay = base_delay * (2 ** (attempt - 1))
                    console.print(
                        f"  [yellow]Attempt {attempt}/{max_attempts} failed: {e}. "
                        f"Retrying in {delay:.1f}s...[/yellow]"
                    )
                    time.sleep(delay)
            return f"Error after {max_attempts} attempts: {last_error}"
        return wrapper
    return decorator


# --- Flaky tools -------------------------------------------------------------

@with_retry(max_attempts=3, base_delay=0.3)
def fetch_stock_price(symbol: str) -> str:
    """
    Fetch the current stock price for a ticker symbol. May fail transiently.
    :param symbol: The stock ticker symbol (e.g. AAPL, GOOG).
    """
    if random.random() < 0.6:
        raise ConnectionError(f"Upstream API timeout for {symbol}")
    prices = {"AAPL": 189.45, "GOOG": 175.20, "MSFT": 415.30, "AMZN": 188.10}
    price = prices.get(symbol.upper())
    if price is None:
        return f"Error: unknown symbol '{symbol}'"
    return f"{symbol.upper()}: ${price:.2f}"


def fetch_cached_price(symbol: str) -> str:
    """
    Fetch a cached (possibly stale) stock price as a fallback.
    :param symbol: The stock ticker symbol (e.g. AAPL, GOOG).
    """
    cache = {"AAPL": 187.00, "GOOG": 173.50, "MSFT": 412.00, "AMZN": 186.75}
    price = cache.get(symbol.upper())
    if price is None:
        return f"No cached price for '{symbol}'"
    return f"{symbol.upper()} (cached, may be stale): ${price:.2f}"


def get_market_summary() -> str:
    """
    Get a general market summary when individual prices are unavailable.
    """
    return (
        "Markets mixed today. Tech sector slightly up (+0.3%). "
        "Energy down (-0.8%). Broad indices near flat."
    )


# --- Demo --------------------------------------------------------------------

DEFAULT_PROMPT = (
    "What is the current stock price for AAPL and GOOG? "
    "If live prices are unavailable, use whatever data you can find."
)


def build_agent(model: str | None = None, max_steps: int = 10) -> Agent:
    registry = ToolRegistry()
    registry.register(fetch_stock_price)
    registry.register(fetch_cached_price)
    registry.register(get_market_summary)

    return Agent(
        model=ModelProvider(model),
        memory=Memory(),
        registry=registry,
        system_prompt=(
            "You are a financial data assistant. "
            "Prefer live stock prices, but if they are unavailable, "
            "use cached prices or a market summary as a fallback. "
            "Always tell the user which data source you used."
        ),
        max_steps=max_steps,
        name="FinanceAgent",
    )


def error_recovery_demo():
    console.print(Rule("[bold blue]Tool Error Recovery[/bold blue]"))
    console.print(
        "[dim]fetch_stock_price fails ~60% of attempts (3 retries). "
        "The agent falls back to cached prices or a market summary.[/dim]\n"
    )

    result = build_agent().run(DEFAULT_PROMPT)

    console.print(Panel(result, title="[bold green]Final Answer[/bold green]", border_style="green"))


if __name__ == "__main__":
    error_recovery_demo()
