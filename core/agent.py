from typing import List, Dict, Any, Optional
import json
from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.table import Table

from core.model import ModelProvider
from core.memory import Memory
from core.registry import ToolRegistry

class Agent:
    def __init__(
        self, 
        model: ModelProvider, 
        memory: Memory, 
        registry: ToolRegistry,
        system_prompt: str = "You are a helpful assistant.",
        max_steps: int = 10,
        verbose: bool = True
    ):
        self.model = model
        self.memory = memory
        self.registry = registry
        self.system_prompt = system_prompt
        self.max_steps = max_steps
        self.verbose = verbose
        self.console = Console()

        # Initialize memory with system prompt if empty
        if not self.memory.get_messages():
            self.memory.add_message("system", self.system_prompt)

    def run(self, user_input: str) -> str:
        """
        Run the recursive Thinking-Acting loop.
        """
        self.memory.add_message("user", user_input)
        
        if self.verbose:
            self.console.print(Panel(f"[bold blue]User:[/bold blue] {user_input}"))

        steps = 0
        while steps < self.max_steps:
            steps += 1
            
            # 1. Think (Model Generation)
            with self.console.status(f"[bold green]Thinking (Step {steps})..."):
                response = self.model.generate(
                    messages=self.memory.get_messages(),
                    tools=self.registry.get_schemas()
                )

            # 2. Observe (Handle Content)
            if response.content:
                self.memory.add_message("assistant", response.content)
                if self.verbose:
                    self.console.print(Panel(f"[bold cyan]Assistant:[/bold cyan] {response.content}"))

            # 3. Act (Tool Execution)
            if response.tool_calls:
                # Add the assistant message with tool calls to memory first
                self.memory.add_message(
                    "assistant", 
                    response.content or "", 
                    tool_calls=response.tool_calls
                )

                for tool_call in response.tool_calls:
                    tool_name = tool_call["function"]["name"]
                    tool_args = tool_call["function"]["arguments"]
                    tool_call_id = tool_call["id"]

                    if self.verbose:
                        self.console.print(f"[bold yellow]Tool Call:[/bold yellow] {tool_name}({tool_args})")

                    try:
                        # Context can be passed here if needed (e.g. self for recursive calls)
                        result = self.registry.call_tool(tool_name, tool_args, context=self)
                        observation = str(result)
                    except Exception as e:
                        observation = f"Error: {str(e)}"

                    if self.verbose:
                        self.console.print(f"[bold magenta]Observation:[/bold magenta] {observation}")

                    # Add tool result to memory
                    self.memory.add_message(
                        "tool", 
                        observation, 
                        tool_call_id=tool_call_id,
                        name=tool_name
                    )
                
                # Continue loop if tools were called
                continue
            else:
                # No more tool calls, we are done
                break

        if steps >= self.max_steps:
            if self.verbose:
                self.console.print("[bold red]Reached max steps safety limit.[/bold red]")

        return self.memory.get_messages()[-1]["content"] if self.memory.get_messages() else ""
