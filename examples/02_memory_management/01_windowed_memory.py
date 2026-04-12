import os
from dotenv import load_dotenv
from core.model import ModelProvider
from core.memory import Memory
from core.registry import ToolRegistry
from core.agent import Agent

# Load environment variables
load_dotenv()

class WindowedMemory(Memory):
    """
    A specialized memory implementation that only keeps the last N messages
    to stay within context window limits.
    """
    def __init__(self, window_size: int = 5):
        super().__init__()
        self.window_size = window_size

    def add_message(self, role: str, content: str, **kwargs):
        super().add_message(role, content, **kwargs)
        # Keep system prompt (index 0) + last N messages
        if len(self.messages) > self.window_size + 1:
            self.messages = [self.messages[0]] + self.messages[-(self.window_size):]

def main():
    print("--- Windowed Memory Example ---")
    
    # 1. Setup
    model = ModelProvider()
    memory = WindowedMemory(window_size=3) # Very small window for demonstration
    registry = ToolRegistry() # Empty registry for this concept
    
    agent = Agent(
        model=model,
        memory=memory,
        registry=registry,
        system_prompt="You are a helpful assistant with a short memory."
    )
    
    # 2. Run multiple turns to see windowing in action
    prompts = [
        "My name is Alice.",
        "I like apples.",
        "I live in Wonderland.",
        "What is my name and what do I like?" # By now, "Alice" might be forgotten!
    ]
    
    for p in prompts:
        print(f"\nUser: {p}")
        response = agent.run(p)
        print(f"Agent: {response}")
        print(f"Memory count: {len(memory.get_messages())}")

if __name__ == "__main__":
    main()
