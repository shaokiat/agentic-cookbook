"""
Primitive 1: Tool Use / Function Calling

Demonstrates the full tool use lifecycle:
  1. Define a plain Python function as a tool.
  2. Register it — the ToolRegistry generates a JSON schema automatically.
  3. Run the agent — the model decides when to call the tool, your loop executes it.

Docs: docs/00_primitives/01_tool_use.md
"""
import os
from dotenv import load_dotenv
from core.model import ModelProvider
from core.memory import Memory
from core.registry import ToolRegistry
from core.agent import Agent

load_dotenv()


# --- Define tools as plain Python functions ---

def add(a: int, b: int) -> int:
    """
    Add two integers together.
    :param a: The first integer.
    :param b: The second integer.
    """
    return a + b


def multiply(a: int, b: int) -> int:
    """
    Multiply two integers together.
    :param a: The first integer.
    :param b: The second integer.
    """
    return a * b


def count_words(text: str) -> int:
    """
    Count the number of words in a text string.
    :param text: The text to count words in.
    """
    return len(text.split())


def summarize_history(context) -> str:
    """
    Summarize how many messages and tool calls have occurred in the conversation so far.
    """
    messages = context.memory.get_messages()
    tool_calls = [m for m in messages if m["role"] == "tool"]
    return f"Conversation has {len(messages)} messages total, including {len(tool_calls)} tool call results."


def main():
    print("--- Tool Use Primitive ---\n")

    model = ModelProvider()
    memory = Memory()
    registry = ToolRegistry()

    # Register tools — schemas are generated automatically from type hints + docstrings
    registry.register(add)
    registry.register(multiply)
    registry.register(count_words)
    registry.register(summarize_history)

    print("Registered tools and their schemas:")
    for schema in registry.get_schemas():
        fn = schema["function"]
        params = list(fn["parameters"]["properties"].keys())
        print(f"  {fn['name']}({', '.join(params) or 'no params'}) — {fn['description']}")
    print()

    agent = Agent(
        model=model,
        memory=memory,
        registry=registry,
        system_prompt="You are a helpful calculator assistant. Use the provided tools to answer questions accurately.",
        max_steps=10,
    )

    # The model will choose which tools to call and in what order
    result = agent.run(
        "I have a sentence: 'The quick brown fox jumps over the lazy dog'. "
        "First count the words in it, then multiply that count by 3, and finally add 7 to the result. "
        "Once done, summarize the conversation history."
    )

    print(f"\nFinal answer: {result}")


if __name__ == "__main__":
    main()
