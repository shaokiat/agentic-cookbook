"""
Async Announce Pattern
========================
Subagents run in background threads and push results into a shared queue when
they finish. The parent loop picks up completions as they arrive without
blocking — it can process other work between checks.

This mirrors OpenClaw's subagent-announce delivery system:
  child completes → pushes message to parent's session → parent picks it up
  as a normal user turn on the next iteration.

Key properties demonstrated:
  - Parent is non-blocking while workers are running
  - Results arrive in completion order (not spawn order)
  - Late-arriving workers don't block early-completing ones
  - Parent synthesizes only after all results are confirmed received

Docs: examples/03_multi_agent_systems/04_async_announce.md
Reference: OpenClaw research/openclaw/src/agents/subagent-announce.ts, Nanobot research/nanobot/nanobot/agent/subagent.py.
"""
import queue
import threading
import time
from dataclasses import dataclass, field
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

DEFAULT_TASKS = [
    ("MarketAnalyst", "What are the 3 biggest trends in the AI infrastructure market in 2025?"),
    ("TechStrategist", "What technical bottlenecks are limiting large-scale LLM deployment?"),
    ("PolicyResearcher", "What regulatory developments are shaping AI governance globally in 2025?"),
]


@dataclass
class Announcement:
    worker_id: str
    result: str
    elapsed: float


def spawn_background_worker(
    worker_id: str,
    task: str,
    announce_queue: "queue.Queue[Announcement]",
    model: str | None = None,
    model_provider: ModelProvider | None = None,
) -> threading.Thread:
    """Start a worker agent in a daemon thread; result is posted to the queue on completion."""
    def _run():
        start = time.perf_counter()
        worker = Agent(
            model=model_provider or ModelProvider(model),
            memory=Memory(),
            registry=ToolRegistry(),
            system_prompt="You are a specialist analyst. Answer the question concisely in 3-5 sentences.",
            name=worker_id,
            verbose=False,
        )
        result = worker.run(task)
        announce_queue.put(Announcement(worker_id=worker_id, result=result, elapsed=time.perf_counter() - start))

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


def run_synthesizer(announcements: list[Announcement], model: str | None = None,
                     model_provider: ModelProvider | None = None) -> str:
    """Combine all worker announcements into one analysis."""
    combined = "\n\n".join(
        f"**{ann.worker_id}**:\n{ann.result}" for ann in announcements
    )
    synthesizer = Agent(
        model=model_provider or ModelProvider(model),
        memory=Memory(),
        registry=ToolRegistry(),
        system_prompt="You are a synthesis expert. Combine specialist inputs into a unified analysis.",
        name="Synthesizer",
        verbose=False,
    )
    return synthesizer.run(f"Synthesize these specialist findings:\n\n{combined}")


def async_announce_demo(tasks: list[tuple[str, str]]):
    console.print(Rule("[bold blue]Async Announce Pattern[/bold blue]"))
    console.print(
        f"[dim]Spawning {len(tasks)} background workers. "
        "Parent continues while they run.[/dim]\n"
    )

    announce_queue: queue.Queue[Announcement] = queue.Queue()
    all_announcements: list[Announcement] = []

    # Spawn all workers — they run in the background immediately
    threads = []
    for worker_id, task in tasks:
        thread = spawn_background_worker(worker_id, task, announce_queue)
        threads.append(thread)
        console.print(f"[dim]→ Spawned:[/dim] [bold]{worker_id}[/bold]")

    console.print("\n[bold yellow]Parent loop is free to do other work while workers run...[/bold yellow]")

    # Parent event loop: poll for announcements, do simulated work between ticks
    tick = 0
    while len(all_announcements) < len(tasks):
        time.sleep(1.0)
        tick += 1

        # Drain all available announcements non-blocking
        newly_arrived: list[Announcement] = []
        try:
            while True:
                newly_arrived.append(announce_queue.get_nowait())
        except queue.Empty:
            pass

        all_announcements.extend(newly_arrived)

        for ann in newly_arrived:
            console.print(
                Panel(
                    ann.result,
                    title=f"[green]Announcement — {ann.worker_id}[/green] [dim]({ann.elapsed:.1f}s)[/dim]",
                    border_style="green",
                )
            )

        if newly_arrived:
            console.print(f"[dim]Tick {tick}: received {len(newly_arrived)} announcement(s) ({len(all_announcements)}/{len(tasks)} total)[/dim]")
        else:
            console.print(f"[dim]Tick {tick}: no new announcements, continuing other work...[/dim]")

    for thread in threads:
        thread.join()

    # Synthesize all results
    console.print(Rule("[bold green]All workers finished — synthesizing[/bold green]"))

    summary = run_synthesizer(all_announcements)
    console.print(Panel(summary, title="[bold]Synthesized Result[/bold]", border_style="blue"))


if __name__ == "__main__":
    async_announce_demo(DEFAULT_TASKS)
