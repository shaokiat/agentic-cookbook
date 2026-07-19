"""
Sequential Pipeline (Baton-Pass Pattern)
==========================================
Chain specialized agents in sequence, each receiving the previous agent's
output as its input. Use this when later stages depend on earlier results.

Pipeline here: Researcher → Writer → Editor

Each agent is given a narrow, well-defined role. This specialization produces
better results than a single agent asked to do all three tasks.

Docs: examples/03_multi_agent_systems/03_sequential_pipeline.md
Reference: Nanobot research/nanobot/nanobot/agent/loop.py (message-bus chaining); related to
Reflexion but focused on specialization rather than self-critique.
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

DEFAULT_TOPIC = "The rise of agentic AI systems in 2025"

STAGES = [
    ("Researcher", "Research Notes",
     "You are a research specialist. Given a topic, produce a structured set of "
     "key facts, statistics, and insights. Focus on accuracy and depth. "
     "Format your output as numbered bullet points."),
    ("Writer", "Draft Article",
     "You are a technical writer. Transform research notes into a clear, "
     "engaging article with an introduction, body paragraphs, and conclusion. "
     "Write for a technically literate but non-expert audience."),
    ("Editor", "Final Article",
     "You are a senior editor. Polish the draft: improve clarity, fix any awkward "
     "phrasing, ensure logical flow, and tighten the prose. "
     "Return only the final edited article."),
]


def make_agent(name: str, system_prompt: str, model: str | None = None) -> Agent:
    return Agent(
        model=ModelProvider(model),
        memory=Memory(),
        registry=ToolRegistry(),
        system_prompt=system_prompt,
        name=name,
        verbose=False,
    )


def pipeline_steps(topic: str, model: str | None = None):
    """Yield (stage_title, text) as each pipeline stage completes."""
    research_notes = make_agent(STAGES[0][0], STAGES[0][2], model).run(
        f"Research this topic and provide key facts: {topic}")
    yield STAGES[0][1], research_notes

    draft = make_agent(STAGES[1][0], STAGES[1][2], model).run(
        f"Write an article based on these research notes:\n\n{research_notes}")
    yield STAGES[1][1], draft

    final_article = make_agent(STAGES[2][0], STAGES[2][2], model).run(
        f"Edit and polish this draft:\n\n{draft}")
    yield STAGES[2][1], final_article


def sequential_pipeline_demo(topic: str):
    console.print(Rule("[bold blue]Sequential Pipeline — Researcher → Writer → Editor[/bold blue]"))
    console.print(f"[dim]Topic: {topic}[/dim]\n")

    banners = [
        ("[bold yellow]❶ Research Stage[/bold yellow]", "yellow"),
        ("\n[bold cyan]❷ Writing Stage[/bold cyan]", "cyan"),
        ("\n[bold green]❸ Editing Stage[/bold green]", "green"),
    ]
    for (banner, style), (title, text) in zip(banners, pipeline_steps(topic)):
        console.print(banner)
        if title == "Final Article":
            console.print(Rule("[bold green]Final Article[/bold green]"))
            console.print(Panel(text, border_style="green"))
        else:
            console.print(Panel(text, title=title, border_style=style))


if __name__ == "__main__":
    sequential_pipeline_demo(DEFAULT_TOPIC)
