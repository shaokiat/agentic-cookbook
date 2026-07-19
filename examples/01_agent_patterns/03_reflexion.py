"""
Reflexion: Generate -> Critique -> Revise via three narrowly-prompted agents.

Docs: examples/01_agent_patterns/03_reflexion.md
Reference: conceptual pattern only — neither OpenClaw nor Nanobot ships a named Reflexion subsystem (see PROJECT_CONTEXT.md #7)
"""
import os
from dotenv import load_dotenv
from core.model import ModelProvider
from core.memory import Memory
from core.agent import Agent
from core.registry import ToolRegistry
from rich.console import Console
from rich.panel import Panel

# Load environment variables
load_dotenv()

console = Console()

DEFAULT_TASK = "Write a short poem about the concept of recursive agent loops in AI."

PHASES = [
    ("Writer", "Initial Attempt", "You are a creative writer. Your goal is to produce a high-quality initial draft."),
    ("Critic", "Critique", "You are a critical reviewer. Review the provided text for style, tone, and logical clarity."),
    ("Editor", "Final Revised Output", "You are an expert editor. Revise the original text based on the provided critique."),
]


def _phase_agent(name: str, system_prompt: str, model: str | None,
                  model_provider: ModelProvider | None = None) -> Agent:
    return Agent(
        model=model_provider or ModelProvider(model),
        memory=Memory(),
        registry=ToolRegistry(),  # Empty registry for these agents
        system_prompt=system_prompt,
        name=name,
        verbose=False,
    )


def reflexion_steps(task: str, model: str | None = None, model_provider: ModelProvider | None = None):
    """Yield (phase_title, text) as each Generate -> Critique -> Revise phase completes."""
    attempt = _phase_agent(PHASES[0][0], PHASES[0][2], model, model_provider).run(task)
    yield PHASES[0][1], attempt

    critique = _phase_agent(PHASES[1][0], PHASES[1][2], model, model_provider).run(
        f"Please critique this text:\n\n{attempt}")
    yield PHASES[1][1], critique

    final_output = _phase_agent(PHASES[2][0], PHASES[2][2], model, model_provider).run(
        f"Original Text: {attempt}\n\nCritique: {critique}")
    yield PHASES[2][1], final_output


def reflexion_demo(task: str):
    console.print(Panel(f"[bold blue]Reflexion Agent[/bold blue]\n[dim]Task: {task}[/dim]", expand=False))

    banners = [
        "\n[bold yellow]\u2776 Phase 1: Generating Initial Attempt...[/bold yellow]",
        "\n[bold magenta]\u2777 Phase 2: Self-Critiquing...[/bold magenta]",
        "\n[bold cyan]\u2778 Phase 3: Revised Output...[/bold cyan]",
    ]
    for banner, (title, text) in zip(banners, reflexion_steps(task)):
        console.print(banner)
        style = "green" if title == "Final Revised Output" else "none"
        console.print(Panel(text, title=title, border_style=style))

if __name__ == "__main__":
    reflexion_demo(DEFAULT_TASK)
