from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from core.model import ModelProvider
from core.memory import Memory
from core.registry import ToolRegistry
from core.logger import AgentLogger


@dataclass
class AgentEvent:
    kind: str  # "user" | "step_start" | "assistant" | "tool_call" | "observation" | "approval_request" | "max_steps" | "final"
    content: str = ""
    tool: str = ""
    args: str = ""
    step: int = 0


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

    def run_events(self, user_input: str) -> Iterator[AgentEvent]:
        """Run the Think-Act-Observe loop, yielding an event at each step."""
        self.memory.add_message("user", user_input)

        self.logger.log_event({
            "event": "run_start",
            "user_input": user_input,
            "agent_name": self.name
        }, overwrite=self.overwrite)

        yield AgentEvent("user", content=user_input)

        steps = 0
        final_from_act: Optional[AgentEvent] = None
        while steps < self.max_steps:
            steps += 1

            # 1. Think (Model Generation)
            yield AgentEvent("step_start", step=steps)
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
                yield AgentEvent("assistant", content=response.content, step=steps)

            # 3. Act (Tool Execution)
            if response.tool_calls:
                # Add the assistant message with tool calls to memory first
                self.memory.add_message(
                    "assistant",
                    response.content or "",
                    tool_calls=response.tool_calls
                )

                act = self._act(response.tool_calls, steps)
                sent = None
                while True:
                    try:
                        event = act.send(sent)
                    except StopIteration:
                        break
                    if event.kind == "final":
                        final_from_act = event
                    sent = yield event

                # A "final" from _act is the terminal-tool signal: stop the loop
                if final_from_act is not None:
                    break
                continue
            else:
                # No more tool calls, we are done
                break

        if final_from_act is not None:
            final_answer = final_from_act.content
        else:
            if steps >= self.max_steps:
                yield AgentEvent("max_steps", step=steps)
            final_answer = self.memory.get_messages()[-1]["content"] if self.memory.get_messages() else ""
            yield AgentEvent("final", content=final_answer, step=steps)

        self.logger.log_event({
            "event": "run_end",
            "final_answer": final_answer,
            "steps": steps,
            "agent_name": self.name
        }, overwrite=self.overwrite)

    def _act(self, tool_calls: List[Dict[str, Any]], step: int) -> Iterator[AgentEvent]:
        """Execute one turn's tool calls sequentially. Subclasses override this, not run()."""
        for tool_call in tool_calls:
            tool_name = tool_call["function"]["name"]
            tool_args = tool_call["function"]["arguments"]
            tool_call_id = tool_call["id"]

            yield AgentEvent("tool_call", tool=tool_name, args=tool_args, step=step)

            try:
                # Context can be passed here if needed (e.g. self for recursive calls)
                result = self.registry.call_tool(tool_name, tool_args, context=self)
                observation = str(result)
            except Exception as e:
                observation = f"Error: {str(e)}"

            yield AgentEvent("observation", content=observation, tool=tool_name, step=step)

            self.logger.log_event({
                "step": step,
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

    def run(self, user_input: str) -> str:
        """Drive run_events with terminal rendering; returns the final answer."""
        gen = self.run_events(user_input)
        final_answer = ""
        status = None
        sent = None
        while True:
            try:
                # The spinner (started on step_start) runs while the generator
                # computes the next event — i.e. during the model call.
                event = gen.send(sent)
            except StopIteration:
                break
            finally:
                if status is not None:
                    status.stop()
                    status = None
            sent = None

            if event.kind == "final":
                final_answer = event.content
            elif event.kind == "approval_request":
                sent = Confirm.ask(f"Approve [bold]{event.tool}[/bold]({event.args})?")
            elif event.kind == "step_start" and self.verbose:
                status = self.console.status(f"[bold green]Thinking (Step {event.step})...")
                status.start()

            if self.verbose:
                self._render(event)

        return final_answer

    def _render(self, event: AgentEvent) -> None:
        if event.kind == "user":
            self.console.print(Panel(f"[bold blue]User:[/bold blue] {event.content}"))
        elif event.kind == "assistant":
            self.console.print(Panel(f"[bold cyan]Assistant:[/bold cyan] {event.content}"))
        elif event.kind == "tool_call":
            self.console.print(f"[bold yellow]Tool Call:[/bold yellow] {event.tool}({event.args})")
        elif event.kind == "observation":
            self.console.print(f"[bold magenta]Observation:[/bold magenta] {event.content}")
        elif event.kind == "max_steps":
            self.console.print("[bold red]Reached max steps safety limit.[/bold red]")
