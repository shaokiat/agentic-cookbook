import os
from dotenv import load_dotenv
from core.model import ModelProvider
from core.memory import Memory

# Load environment variables
load_dotenv()

model = ModelProvider()

def reflexion_demo(task: str):
    print(f"--- Reflexion Agent ---")
    print(f"Task: {task}")
    
    # Step 1: Initial Attempt
    print("\n[bold yellow]Step 1: Generating Initial Attempt...[/bold yellow]")
    memory = Memory([{"role": "system", "content": "You are a creative writer."}])
    memory.add_message("user", task)
    
    attempt = model.generate(memory.get_messages()).content
    print(f"Attempt:\n{attempt}")
    
    # Step 2: Critique
    print("\n[bold magenta]Step 2: Critiquing...[/bold magenta]")
    critique_prompt = f"""Review the following text for style, tone, and logical clarity. 
    Point out any flaws or areas for improvement.
    Text: {attempt}"""
    
    critique_memory = Memory([{"role": "system", "content": "You are a critical reviewer."}])
    critique_memory.add_message("user", critique_prompt)
    
    critique = model.generate(critique_memory.get_messages()).content
    print(f"Critique:\n{critique}")
    
    # Step 3: Revision
    print("\n[bold cyan]Step 3: Revising...[/bold cyan]")
    revision_prompt = f"""Revise the original text based on the following critique.
    Original Text: {attempt}
    Critique: {critique}"""
    
    memory.add_message("assistant", attempt)
    memory.add_message("user", revision_prompt)
    
    final_output = model.generate(memory.get_messages()).content
    print(f"Final Revised Output:\n{final_output}")

if __name__ == "__main__":
    task = "Write a short poem about the concept of recursive agent loops in AI."
    reflexion_demo(task)
