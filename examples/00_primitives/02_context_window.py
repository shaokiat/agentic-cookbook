"""
Primitive 2: The Context Window as Working Memory

Demonstrates how the context window fills up as the agent takes steps, and the
contrast between unbounded memory (everything accumulates) and windowed memory
(old messages are evicted to stay within limits).

Run with SHOW_FULL_CONTEXT=1 to print the raw message list after each step.

Docs: docs/00_primitives/02_context_window.md
"""
import os
from dotenv import load_dotenv
from core.model import ModelProvider
from core.memory import Memory
from core.registry import ToolRegistry
from core.agent import Agent

load_dotenv()

SHOW_FULL_CONTEXT = os.getenv("SHOW_FULL_CONTEXT", "0") == "1"


class InstrumentedMemory(Memory):
    """Memory that prints its message count after every addition."""

    def add_message(self, role: str, content: str, **kwargs):
        super().add_message(role, content, **kwargs)
        total_chars = sum(len(str(m.get("content", ""))) for m in self.messages)
        print(f"  [Memory] {len(self.messages)} messages | ~{total_chars} chars in context")
        if SHOW_FULL_CONTEXT:
            for i, m in enumerate(self.messages):
                snippet = str(m.get("content", ""))[:60].replace("\n", " ")
                print(f"    [{i}] {m['role']:10s} | {snippet}")


class WindowedMemory(Memory):
    """Keeps the system prompt + only the last `window_size` messages."""

    def __init__(self, window_size: int = 6):
        super().__init__()
        self.window_size = window_size

    def add_message(self, role: str, content: str, **kwargs):
        super().add_message(role, content, **kwargs)
        if len(self.messages) > self.window_size + 1:
            self.messages = [self.messages[0]] + self.messages[-self.window_size:]
            # Drop orphaned tool messages whose assistant+tool_calls was evicted
            while len(self.messages) > 1 and self.messages[1].get("role") == "tool":
                self.messages.pop(1)
        total_chars = sum(len(str(m.get("content", ""))) for m in self.messages)
        print(f"  [WindowedMemory] {len(self.messages)} messages kept | ~{total_chars} chars in context")


class AutoCompactMemory(Memory):
    """
    When message count exceeds `threshold`, calls the model to summarize old
    messages and replaces them with a single summary, keeping the last
    `keep_recent` messages intact.
    """

    def __init__(self, model: ModelProvider, threshold: int = 6, keep_recent: int = 3):
        super().__init__()
        self.model = model
        self.threshold = threshold
        self.keep_recent = keep_recent

    def add_message(self, role: str, content: str, **kwargs):
        super().add_message(role, content, **kwargs)
        if len(self.messages) > self.threshold + 1:
            self._compact()
        total_chars = sum(len(str(m.get("content", ""))) for m in self.messages)
        print(f"  [AutoCompactMemory] {len(self.messages)} messages kept | ~{total_chars} chars in context")

    def _compact(self):
        old = self.messages[1:-self.keep_recent]
        recent = self.messages[-self.keep_recent:]

        old_text = "\n".join(
            f"[{m['role']}]: {str(m.get('content', ''))[:300]}" for m in old
        )
        response = self.model.generate([{
            "role": "user",
            "content": (
                "Summarize these agent steps in 2-3 sentences. "
                "Preserve: tool results obtained, decisions made, open tasks.\n\n"
                + old_text
            )
        }])

        summary = {"role": "assistant", "content": f"[Compacted summary]: {response.content}"}
        print(f"  [AutoCompactMemory] Compacted {len(old)} messages into summary")
        self.messages = [self.messages[0], summary] + recent
        # Drop orphaned tool messages whose assistant+tool_calls was compacted away
        while len(self.messages) > 2 and self.messages[2].get("role") == "tool":
            self.messages.pop(2)


# --- Tools that produce verbose output to fill up context quickly ---

def get_history(topic: str) -> str:
    """
    Return a brief history of a topic.
    :param topic: The topic to get history for.
    """
    histories = {
        "python": (
            "Python was created by Guido van Rossum and first released in 1991. "
            "Python 2.0 was released in 2000 with list comprehensions and garbage collection. "
            "Python 3.0 was released in 2008, breaking backward compatibility to fix design flaws. "
            "Today Python is one of the most popular programming languages in the world."
        ),
        "internet": (
            "The Internet grew from ARPANET, a US military project from the 1960s. "
            "Tim Berners-Lee invented the World Wide Web in 1989. "
            "The dot-com boom of the late 1990s drove massive commercialisation. "
            "Today over 5 billion people are connected to the Internet."
        ),
        "llm": (
            "Large Language Models descend from the transformer architecture introduced in 2017. "
            "GPT-3 (2020) demonstrated that scale alone could produce remarkable capabilities. "
            "ChatGPT (2022) brought LLMs to mainstream awareness. "
            "Models like Claude, GPT-4, and Gemini now power a wide range of applications."
        ),
    }
    return histories.get(topic.lower(), f"No history found for '{topic}'.")


def summarize(text: str) -> str:
    """
    Return a one-sentence summary of a text.
    :param text: The text to summarize.
    """
    # Simulate a summary (in practice this would call the model)
    words = text.split()
    return " ".join(words[:12]) + "..."


def main():
    print("--- Context Window Primitive ---\n")

    model = ModelProvider()
    registry = ToolRegistry()
    registry.register(get_history)
    registry.register(summarize)

    system_prompt = (
        "You are a research assistant. Use get_history to fetch information, "
        "then summarize what you learned."
    )

    # --- Run 1: Unbounded memory ---
    print("=== Run 1: Unbounded Memory ===")
    memory_unbounded = InstrumentedMemory()
    agent_unbounded = Agent(
        model=model,
        memory=memory_unbounded,
        registry=registry,
        system_prompt=system_prompt,
        max_steps=8,
        verbose=False,
    )
    agent_unbounded.run(
        "Look up the history of Python and the history of LLMs, then summarize both."
    )
    print(f"\nFinal context size: {len(memory_unbounded.get_messages())} messages\n")

    # --- Run 2: Windowed memory (window=6) ---
    print("=== Run 2: Windowed Memory (window_size=6) ===")
    memory_windowed = WindowedMemory(window_size=6)
    agent_windowed = Agent(
        model=model,
        memory=memory_windowed,
        registry=registry,
        system_prompt=system_prompt,
        max_steps=8,
        verbose=False,
    )
    agent_windowed.run(
        "Look up the history of Python and the history of LLMs, then summarize both."
    )
    print(f"\nFinal context size: {len(memory_windowed.get_messages())} messages")
    print("(older messages were evicted to stay within the window)")

    # --- Run 3: Auto-compact (summarization at threshold) ---
    print("\n=== Run 3: Auto-Compact Memory (threshold=6, keep_recent=3) ===")
    memory_compact = AutoCompactMemory(model=model, threshold=6, keep_recent=3)
    agent_compact = Agent(
        model=model,
        memory=memory_compact,
        registry=registry,
        system_prompt=system_prompt,
        max_steps=8,
        verbose=False,
    )
    agent_compact.run(
        "Look up the history of Python and the history of LLMs, then summarize both."
    )
    print(f"\nFinal context size: {len(memory_compact.get_messages())} messages")
    print("(old messages were compressed into a summary instead of dropped)")


if __name__ == "__main__":
    main()
