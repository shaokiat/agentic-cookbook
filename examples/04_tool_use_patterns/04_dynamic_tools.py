"""
Dynamic Tool Loading

Tools don't have to be registered at startup. This example shows two
runtime loading patterns:

  Pattern A — Capability-scoped loading: register only the tools relevant
    to the current task. Reduces the schema list the model sees, which
    lowers prompt tokens and avoids confusing the model with irrelevant options.

  Pattern B — Plugin discovery: scan a namespace for functions that carry a
    marker attribute and register them automatically. New tools are added by
    dropping a function into the namespace — no manual registry calls.

Key insight: ToolRegistry is just a dict. You can build, swap, or extend it
at any point before or during the agent loop.

Docs: examples/04_tool_use_patterns/04_dynamic_tools.md
Reference: OpenClaw research/openclaw/src/agents/pi-tools.ts, Nanobot research/nanobot/nanobot/agent/tools/registry.py
"""
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from core.agent import Agent
from core.memory import Memory
from core.model import ModelProvider
from core.registry import ToolRegistry

load_dotenv()

console = Console()


# --- Tool library (not registered at startup) --------------------------------

def search_web(query: str) -> str:
    """
    Search the web for up-to-date information. Use for current events or facts.
    :param query: The search query string.
    """
    return f"[Simulated web result for '{query}']: Python 3.13 released Oct 2024 with free-threaded mode."


def run_python(code: str) -> str:
    """
    Execute a Python code snippet and return the output.
    :param code: Valid Python code to execute.
    """
    import io, contextlib
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(code, {})  # noqa: S102
        return buf.getvalue().strip() or "(no output)"
    except Exception as e:
        return f"Error: {e}"


def read_csv(path: str) -> str:
    """
    Read a CSV file and return the first five rows as a string.
    :param path: Absolute path to the CSV file.
    """
    import csv, os
    if not os.path.exists(path):
        return f"Error: file not found: {path}"
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    preview = rows[:5]
    return "\n".join(",".join(row) for row in preview)


def send_email(to: str, subject: str, body: str) -> str:
    """
    Send an email to a recipient. (Simulated — no email is actually sent.)
    :param to: Recipient email address.
    :param subject: Subject line of the email.
    :param body: Body text of the email.
    """
    return f"[Simulated] Email sent to {to!r} — subject: {subject!r}"


# --- Pattern A: Capability-scoped loading ------------------------------------

CAPABILITY_MAP = {
    "research": [search_web],
    "code": [run_python],
    "data": [read_csv],
    "communication": [send_email],
}


def build_registry_for(capabilities: list[str]) -> ToolRegistry:
    """Return a ToolRegistry containing only the tools for the given capabilities."""
    registry = ToolRegistry()
    for cap in capabilities:
        for fn in CAPABILITY_MAP.get(cap, []):
            registry.register(fn)
    return registry


DEFAULT_SCOPED_PROMPT = (
    "Find out the latest Python version and then write a one-liner that "
    "prints the numbers 1 to 10 using list comprehension."
)


def build_scoped_agent(capabilities: list[str], model: str | None = None, max_steps: int = 6) -> Agent:
    return Agent(
        model=ModelProvider(model),
        memory=Memory(),
        registry=build_registry_for(capabilities),
        system_prompt="You are a research and coding assistant.",
        max_steps=max_steps,
        name="ResearchAgent",
    )


def scoped_loading_demo():
    console.print(Rule("[bold blue]Pattern A — Capability-Scoped Loading[/bold blue]"))

    # Task 1: research + code only
    agent = build_scoped_agent(["research", "code"])
    names = [s["function"]["name"] for s in agent.registry.get_schemas()]
    console.print(f"[dim]Registered tools: {names}[/dim]")

    result = agent.run(DEFAULT_SCOPED_PROMPT)
    console.print(Panel(result, title="Research + Code result", border_style="cyan"))


# --- Pattern B: Plugin discovery via marker attribute ------------------------

PLUGIN_MARKER = "_is_agent_tool"


def agent_tool(fn):
    """Marker decorator — tags a function for auto-discovery."""
    setattr(fn, PLUGIN_MARKER, True)
    return fn


# Plugin tools (discovered automatically, not manually registered)
@agent_tool
def celsius_to_fahrenheit(celsius: float) -> str:
    """
    Convert a temperature from Celsius to Fahrenheit.
    :param celsius: Temperature in Celsius.
    """
    return f"{celsius}°C = {celsius * 9/5 + 32:.1f}°F"


@agent_tool
def word_count(text: str) -> str:
    """
    Count the number of words in a text string.
    :param text: The text to count words in.
    """
    return f"{len(text.split())} words"


@agent_tool
def reverse_string(text: str) -> str:
    """
    Reverse a string.
    :param text: The string to reverse.
    """
    return text[::-1]


def discover_plugins(namespace: dict) -> ToolRegistry:
    """Scan a namespace dict and register all functions marked with @agent_tool."""
    registry = ToolRegistry()
    for obj in namespace.values():
        if callable(obj) and getattr(obj, PLUGIN_MARKER, False):
            registry.register(obj)
            console.print(f"  [dim]Discovered plugin: {obj.__name__}[/dim]")
    return registry


DEFAULT_PLUGIN_PROMPT = (
    "Convert 100°C to Fahrenheit, count the words in 'the quick brown fox', "
    "and reverse the string 'hello world'."
)


def build_plugin_agent(model: str | None = None, max_steps: int = 6) -> Agent:
    return Agent(
        model=ModelProvider(model),
        memory=Memory(),
        registry=discover_plugins(globals()),
        system_prompt="You are a utility assistant. Use available tools to answer.",
        max_steps=max_steps,
        name="PluginAgent",
    )


def plugin_discovery_demo():
    console.print(Rule("[bold blue]Pattern B — Plugin Discovery[/bold blue]"))
    console.print("[dim]Scanning namespace for @agent_tool functions...[/dim]")

    agent = build_plugin_agent()
    names = [s["function"]["name"] for s in agent.registry.get_schemas()]
    console.print(f"[dim]Auto-registered: {names}[/dim]\n")

    result = agent.run(DEFAULT_PLUGIN_PROMPT)
    console.print(Panel(result, title="Plugin Discovery result", border_style="green"))


if __name__ == "__main__":
    scoped_loading_demo()
    plugin_discovery_demo()
