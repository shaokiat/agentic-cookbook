from typing import List, Dict, Any, Optional
from rich.console import Console
from rich.panel import Panel

from core.model import ModelProvider
from core.memory import Memory
from core.registry import ToolRegistry
from core.logger import AgentLogger

class Agent:
    def __init__(
        self, 
        model: ModelProvider, 
        memory: Memory, 
        registry: ToolRegistry,
        system_prompt: str = "You are a helpful assistant.",
        max_steps: int = 10,
        verbose: bool = True,
        log_path: Optional[str] = None,
        name: str = "Agent",
        overwrite: bool = True
    ):
        self.model = model
        self.memory = memory
        self.registry = registry
        self.system_prompt = system_prompt
        self.max_steps = max_steps
        self.verbose = verbose
        self.name = name
        self.overwrite = overwrite
        self.logger = AgentLogger(log_path)
        self.console = Console()

        # Initialize memory with system prompt if empty
        if not self.memory.get_messages():
            self.memory.add_message("system", self.system_prompt)

    def run(self, user_input: str) -> str:
        """
        Run the recursive Thinking-Acting loop.
        """
        self.memory.add_message("user", user_input)
        
        self.logger.log_event({
            "event": "run_start", 
            "user_input": user_input,
            "agent_name": self.name
        }, overwrite=self.overwrite)

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

            self.logger.log_event({
                "step": steps,
                "event": "think",
                "content": response.content,
                "tool_calls": response.tool_calls,
                "agent_name": self.name
            }, overwrite=self.overwrite)

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

                    self.logger.log_event({
                        "step": steps,
                        "event": "act",
                        "tool": tool_name,
                        "arguments": tool_args,
                        "observation": observation,
                        "agent_name": self.name
                    }, overwrite=self.overwrite)

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

        final_answer = self.memory.get_messages()[-1]["content"] if self.memory.get_messages() else ""
        self.logger.log_event({
            "event": "run_end", 
            "final_answer": final_answer, 
            "steps": steps,
            "agent_name": self.name
        }, overwrite=self.overwrite)
        return final_answer
