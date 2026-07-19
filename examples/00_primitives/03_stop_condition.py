"""
Primitive 3: The Stop Condition Problem

Demonstrates three stop mechanisms and what happens when they interact:
  1. Natural stop   — model emits no tool calls, loop breaks cleanly.
  2. Terminal tool  — model calls `finish()` explicitly to signal completion.
  3. Step cap       — loop exits after max_steps regardless of agent state.

Each scenario runs a separate agent so the behaviours are isolated.

Docs: examples/00_primitives/03_stop_condition.md
Reference: Nanobot research/nanobot/nanobot/agent/runner.py — max_iterations + stop_reason signals
"""
import os
from dotenv import load_dotenv
from core.model import ModelProvider
from core.memory import Memory
from core.registry import ToolRegistry
from core.agent import Agent, AgentEvent

load_dotenv()


# ---------------------------------------------------------------------------
# Scenario 1: Natural stop
# The model calls one tool then returns a text answer — loop exits via `break`.
# ---------------------------------------------------------------------------

def lookup_capital(country: str) -> str:
    """
    Look up the capital city of a country.
    :param country: The name of the country.
    """
    capitals = {
        "france": "Paris",
        "japan": "Tokyo",
        "brazil": "Brasília",
        "australia": "Canberra",
    }
    return capitals.get(country.lower(), f"Unknown capital for '{country}'")


def build_natural_agent(model: str | None = None) -> Agent:
    registry = ToolRegistry()
    registry.register(lookup_capital)
    return Agent(
        model=ModelProvider(model),
        memory=Memory(),
        registry=registry,
        system_prompt="Answer geography questions using the lookup_capital tool.",
        max_steps=5,
    )


def run_natural_stop():
    print("=== Scenario 1: Natural Stop ===")
    print("The model calls one tool then returns a text answer.\n")

    agent = build_natural_agent()
    result = agent.run("What is the capital of Japan?")
    final_messages = agent.memory.get_messages()
    print(f"\nStopped after {len(final_messages)} messages in context.")
    print(f"Stop reason: natural (no tool calls on final step)\n")


# ---------------------------------------------------------------------------
# Scenario 2: Terminal tool call
# The agent must call `finish()` to exit. The loop watches for this call
# explicitly and returns immediately, bypassing the normal break condition.
# ---------------------------------------------------------------------------

def search(query: str) -> str:
    """
    Search for information about a topic.
    :param query: The search query.
    """
    results = {
        "population of singapore": "Singapore has a population of approximately 5.9 million people.",
        "area of singapore": "Singapore covers an area of approximately 733 square kilometres.",
    }
    return results.get(query.lower(), "No results found.")


def finish(answer: str) -> str:
    """
    Signal that the task is complete and provide the final answer.
    Call this when you have gathered all required information.
    :param answer: The complete final answer to return to the user.
    """
    return answer


class TerminalToolAgent(Agent):
    """Agent that watches for a `finish` tool call and stops the loop immediately."""

    def _act(self, tool_calls, step):
        for tool_call in tool_calls:
            name = tool_call["function"]["name"]
            args = tool_call["function"]["arguments"]

            yield AgentEvent("tool_call", tool=name, args=args, step=step)
            result = str(self.registry.call_tool(name, args))
            yield AgentEvent("observation", content=result, tool=name, step=step)

            # Terminal tool: a `final` event makes the base loop exit immediately
            if name == "finish":
                yield AgentEvent("final", content=result, step=step)
                return

            self.memory.add_message(
                "tool", result, tool_call_id=tool_call["id"], name=name
            )


def build_terminal_agent(model: str | None = None) -> TerminalToolAgent:
    registry = ToolRegistry()
    registry.register(search)
    registry.register(finish)
    return TerminalToolAgent(
        model=ModelProvider(model),
        memory=Memory(),
        registry=registry,
        system_prompt=(
            "Answer questions by using the search tool to gather facts. "
            "When you have all the information needed, call finish() with your complete answer."
        ),
        max_steps=8,
        verbose=False,
    )


def run_terminal_tool():
    print("=== Scenario 2: Terminal Tool Call ===")
    print("The model must explicitly call finish() to signal completion.\n")

    agent = build_terminal_agent()

    result = ""
    saw_finish = False
    for event in agent.run_events("What is the population and area of Singapore?"):
        if event.kind == "observation":
            print(f"  Tool: {event.tool}  →  {event.content}")
            if event.tool == "finish":
                saw_finish = True
        elif event.kind == "final":
            result = event.content
            if saw_finish:
                print(f"\nStopped via terminal tool call at step {event.step}.")
    print(f"Final answer: {result}\n")


# ---------------------------------------------------------------------------
# Scenario 3: Step cap
# A deliberately broken tool always fails. The agent loops until max_steps.
# ---------------------------------------------------------------------------

def broken_tool(input: str) -> str:
    """
    A tool that always fails, simulating an unreliable external service.
    :param input: The input to process.
    """
    raise RuntimeError("Service unavailable. Please try again later.")


def build_capped_agent(model: str | None = None, max_steps: int = 3) -> Agent:
    registry = ToolRegistry()
    registry.register(broken_tool)
    return Agent(
        model=ModelProvider(model),
        memory=Memory(),
        registry=registry,
        system_prompt=(
            "You must use the broken_tool to complete your task. "
            "Keep trying even if it fails."
        ),
        max_steps=max_steps,  # low cap so the demo finishes quickly
    )


def run_step_cap():
    print("=== Scenario 3: Step Cap (Safety Net) ===")
    print("A broken tool causes the agent to loop. max_steps prevents infinite execution.\n")

    agent = build_capped_agent()
    result = agent.run("Use broken_tool to process the string 'hello'.")
    messages = agent.memory.get_messages()
    print(f"\nAgent stopped after hitting max_steps=3.")
    print(f"Total messages in context: {len(messages)}")
    print(f"Last message: {result[:120]}")


# ---------------------------------------------------------------------------

def main():
    run_natural_stop()
    run_terminal_tool()
    run_step_cap()


if __name__ == "__main__":
    main()
