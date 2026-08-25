"""
Inference Backends

Every self-hosted inference server in common use speaks the OpenAI chat-completions
wire format. That single fact is why this cookbook needs no new abstraction to run on
a model you host yourself: `core/model.py` already calls litellm, which speaks it too.

A "backend" here is therefore just (model string, base URL, key) — not a class hierarchy.

Because each engine wants the whole accelerator, they all serve on ONE local endpoint
(LOCAL_API_BASE) and only one runs at a time. This example probes it, works out which
engine answered and what model it has loaded, then streams one timed completion.

Key insight: at concurrency 1 every engine looks similar. That is expected, not a null
result — continuous batching is invisible until requests overlap. See 03_load_sweep.py.

Docs: examples/07_inference/01_backends.md
Reference: docs/inference_serving.md, deploy/vllm/README.md
"""
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import PROMPT_SUITE, discover, timed_completion

load_dotenv()
console = Console()

DEFAULT_PROMPT = PROMPT_SUITE[0]


def backends_demo(prompt: str = DEFAULT_PROMPT, max_tokens: int = 128) -> None:
    console.print(Rule("[bold]Local endpoint[/bold]"))
    backends = discover()

    if not backends:
        console.print(Panel(
            "No local endpoint configured.\n\n"
            "Set LOCAL_API_BASE in .env — see examples/07_inference/00_running_engines.md.",
            border_style="yellow",
        ))
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Backend")
    table.add_column("Model string")
    table.add_column("Base URL")
    table.add_column("Status")
    for b in backends:
        status = f"[green]up[/green] — {b.detail}" if b.available else f"[red]down[/red] — {b.detail}"
        table.add_row(b.name, b.model, b.api_base or "-", status)
    console.print(table)

    live = [b for b in backends if b.available]
    if not live:
        console.print("[yellow]Nothing live to call. Start an engine first: make serve-vllm (or serve-mlx / serve-ollama)[/yellow]")
        return

    console.print(Rule("[bold]One streaming completion each[/bold]"))
    console.print(f"[dim]{prompt}[/dim]\n")

    for b in live:
        with console.status(f"Calling {b.name}…"):
            r = timed_completion(b, prompt, max_tokens=max_tokens)
        if not r.ok:
            console.print(Panel(r.error, title=f"[bold]{b.name}[/bold]", border_style="red"))
            continue
        # Reasoning models can spend the whole token budget thinking; show that
        # rather than an empty panel.
        body = r.text.strip() or (f"[dim](reasoning only, no final answer within max_tokens)[/dim]\n"
                                  f"[dim]{r.reasoning.strip()[:300]}…[/dim]" if r.reasoning else "[dim](empty)[/dim]")
        console.print(Panel(
            f"{body}\n\n"
            f"[bold]TTFT[/bold] {r.ttft_ms:.0f}ms   "
            f"[bold]ITL[/bold] {r.itl_ms:.1f}ms   "
            f"[bold]decode[/bold] {r.output_tps:.1f} tok/s   "
            f"[bold]tokens[/bold] {r.output_tokens}",
            title=f"[bold]{b.name}[/bold] ({b.model})",
            border_style="cyan",
        ))


if __name__ == "__main__":
    backends_demo()
