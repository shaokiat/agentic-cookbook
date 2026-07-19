"""
Orchestrator-Worker Pattern
============================
An orchestrator agent breaks a complex task into subtasks and delegates each
to a specialized worker agent via a `delegate_to_agent` tool.

Key insight: tools can spawn agents. The orchestrator sees worker results as
ordinary tool observations, letting it synthesize across multiple specialists
without any custom plumbing.

Docs: examples/03_multi_agent_systems/01_orchestrator_worker.md
Reference: OpenClaw research/openclaw/src/agents/subagent-registry.ts, Nanobot research/nanobot/nanobot/agent/subagent.py (SubagentManager).
"""
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

DEFAULT_GOAL = (
    "Compare Python and Go as backend languages. "
    "Delegate research on each language to separate specialists, "
    "then synthesize a concise comparison covering performance, ecosystem, and ideal use cases."
)


def delegate_to_agent(role: str, task: str, context) -> str:
    """
    Spawn a worker agent with a specific role to complete a task.
    :param role: The specialist role for the worker (e.g. 'researcher', 'analyst').
    :param task: Detailed instructions for the worker to complete.
    """
    worker = Agent(
        model=context.model,
        memory=Memory(),
        registry=ToolRegistry(),
        system_prompt=f"You are a {role}. Complete the assigned task thoroughly and concisely.",
        name=role.capitalize(),
        verbose=False,
    )
    result = worker.run(task)
    console.print(Panel(result, title=f"[dim]Worker: {role.capitalize()}[/dim]", border_style="dim"))
    return result


def build_orchestrator(model: str | None = None, max_steps: int = 10) -> Agent:
    orchestrator_registry = ToolRegistry()
    orchestrator_registry.register(delegate_to_agent)

    return Agent(
        model=ModelProvider(model),
        memory=Memory(),
        registry=orchestrator_registry,
        system_prompt="""You are an orchestrator. Break complex goals into focused subtasks
and delegate each to a specialist worker using the delegate_to_agent tool.
After all workers report back, synthesize their findings into a final answer.""",
        name="Orchestrator",
        max_steps=max_steps,
    )


def orchestrator_worker_demo(goal: str):
    console.print(Rule("[bold blue]Orchestrator-Worker Pattern[/bold blue]"))
    console.print(f"[dim]Goal: {goal}[/dim]\n")

    result = build_orchestrator().run(goal)
    console.print(Rule("[bold green]Final Synthesis[/bold green]"))
    console.print(Panel(result, border_style="green"))


if __name__ == "__main__":
    orchestrator_worker_demo(DEFAULT_GOAL)
