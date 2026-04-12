import os
from dotenv import load_dotenv
from core.model import ModelProvider
from core.memory import Memory
from core.agent import Agent
from core.registry import ToolRegistry
from core.logger import AgentLogger
from rich.console import Console
from rich.panel import Panel

# Load environment variables
load_dotenv()

model = ModelProvider()
registry = ToolRegistry() # Empty registry for these agents
console = Console()

def reflexion_demo(task: str):
    log_path = "examples/logs/03_reflexion_log.md"
    
    console.print(Panel(f"[bold blue]Reflexion Agent[/bold blue]\n[dim]Task: {task}[/dim]", expand=False))
    
    # Phase 1: Drafting
    console.print("\n[bold yellow]\u2776 Phase 1: Generating Initial Attempt...[/bold yellow]")
    writer_agent = Agent(
        model=model,
        memory=Memory(),
        registry=registry,
        system_prompt="You are a creative writer. Your goal is to produce a high-quality initial draft.",
        log_path=log_path,
        verbose=False
    )
    attempt = writer_agent.run(task)
    console.print(Panel(attempt, title="Initial Attempt"))
    
    # Phase 2: Critique
    console.print("\n[bold magenta]\u2777 Phase 2: Self-Critiquing...[/bold magenta]")
    critic_agent = Agent(
        model=model,
        memory=Memory(),
        registry=registry,
        system_prompt="You are a critical reviewer. Review the provided text for style, tone, and logical clarity.",
        log_path=log_path,
        verbose=False
    )
    critique = critic_agent.run(f"Please critique this text:\n\n{attempt}")
    console.print(Panel(critique, title="Critique"))
    
    # Phase 3: Revision
    console.print("\n[bold cyan]\u2778 Phase 3: Revised Output...[/bold cyan]")
    revision_agent = Agent(
        model=model,
        memory=Memory(),
        registry=registry,
        system_prompt="You are an expert editor. Revise the original text based on the provided critique.",
        log_path=log_path,
        verbose=False
    )
    final_output = revision_agent.run(f"Original Text: {attempt}\n\nCritique: {critique}")
    console.print(Panel(final_output, title="Final Revised Output", border_style="green"))

if __name__ == "__main__":
    task = "Write a short poem about the concept of recursive agent loops in AI."
    reflexion_demo(task)
