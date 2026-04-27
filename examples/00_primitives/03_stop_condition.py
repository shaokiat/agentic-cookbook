"""
Primitive 3: The Stop Condition Problem

Demonstrates three stop mechanisms and what happens when they interact:
  1. Natural stop   — model emits no tool calls, loop breaks cleanly.
  2. Terminal tool  — model calls `finish()` explicitly to signal completion.
  3. Step cap       — loop exits after max_steps regardless of agent state.

Each scenario runs a separate agent so the behaviours are isolated.

Docs: docs/00_primitives/03_stop_condition.md
"""
import os
from dotenv import load_dotenv
from core.model import ModelProvider
from core.memory import Memory
from core.registry import ToolRegistry
from core.agent import Agent

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


def run_natural_stop():
    print("=== Scenario 1: Natural Stop ===")
    print("The model calls one tool then returns a text answer.\n")

    model = ModelProvider()
    memory = Memory()
    registry = ToolRegistry()
    registry.register(lookup_capital)

    agent = Agent(
        model=model,
        memory=memory,
        registry=registry,
        system_prompt="Answer geography questions using the lookup_capital tool.",
        max_steps=5,
    )

    result = agent.run("What is the capital of Japan?")
    final_messages = memory.get_messages()
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
    """Agent that watches for a `finish` tool call and exits immediately."""

    def run(self, user_input: str) -> str:
        self.memory.add_message("user", user_input)
        steps = 0

        while steps < self.max_steps:
            steps += 1
            response = self.model.generate(
                messages=self.memory.get_messages(),
                tools=self.registry.get_schemas(),
            )

            if response.content:
                self.memory.add_message("assistant", response.content)

            if response.tool_calls:
                self.memory.add_message(
                    "assistant", response.content or "", tool_calls=response.tool_calls
                )
                for tool_call in response.tool_calls:
                    name = tool_call["function"]["name"]
                    args = tool_call["function"]["arguments"]

                    result = self.registry.call_tool(name, args)
                    print(f"  Tool: {name}  →  {result}")

                    # Terminal tool: exit immediately with the answer
                    if name == "finish":
                        print(f"\nStopped via terminal tool call at step {steps}.")
                        return result

                    self.memory.add_message(
                        "tool", str(result), tool_call_id=tool_call["id"], name=name
                    )
                continue
            else:
                break

        return self.memory.get_messages()[-1]["content"]


def run_terminal_tool():
    print("=== Scenario 2: Terminal Tool Call ===")
    print("The model must explicitly call finish() to signal completion.\n")

    model = ModelProvider()
    memory = Memory()
    registry = ToolRegistry()
    registry.register(search)
    registry.register(finish)

    agent = TerminalToolAgent(
        model=model,
        memory=memory,
        registry=registry,
        system_prompt=(
            "Answer questions by using the search tool to gather facts. "
            "When you have all the information needed, call finish() with your complete answer."
        ),
        max_steps=8,
        verbose=False,
    )

    result = agent.run("What is the population and area of Singapore?")
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


def run_step_cap():
    print("=== Scenario 3: Step Cap (Safety Net) ===")
    print("A broken tool causes the agent to loop. max_steps prevents infinite execution.\n")

    model = ModelProvider()
    memory = Memory()
    registry = ToolRegistry()
    registry.register(broken_tool)

    agent = Agent(
        model=model,
        memory=memory,
        registry=registry,
        system_prompt=(
            "You must use the broken_tool to complete your task. "
            "Keep trying even if it fails."
        ),
        max_steps=3,  # low cap so the demo finishes quickly
    )

    result = agent.run("Use broken_tool to process the string 'hello'.")
    messages = memory.get_messages()
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
