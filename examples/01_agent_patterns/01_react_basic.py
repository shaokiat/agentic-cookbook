"""
Basic ReAct agent: Thought -> Tool Call -> Observation loop over filesystem tools.

Docs: examples/01_agent_patterns/01_react_basic.md
Reference: OpenClaw research/openclaw/src/agents/pi-embedded-runner.ts, Nanobot research/nanobot/nanobot/agent/runner.py
"""
import os
from dotenv import load_dotenv
from core.model import ModelProvider
from core.memory import Memory
from core.registry import ToolRegistry
from core.agent import Agent
from tools.system_tools import list_files, read_file_content

# Load environment variables
load_dotenv()

DEFAULT_QUESTION = "What files are in the current directory? Can you read the README.md for me?"


def build_agent(model: str | None = None, max_steps: int = 10) -> Agent:
    # 1. Setup Tools
    registry = ToolRegistry()
    registry.register(list_files)
    registry.register(read_file_content)

    # 2. Setup Agent
    return Agent(
        model=ModelProvider(model),
        memory=Memory(),
        registry=registry,
        system_prompt="""You are a helpful file system assistant.
    You can list files and read their contents to answer questions.""",
        max_steps=max_steps,
    )


# 3. Run Agent
def main():
    print("--- Basic ReAct Agent ---")
    build_agent().run(DEFAULT_QUESTION)

if __name__ == "__main__":
    main()
