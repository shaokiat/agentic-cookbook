"""
Plan-and-Execute: a planner call produces a global plan; a ReAct executor works through it.

Docs: examples/01_agent_patterns/02_plan_and_execute.md
Reference: OpenClaw research/openclaw/src/agents/runtime-plan/
"""
import os
from dotenv import load_dotenv
from core.model import ModelProvider
from core.memory import Memory
from core.registry import ToolRegistry
from core.agent import Agent
from tools.system_tools import list_files, read_file_content, execute_command

# Load environment variables
load_dotenv()

DEFAULT_GOAL = "Analyze the project structure and create a summary of what the core/ directory does."


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(list_files)
    registry.register(read_file_content)
    registry.register(execute_command)
    return registry


def make_plan(goal: str, model: str | None = None, model_provider: ModelProvider | None = None) -> str:
    planner_prompt = f"""You are a strategy planner.
    Decompose the following goal into a numbered list of steps.
    Do NOT execute the steps yet.
    Goal: {goal}"""

    planner_memory = Memory([{"role": "system", "content": "You are a strategic planner."}])
    planner_memory.add_message("user", planner_prompt)

    provider = model_provider or ModelProvider(model)
    return provider.generate(planner_memory.get_messages()).content


def build_executor(plan: str, model: str | None = None, model_provider: ModelProvider | None = None) -> Agent:
    return Agent(
        model=model_provider or ModelProvider(model),
        memory=Memory(),
        registry=build_registry(),
        system_prompt=f"""You are an executor agent.
        Your task is to follow this plan precisely to achieve the goal:
        {plan}

        IMPORTANT: You are already in the project directory. Use the provided tools (list_files, read_file_content, etc.) to explore the local filesystem."""
    )


def plan_and_execute(goal: str):
    print(f"--- Plan-and-Execute Agent ---")
    print(f"Goal: {goal}")

    # Phase 1: Planning
    plan = make_plan(goal)
    print(f"\n[bold green]PLAN GENERATED:[/bold green]\n{plan}\n")

    # Phase 2: Execution via the standard ReAct agent
    build_executor(plan).run("Begin executing the plan.")

if __name__ == "__main__":
    plan_and_execute(DEFAULT_GOAL)
