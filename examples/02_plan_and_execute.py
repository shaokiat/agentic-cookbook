import os
from dotenv import load_dotenv
from core.model import ModelProvider
from core.memory import Memory
from core.registry import ToolRegistry
from core.agent import Agent
from tools.system_tools import list_files, read_file_content, execute_command

# Load environment variables
load_dotenv()

# Setup
registry = ToolRegistry()
registry.register(list_files)
registry.register(read_file_content)
registry.register(execute_command)

model = ModelProvider()

def plan_and_execute(goal: str):
    print(f"--- Plan-and-Execute Agent ---")
    print(f"Goal: {goal}")
    
    # Phase 1: Planning
    # We use a specialized prompt to create a plan
    planner_prompt = f"""You are a strategy planner. 
    Decompose the following goal into a numbered list of steps. 
    Do NOT execute the steps yet.
    Goal: {goal}"""
    
    planner_memory = Memory([{"role": "system", "content": "You are a strategic planner."}])
    planner_memory.add_message("user", planner_prompt)
    
    plan_response = model.generate(planner_memory.get_messages())
    plan = plan_response.content
    print(f"\n[bold green]PLAN GENERATED:[/bold green]\n{plan}\n")
    
    # Phase 2: Execution
    # We use our standard ReAct agent to execute the plan
    executor_agent = Agent(
        model=model,
        memory=Memory(),
        registry=registry,
        system_prompt=f"""You are an executor agent. 
        Your task is to follow this plan precisely to achieve the goal:
        {plan}"""
    )
    
    executor_agent.run("Begin executing the plan.")

if __name__ == "__main__":
    main_goal = "Analyze the project structure and create a summary of what the core/ directory does."
    plan_and_execute(main_goal)
