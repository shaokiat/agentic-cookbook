"""
Agent Tracer

A lightweight context-manager wrapper that intercepts every model call and
tool execution inside an agent run, building a structured trace tree without
modifying Agent or ModelProvider source code.

The trace captures:
  - Wall-clock latency per step and per tool call
  - Token usage per model call (via ModelProvider.cumulative_usage)
  - Tool call inputs and outputs
  - The full step sequence (think → act → think → ...)

After the run the tracer renders a Rich tree and returns a dict suitable for
JSON serialisation or downstream evaluation.

Usage:
  with AgentTracer(agent) as tracer:
      result = agent.run("Do something")
  tracer.print_report()

Docs: examples/05_evaluation_and_monitoring/02_agent_tracer.md
Reference: OpenClaw research/openclaw/src/agents/cache-trace.ts, Nanobot research/nanobot/nanobot/agent/hook.py
  data = tracer.to_dict()
"""
import time
import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

from dotenv import load_dotenv
from rich.console import Console
from rich.tree import Tree
from rich.panel import Panel
from rich.rule import Rule

from core.agent import Agent
from core.memory import Memory
from core.model import ModelProvider
from core.registry import ToolRegistry

load_dotenv()

console = Console()


# --- Trace data model --------------------------------------------------------

@dataclass
class ToolEvent:
    name: str
    arguments: dict
    result: str
    latency_ms: float
    is_error: bool


@dataclass
class Step:
    index: int
    thought: str | None
    tool_events: list[ToolEvent] = field(default_factory=list)
    latency_ms: float = 0.0


@dataclass
class Trace:
    agent_name: str
    user_input: str
    final_answer: str = ""
    steps: list[Step] = field(default_factory=list)
    total_latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "user_input": self.user_input,
            "final_answer": self.final_answer,
            "total_latency_ms": round(self.total_latency_ms, 1),
            "total_steps": len(self.steps),
            "total_tool_calls": sum(len(s.tool_events) for s in self.steps),
            "tokens": {
                "prompt": self.prompt_tokens,
                "completion": self.completion_tokens,
                "total": self.total_tokens,
            },
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "steps": [
                {
                    "index": s.index,
                    "thought": s.thought,
                    "latency_ms": round(s.latency_ms, 1),
                    "tools": [
                        {
                            "name": te.name,
                            "arguments": te.arguments,
                            "result": te.result[:200],
                            "latency_ms": round(te.latency_ms, 1),
                            "is_error": te.is_error,
                        }
                        for te in s.tool_events
                    ],
                }
                for s in self.steps
            ],
        }


# --- Tracer ------------------------------------------------------------------

class AgentTracer:
    """
    Wraps an Agent to capture a structured execution trace.

    Usage as context manager:
        with AgentTracer(agent) as tracer:
            result = agent.run("...")
        tracer.print_report()
    """

    def __init__(self, agent: Agent):
        self.agent = agent
        self.trace: Trace | None = None
        self._patches: list = []
        self._current_step: Step | None = None
        self._run_start: float = 0.0

    def __enter__(self):
        self._install_patches()
        return self

    def __exit__(self, *args):
        self._remove_patches()
        if self.trace and self._run_start:
            self.trace.total_latency_ms = (time.perf_counter() - self._run_start) * 1000
            usage = self.agent.model.get_cumulative_usage()
            self.trace.prompt_tokens = usage.prompt_tokens
            self.trace.completion_tokens = usage.completion_tokens
            self.trace.total_tokens = usage.total_tokens
            self.trace.estimated_cost_usd = usage.cost

    def _install_patches(self):
        original_run = self.agent.run
        original_generate = self.agent.model.generate
        original_call_tool = self.agent.registry.call_tool

        tracer = self

        def patched_run(user_input: str) -> str:
            tracer.trace = Trace(
                agent_name=tracer.agent.name,
                user_input=user_input,
            )
            tracer._run_start = time.perf_counter()
            result = original_run(user_input)
            tracer.trace.final_answer = result
            return result

        step_counter = [0]

        def patched_generate(messages, tools=None, tool_choice="auto"):
            step_counter[0] += 1
            t0 = time.perf_counter()
            response = original_generate(messages, tools=tools, tool_choice=tool_choice)
            elapsed = (time.perf_counter() - t0) * 1000
            step = Step(
                index=step_counter[0],
                thought=response.content,
                latency_ms=elapsed,
            )
            tracer._current_step = step
            if tracer.trace is not None:
                tracer.trace.steps.append(step)
            return response

        def patched_call_tool(name, arguments, context=None):
            t0 = time.perf_counter()
            try:
                result = original_call_tool(name, arguments, context=context)
                is_error = str(result).lower().startswith("error")
            except Exception as e:
                result = f"Error: {e}"
                is_error = True
            elapsed = (time.perf_counter() - t0) * 1000
            args_dict = {}
            try:
                import json as _json
                args_dict = _json.loads(arguments)
            except Exception:
                args_dict = {"raw": arguments}
            event = ToolEvent(
                name=name,
                arguments=args_dict,
                result=str(result),
                latency_ms=elapsed,
                is_error=is_error,
            )
            if tracer._current_step is not None:
                tracer._current_step.tool_events.append(event)
            return result

        self.agent.run = patched_run
        self.agent.model.generate = patched_generate
        self.agent.registry.call_tool = patched_call_tool

        self._originals = (original_run, original_generate, original_call_tool)

    def _remove_patches(self):
        orig_run, orig_gen, orig_call = self._originals
        self.agent.run = orig_run
        self.agent.model.generate = orig_gen
        self.agent.registry.call_tool = orig_call

    def print_report(self):
        if self.trace is None:
            console.print("[red]No trace captured.[/red]")
            return

        tree = Tree(f"[bold]{self.trace.agent_name}[/bold] — {self.trace.user_input[:60]}")

        for step in self.trace.steps:
            step_label = f"[cyan]Step {step.index}[/cyan] ({step.latency_ms:.0f}ms)"
            if step.thought:
                step_label += f" — {step.thought[:60]}..."
            step_node = tree.add(step_label)

            for te in step.tool_events:
                color = "red" if te.is_error else "green"
                args_str = json.dumps(te.arguments)[:60]
                step_node.add(
                    f"[{color}]{te.name}[/{color}]({args_str}) "
                    f"→ {te.result[:60]} [{te.latency_ms:.0f}ms]"
                )

        console.print(tree)
        console.print(
            Panel(
                f"Steps: {len(self.trace.steps)}  |  "
                f"Tool calls: {sum(len(s.tool_events) for s in self.trace.steps)}  |  "
                f"Latency: {self.trace.total_latency_ms:.0f}ms  |  "
                f"Tokens: {self.trace.total_tokens}  |  "
                f"Cost: ${self.trace.estimated_cost_usd:.4f}",
                title="[bold]Trace Summary[/bold]",
                border_style="blue",
            )
        )

    def to_dict(self) -> dict:
        return self.trace.to_dict() if self.trace else {}


# --- Demo --------------------------------------------------------------------

def add(a: int, b: int) -> int:
    """Add two integers. :param a: First number. :param b: Second number."""
    return a + b


def multiply(a: int, b: int) -> int:
    """Multiply two integers. :param a: First number. :param b: Second number."""
    return a * b


def count_words(text: str) -> int:
    """Count words in a string. :param text: Input text."""
    return len(text.split())


DEFAULT_PROMPT = (
    "Count the words in 'the quick brown fox jumps over the lazy dog', "
    "multiply that count by 4, then add 3 to the result."
)


def build_agent(model: str | None = None, max_steps: int = 8) -> Agent:
    registry = ToolRegistry()
    registry.register(add)
    registry.register(multiply)
    registry.register(count_words)

    return Agent(
        model=ModelProvider(model),
        memory=Memory(),
        registry=registry,
        system_prompt="You are a helpful calculator. Use tools to answer precisely.",
        max_steps=max_steps,
        verbose=False,
        name="CalcAgent",
    )


def run_traced(prompt: str, model: str | None = None) -> tuple[str, "AgentTracer"]:
    """Run the demo agent under the tracer; the tracer patches agent.run, so call run()."""
    agent = build_agent(model)
    with AgentTracer(agent) as tracer:
        result = agent.run(prompt)
    return result, tracer


def tracer_demo():
    console.print(Rule("[bold blue]Agent Tracer[/bold blue]"))

    result, tracer = run_traced(DEFAULT_PROMPT)

    console.print(f"\n[bold green]Final Answer:[/bold green] {result}\n")
    tracer.print_report()

    trace_data = tracer.to_dict()
    console.print(f"\n[dim]Trace dict keys: {list(trace_data.keys())}[/dim]")


if __name__ == "__main__":
    tracer_demo()
