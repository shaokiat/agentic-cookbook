"""
Parallel Tool Call Execution

When the model returns multiple tool calls in one response, the default Agent
executes them sequentially. This example shows a ParallelAgent subclass that
dispatches the whole batch concurrently via ThreadPoolExecutor.

Key insight: the model already groups independent tool calls into one response.
Parallelising execution within that batch cuts wall-clock time without changing
the agent loop protocol — tool results are still assembled before the next turn.

Docs: examples/04_tool_use_patterns/02_parallel_tool_calls.md
Reference: OpenClaw research/openclaw/src/agents/pi-embedded-subscribe.ts dispatches all tool
calls in a response concurrently. Nanobot uses concurrent_tools=True in AgentRunner
(research/nanobot/nanobot/agent/runner.py).
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from core.agent import Agent, AgentEvent
from core.memory import Memory
from core.model import ModelProvider
from core.registry import ToolRegistry

load_dotenv()

console = Console()


# --- Slow tools that benefit from concurrency --------------------------------

def fetch_weather(city: str) -> str:
    """
    Fetch the current weather for a city. (Simulated — takes ~1 second.)
    :param city: The name of the city to fetch weather for.
    """
    time.sleep(1.0)
    data = {
        "London": "15°C, cloudy",
        "Tokyo": "22°C, sunny",
        "New York": "18°C, partly cloudy",
        "Sydney": "25°C, clear",
    }
    return data.get(city, f"Weather data unavailable for {city}")


def fetch_exchange_rate(currency: str) -> str:
    """
    Fetch the USD exchange rate for a currency. (Simulated — takes ~1 second.)
    :param currency: The three-letter currency code (e.g. EUR, JPY, GBP).
    """
    time.sleep(1.0)
    rates = {"EUR": 0.92, "JPY": 149.5, "GBP": 0.79, "AUD": 1.53}
    rate = rates.get(currency.upper())
    if rate is None:
        return f"Exchange rate unavailable for {currency}"
    return f"1 USD = {rate} {currency.upper()}"


def fetch_news_headline(topic: str) -> str:
    """
    Fetch the top news headline for a topic. (Simulated — takes ~1 second.)
    :param topic: The topic to fetch a headline for (e.g. technology, sports).
    """
    time.sleep(1.0)
    headlines = {
        "technology": "AI Models Reach New Reasoning Benchmarks in 2025",
        "sports": "Record Attendance at Global Athletics Championships",
        "finance": "Central Banks Signal Cautious Rate Paths Ahead",
    }
    return headlines.get(topic.lower(), f"No headline available for topic: {topic}")


# --- ParallelAgent -----------------------------------------------------------

class ParallelAgent(Agent):
    """
    Subclass of Agent that executes multiple tool calls concurrently
    instead of sequentially within a single model turn.
    """

    def _execute_tool_calls(self, tool_calls: list) -> list[tuple[str, str, str]]:
        """
        Execute all tool calls in parallel.
        Returns list of (tool_call_id, tool_name, observation) tuples.
        """
        def run_one(tc):
            name = tc["function"]["name"]
            args = tc["function"]["arguments"]
            tc_id = tc["id"]
            try:
                result = self.registry.call_tool(name, args, context=self)
                return tc_id, name, str(result)
            except Exception as e:
                return tc_id, name, f"Error: {e}"

        with ThreadPoolExecutor(max_workers=len(tool_calls)) as executor:
            futures = [executor.submit(run_one, tc) for tc in tool_calls]
            return [f.result() for f in as_completed(futures)]

    def _act(self, tool_calls, step):
        n = len(tool_calls)
        if self.verbose:
            console.print(f"[bold yellow]Executing {n} tool call(s) in parallel...[/bold yellow]")
        for tc in tool_calls:
            yield AgentEvent(
                "tool_call", tool=tc["function"]["name"],
                args=tc["function"]["arguments"], step=step,
            )

        t0 = time.perf_counter()
        results = self._execute_tool_calls(tool_calls)
        elapsed = time.perf_counter() - t0

        for tc_id, name, observation in results:
            yield AgentEvent("observation", content=observation, tool=name, step=step)
            self.memory.add_message("tool", observation, tool_call_id=tc_id, name=name)

        if self.verbose:
            console.print(f"[dim]All {n} tool(s) completed in {elapsed:.2f}s[/dim]")


# --- Demo: compare sequential vs parallel ------------------------------------

DEFAULT_PROMPT = (
    "I need three things at once: the weather in London, "
    "the USD to EUR exchange rate, and the top technology headline. "
    "Fetch all three, then give me a combined summary."
)


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(fetch_weather)
    registry.register(fetch_exchange_rate)
    registry.register(fetch_news_headline)
    return registry


def _run_sequential(registry: ToolRegistry, prompt: str, model: str | None = None,
                     model_provider: ModelProvider | None = None) -> tuple[str, float]:
    agent = Agent(
        model=model_provider or ModelProvider(model),
        memory=Memory(),
        registry=registry,
        system_prompt="You are a helpful assistant. Call all relevant tools to answer.",
        max_steps=5,
        verbose=False,
    )
    t0 = time.perf_counter()
    result = agent.run(prompt)
    return result, time.perf_counter() - t0


def build_parallel_agent(registry: ToolRegistry | None = None, model: str | None = None, verbose: bool = True,
                          model_provider: ModelProvider | None = None) -> "ParallelAgent":
    return ParallelAgent(
        model=model_provider or ModelProvider(model),
        memory=Memory(),
        registry=registry or build_registry(),
        system_prompt="You are a helpful assistant. Call all relevant tools to answer.",
        max_steps=5,
        verbose=verbose,
    )


def _run_parallel(registry: ToolRegistry, prompt: str, model: str | None = None) -> tuple[str, float]:
    agent = ParallelAgent(
        model=ModelProvider(model),
        memory=Memory(),
        registry=registry,
        system_prompt="You are a helpful assistant. Call all relevant tools to answer.",
        max_steps=5,
        verbose=True,
    )
    t0 = time.perf_counter()
    result = agent.run(prompt)
    return result, time.perf_counter() - t0


def parallel_tools_demo():
    console.print(Rule("[bold blue]Parallel Tool Call Execution[/bold blue]"))

    registry = build_registry()
    prompt = DEFAULT_PROMPT

    console.print("[bold yellow]Sequential execution...[/bold yellow]")
    _, seq_time = _run_sequential(registry, prompt)

    console.print(f"\n[bold cyan]Parallel execution...[/bold cyan]")
    result, par_time = _run_parallel(registry, prompt)

    table = Table(title="Execution Time Comparison")
    table.add_column("Mode", style="bold")
    table.add_column("Time (s)", justify="right")
    table.add_column("Speedup", justify="right")
    table.add_row("Sequential", f"{seq_time:.2f}s", "1.0×")
    table.add_row(
        "Parallel",
        f"{par_time:.2f}s",
        f"[green]{seq_time / par_time:.1f}×[/green]",
    )
    console.print(table)
    console.print(Panel(result, title="[bold]Final Answer[/bold]", border_style="green"))


if __name__ == "__main__":
    parallel_tools_demo()
