"""
Log Analyzer

Parses the markdown trace files produced by AgentLogger and reports:
  - Total steps per run
  - Tools called (frequency table)
  - Error rate (tool calls returning "Error:")
  - Estimated trajectory efficiency (steps taken vs. minimum possible)

Run this after executing any example that writes to examples/logs/.

Usage:
  python examples/05_evaluation_and_monitoring/01_log_analyzer.py
  python examples/05_evaluation_and_monitoring/01_log_analyzer.py --log-dir examples/logs

Docs: examples/05_evaluation_and_monitoring/01_log_analyzer.md
Reference: OpenClaw research/openclaw/src/agents/anthropic-payload-log.ts
"""
import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.rule import Rule

console = Console()


# --- Data model --------------------------------------------------------------

@dataclass
class ToolCall:
    name: str
    arguments: str
    observation: str
    is_error: bool


@dataclass
class RunTrace:
    agent_name: str
    user_input: str
    final_answer: str
    steps: int
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for tc in self.tool_calls if tc.is_error)

    @property
    def tool_names(self) -> list[str]:
        return [tc.name for tc in self.tool_calls]


# --- Parser ------------------------------------------------------------------

def parse_log_file(path: Path) -> list[RunTrace]:
    """Parse a markdown log file into a list of RunTrace objects."""
    content = path.read_text()

    runs: list[RunTrace] = []
    current_run: dict | None = None
    current_tool: dict | None = None

    for line in content.splitlines():
        # Run start
        m = re.match(r"^## RUN_START \[(.+?)\]", line)
        if m:
            if current_run is not None:
                runs.append(_finalize_run(current_run))
            current_run = {
                "agent_name": m.group(1),
                "user_input": "",
                "final_answer": "",
                "steps": 0,
                "tool_calls": [],
            }
            current_tool = None
            continue

        if current_run is None:
            continue

        # User input
        m = re.match(r"^\*\*User Input:\*\* (.+)$", line)
        if m:
            current_run["user_input"] = m.group(1)
            continue

        # Step counter
        m = re.match(r"^## (?:THINK|ACT) \[.+?\] - Step (\d+)", line)
        if m:
            current_run["steps"] = max(current_run["steps"], int(m.group(1)))
            continue

        # Tool execution start
        m = re.match(r"^### Tool Execution: `(.+?)`", line)
        if m:
            current_tool = {"name": m.group(1), "arguments": "", "observation": ""}
            continue

        # Tool arguments
        if current_tool is not None:
            m = re.match(r"^\*\*Arguments:\*\* `(.+)`", line)
            if m:
                current_tool["arguments"] = m.group(1)
                continue

            # Observation content (lines inside ``` block)
            if line.strip() not in ("```", "---", ""):
                if current_tool.get("_in_obs"):
                    current_tool["observation"] += line + "\n"
            if line.strip() == "```":
                if current_tool.get("_in_obs"):
                    # Closing fence — finalize tool
                    current_tool["observation"] = current_tool["observation"].strip()
                    current_run["tool_calls"].append(
                        ToolCall(
                            name=current_tool["name"],
                            arguments=current_tool["arguments"],
                            observation=current_tool["observation"],
                            is_error=current_tool["observation"].lower().startswith("error"),
                        )
                    )
                    current_tool = None
                else:
                    current_tool["_in_obs"] = True
                continue

        # Final answer
        if "### Final Answer" in line:
            # Next non-empty line will be the answer
            current_run["_reading_answer"] = True
            continue
        if current_run.get("_reading_answer") and line.strip() and not line.startswith("---"):
            current_run["final_answer"] = line.strip()
            current_run["_reading_answer"] = False
            continue

    if current_run is not None:
        runs.append(_finalize_run(current_run))

    return runs


def _finalize_run(d: dict) -> RunTrace:
    return RunTrace(
        agent_name=d["agent_name"],
        user_input=d["user_input"],
        final_answer=d["final_answer"],
        steps=d["steps"],
        tool_calls=d["tool_calls"],
    )


# --- Aggregation (pure data, no rendering) -------------------------------------

def collect_stats(log_dir: Path) -> dict:
    """Parse all logs in a directory into plain data for any renderer."""
    log_files = sorted(log_dir.glob("*.md"))
    all_runs: list[tuple[Path, RunTrace]] = []
    for log_file in log_files:
        for run in parse_log_file(log_file):
            all_runs.append((log_file, run))

    tool_freq: dict[str, int] = {}
    tool_errors: dict[str, int] = {}
    for _, run in all_runs:
        for tc in run.tool_calls:
            tool_freq[tc.name] = tool_freq.get(tc.name, 0) + 1
            if tc.is_error:
                tool_errors[tc.name] = tool_errors.get(tc.name, 0) + 1

    total_steps = sum(r.steps for _, r in all_runs)
    total_tools = sum(len(r.tool_calls) for _, r in all_runs)
    total_errors = sum(r.error_count for _, r in all_runs)

    return {
        "log_files": log_files,
        "runs": all_runs,
        "tool_freq": tool_freq,
        "tool_errors": tool_errors,
        "total_steps": total_steps,
        "total_tools": total_tools,
        "total_errors": total_errors,
        "error_rate": total_errors / total_tools * 100 if total_tools else 0,
    }


# --- Report ------------------------------------------------------------------

def analyze(log_dir: Path):
    stats = collect_stats(log_dir)
    log_files, all_runs = stats["log_files"], stats["runs"]
    if not log_files:
        console.print(f"[red]No .md log files found in {log_dir}[/red]")
        return

    console.print(Rule("[bold blue]Agent Log Analysis[/bold blue]"))
    console.print(f"[dim]Analyzed {len(log_files)} log file(s), {len(all_runs)} run(s)[/dim]\n")

    # Per-run table
    run_table = Table(title="Run Summary", show_lines=True)
    run_table.add_column("File", style="dim")
    run_table.add_column("Agent")
    run_table.add_column("Steps", justify="right")
    run_table.add_column("Tool Calls", justify="right")
    run_table.add_column("Errors", justify="right")
    run_table.add_column("User Input", max_width=40)

    for log_file, run in all_runs:
        err_color = "red" if run.error_count > 0 else "green"
        run_table.add_row(
            log_file.name,
            run.agent_name,
            str(run.steps),
            str(len(run.tool_calls)),
            f"[{err_color}]{run.error_count}[/{err_color}]",
            run.user_input[:40] + ("..." if len(run.user_input) > 40 else ""),
        )
    console.print(run_table)

    # Tool frequency table
    tool_freq, tool_errors = stats["tool_freq"], stats["tool_errors"]

    if tool_freq:
        freq_table = Table(title="Tool Frequency")
        freq_table.add_column("Tool", style="bold")
        freq_table.add_column("Calls", justify="right")
        freq_table.add_column("Errors", justify="right")
        freq_table.add_column("Error Rate", justify="right")
        for name, count in sorted(tool_freq.items(), key=lambda x: -x[1]):
            errors = tool_errors.get(name, 0)
            rate = f"{errors / count * 100:.0f}%"
            color = "red" if errors > 0 else "green"
            freq_table.add_row(name, str(count), f"[{color}]{errors}[/{color}]", rate)
        console.print(freq_table)

    # Aggregate stats
    console.print(
        Panel(
            f"Runs: {len(all_runs)}  |  Total steps: {stats['total_steps']}  |  "
            f"Total tool calls: {stats['total_tools']}  |  Error rate: {stats['error_rate']:.1f}%",
            title="[bold]Aggregate Stats[/bold]",
            border_style="blue",
        )
    )


def main():
    parser = argparse.ArgumentParser(description="Analyze agent log files.")
    parser.add_argument(
        "--log-dir",
        default="examples/logs",
        help="Directory containing .md log files (default: examples/logs)",
    )
    args = parser.parse_args()
    analyze(Path(args.log_dir))


if __name__ == "__main__":
    main()
