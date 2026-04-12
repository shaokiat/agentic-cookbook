import os
from dotenv import load_dotenv
from core.model import ModelProvider
from core.memory import Memory
from core.registry import ToolRegistry
from core.agent import Agent
from tools.system_tools import list_files, read_file_content

# Load environment variables
load_dotenv()

# 1. Setup Tools
registry = ToolRegistry()
registry.register(list_files)
registry.register(read_file_content)

# 2. Setup Agent
model = ModelProvider()
memory = Memory()
agent = Agent(
    model=model, 
    memory=memory, 
    registry=registry,
    system_prompt="""You are a helpful file system assistant. 
    You can list files and read their contents to answer questions."""
)

# 3. Run Agent
def main():
    print("--- Basic ReAct Agent ---")
    question = "What files are in the current directory? Can you read the README.md for me?"
    agent.run(question)

if __name__ == "__main__":
    main()
