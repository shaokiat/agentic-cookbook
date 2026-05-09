"""
Parallel Subagents (Fan-Out Pattern)
======================================
Spawn multiple independent worker agents concurrently and aggregate their results.

Use this when subtasks are independent — running them in parallel cuts wall-clock
time proportionally to the number of workers. Sequential execution of the same tasks
is shown first so the speedup is visible.

Reference: Nanobot `concurrent_tools=True`, OpenClaw parallel tool dispatch.
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from core.agent import Agent
from core.memory import Memory
from core.model import ModelProvider
from core.registry import ToolRegistry

load_dotenv()

console = Console()
model = ModelProvider()


def run_worker(role: str, task: str) -> tuple[str, str]:
    """Run a single worker agent and return (role, result)."""
    worker = Agent(
        model=model,
        memory=Memory(),
        registry=ToolRegistry(),
        system_prompt=f"You are a {role}. Answer the question concisely in 3-5 sentences.",
        name=role,
        verbose=False,
    )
    return role, worker.run(task)


def run_sequential(tasks: list[tuple[str, str]]) -> tuple[dict[str, str], float]:
    """Run workers one after another and measure elapsed time."""
    start = time.perf_counter()
    results = {}
    for role, task in tasks:
        role_result, result = run_worker(role, task)
        results[role_result] = result
    elapsed = time.perf_counter() - start
    return results, elapsed


def run_parallel(tasks: list[tuple[str, str]]) -> tuple[dict[str, str], float]:
    """Run workers concurrently and measure elapsed time."""
    start = time.perf_counter()
    results = {}
    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {executor.submit(run_worker, role, task): role for role, task in tasks}
        for future in as_completed(futures):
            role, result = future.result()
            results[role] = result
    elapsed = time.perf_counter() - start
    return results, elapsed


def parallel_subagents_demo(tasks: list[tuple[str, str]]):
    console.print(Rule("[bold blue]Parallel Subagents — Fan-Out Pattern[/bold blue]"))
    console.print(f"[dim]Spawning {len(tasks)} workers: {[r for r, _ in tasks]}[/dim]\n")

    console.print("[bold yellow]Running sequentially...[/bold yellow]")
    sequential_results, sequential_time = run_sequential(tasks)

    console.print(f"\n[bold cyan]Running in parallel...[/bold cyan]")
    parallel_results, parallel_time = run_parallel(tasks)

    # Display results
    for role, result in parallel_results.items():
        console.print(Panel(result, title=f"[dim]{role}[/dim]", border_style="dim"))

    # Timing comparison
    table = Table(title="Execution Time Comparison")
    table.add_column("Mode", style="bold")
    table.add_column("Time (s)", justify="right")
    table.add_column("Speedup", justify="right")
    table.add_row("Sequential", f"{sequential_time:.1f}s", "1.0×")
    table.add_row(
        "Parallel",
        f"{parallel_time:.1f}s",
        f"[green]{sequential_time / parallel_time:.1f}×[/green]",
    )
    console.print(table)

    # Aggregator synthesizes all worker outputs
    console.print(Rule("[bold green]Aggregating Results[/bold green]"))
    combined = "\n\n".join(f"**{role}**:\n{res}" for role, res in parallel_results.items())
    aggregator = Agent(
        model=model,
        memory=Memory(),
        registry=ToolRegistry(),
        system_prompt="You are a synthesis expert. Combine the specialist reports into a unified summary.",
        name="Aggregator",
        verbose=False,
    )
    summary = aggregator.run(f"Synthesize these specialist reports:\n\n{combined}")
    console.print(Panel(summary, title="[bold]Aggregated Summary[/bold]", border_style="green"))


if __name__ == "__main__":
    tasks = [
        ("Python Expert", "What are Python's biggest strengths for data science in 2025?"),
        ("Go Expert", "What are Go's biggest strengths for backend services in 2025?"),
        ("Rust Expert", "What are Rust's biggest strengths for systems programming in 2025?"),
    ]
    parallel_subagents_demo(tasks)
