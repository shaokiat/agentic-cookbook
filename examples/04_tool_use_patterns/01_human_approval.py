"""
Human-in-the-Loop (HIL) Tool Approval

When an agent wants to run a destructive action, an approval gate pauses
the loop until the user approves or denies. If denied, the tool never runs
and the agent reasons around the refusal observation.

Key insight: approval is loop policy, not tool internals. Tools stay pure;
the agent's tool-execution step checks a `requires_approval` marker and
yields an `approval_request` event — the surrounding UI (terminal, web page)
decides how to ask. This mirrors OpenClaw's tool-policy pipeline, where an
interactive-approval stage sits in front of execution.

Pattern: mark any dangerous callable with `@dangerous`; ApprovalAgent gates
it before execution.

Docs: examples/04_tool_use_patterns/01_human_approval.md
Reference: OpenClaw research/openclaw/src/agents/tool-policy-pipeline.ts + bash-tools.exec-approval-request.ts
"""
import os
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from core.agent import Agent, AgentEvent
from core.memory import Memory
from core.model import ModelProvider
from core.registry import ToolRegistry

load_dotenv()

console = Console()


# --- Approval marker ----------------------------------------------------------

def dangerous(func):
    """Mark a tool as requiring user approval before execution."""
    func.requires_approval = True
    return func


# --- Tools (pure — no prompting inside) ----------------------------------------

def list_directory(path: str) -> str:
    """
    List the files and directories at a given path.
    :param path: The filesystem path to list.
    """
    try:
        entries = os.listdir(path)
        return "\n".join(entries) if entries else "(empty directory)"
    except FileNotFoundError:
        return f"Error: path '{path}' does not exist."


@dangerous
def delete_file(path: str) -> str:
    """
    Permanently delete a file from the filesystem. Requires user approval.
    :param path: The path to the file to delete.
    """
    try:
        os.remove(path)
        return f"File '{path}' deleted successfully."
    except FileNotFoundError:
        return f"Error: file '{path}' does not exist."
    except OSError as e:
        return f"Error deleting file: {e}"


@dangerous
def write_file(path: str, content: str) -> str:
    """
    Write content to a file, creating it if it does not exist. Requires user approval.
    :param path: The path of the file to write.
    :param content: The text content to write into the file.
    """
    with open(path, "w") as f:
        f.write(content)
    return f"File '{path}' written successfully ({len(content)} chars)."


# --- ApprovalAgent -------------------------------------------------------------

class ApprovalAgent(Agent):
    """Gates marked tools behind an approval_request event before execution."""

    def _act(self, tool_calls, step):
        for tool_call in tool_calls:
            name = tool_call["function"]["name"]
            args = tool_call["function"]["arguments"]
            func = self.registry.tools.get(name)

            if func is not None and getattr(func, "requires_approval", False):
                if self.verbose:
                    console.print(
                        Panel(
                            f"[bold yellow]Agent wants to: {name}({args})[/bold yellow]",
                            title="[red]Approval Required[/red]",
                            border_style="red",
                        )
                    )
                approved = yield AgentEvent(
                    "approval_request", tool=name, args=args, step=step
                )
                if not approved:
                    observation = f"Action denied by user. Tool '{name}' was NOT executed."
                    yield AgentEvent("observation", content=observation, tool=name, step=step)
                    self.memory.add_message(
                        "tool", observation, tool_call_id=tool_call["id"], name=name
                    )
                    continue

            yield from super()._act([tool_call], step)


def build_agent(model: str | None = None, max_steps: int = 8) -> ApprovalAgent:
    registry = ToolRegistry()
    registry.register(list_directory)
    registry.register(write_file)
    registry.register(delete_file)

    return ApprovalAgent(
        model=ModelProvider(model),
        memory=Memory(),
        registry=registry,
        system_prompt=(
            "You are a file management assistant. "
            "You can list directories, write files, and delete files. "
            "Always list the directory first to understand what exists, "
            "then perform the requested operations."
        ),
        max_steps=max_steps,
        name="FileAgent",
    )


# --- Demo --------------------------------------------------------------------

def hil_demo():
    console.print(Panel("[bold blue]Human-in-the-Loop Tool Approval[/bold blue]"))
    console.print(
        "[dim]The agent will attempt file operations. "
        "You control whether each destructive action runs.[/dim]\n"
    )

    agent = build_agent()
    result = agent.run(
        "Create a temporary file at '/tmp/hil_demo.txt' with the content "
        "'Hello from the agent!', then list /tmp to confirm it exists, "
        "and finally delete the file."
    )

    console.print(Panel(result, title="[bold green]Final Result[/bold green]", border_style="green"))


if __name__ == "__main__":
    hil_demo()
