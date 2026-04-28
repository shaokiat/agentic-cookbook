"""
Intermediate Memory: Markdown Persistence

Demonstrates how facts can survive session restarts by writing them to a markdown
file and injecting that file into the system prompt at the start of each new session.
The agent in Session 2 starts with a completely empty Memory() yet recalls everything
saved in Session 1 — because the facts were persisted to disk, not to the context window.

Docs: examples/02_memory_management/01_markdown_persistence.md
"""
from pathlib import Path
from dotenv import load_dotenv
from core.model import ModelProvider
from core.memory import Memory
from core.registry import ToolRegistry
from core.agent import Agent

load_dotenv()

MEMORY_FILE = Path(__file__).parent / "memory_store.md"

# --- Persistent Memory Tools ---

def save_fact(fact: str) -> str:
    """Save a fact to persistent markdown memory so it survives session restarts.

    :param fact: The fact to remember, written as a plain sentence.
    """
    with open(MEMORY_FILE, "a") as f:
        f.write(f"- {fact}\n")
    return f"Saved to memory: {fact}"

def load_facts() -> str:
    """Load all facts saved to persistent markdown memory.

    """
    if not MEMORY_FILE.exists() or MEMORY_FILE.read_text().strip() == "":
        return "No facts saved yet."
    return MEMORY_FILE.read_text().strip()

# --- Session Factory ---

def make_agent(session_name: str) -> Agent:
    registry = ToolRegistry()
    registry.register(save_fact)
    registry.register(load_facts)

    # Prime the system prompt with whatever is already on disk.
    # This is the key mechanic: persistent context injected at session start.
    existing_facts = load_facts()
    system_prompt = f"""You are a helpful assistant with persistent memory across sessions.

--- Recalled from previous sessions ---
{existing_facts}
----------------------------------------

Use save_fact to remember new information for future sessions."""

    return Agent(
        model=ModelProvider(),
        memory=Memory(),
        registry=registry,
        system_prompt=system_prompt,
        name=session_name,
    )

# --- Demo ---

def main():
    # Clear state for a clean demo run
    if MEMORY_FILE.exists():
        MEMORY_FILE.unlink()

    print("\n" + "="*50)
    print("SESSION 1: Agent learns and saves facts")
    print("="*50)
    agent1 = make_agent("Session-1")
    agent1.run(
        "My name is Alice and I'm a researcher at Anthropic. "
        "My favourite model is Claude. Please save these facts."
    )

    print("\n" + "="*50)
    print("SESSION 2: Brand-new agent, same persistent memory")
    print("="*50)
    agent2 = make_agent("Session-2")
    agent2.run("What do you know about me? What is my favourite model?")

if __name__ == "__main__":
    main()
