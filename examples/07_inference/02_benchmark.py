"""
Single-Stream Benchmark

Measures the two latency numbers that matter, separately, because they come from
different phases of generation:

  TTFT — time to first token. Dominated by *prefill*, which is compute-bound and
         scales with prompt length.
  ITL  — inter-token latency during decode. Memory-bandwidth-bound, scales with
         model size, and is nearly independent of prompt length.

The suite deliberately includes one long-prefill prompt. Watching TTFT jump while ITL
stays flat is the clearest demonstration that these are two different workloads.

Key insight: a single-stream benchmark cannot tell you which server is better. It tells
you what one user feels. Capacity lives in 03_load_sweep.py.

Docs: examples/07_inference/02_benchmark.md
Reference: docs/inference_serving.md
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.rule import Rule
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import (
    LONG_PREFILL_PROMPT, PROMPT_SUITE, Backend, discover, env_context,
    save_replacing, summarize, timed_completion,
)

load_dotenv()
console = Console()

MAX_TOKENS = 128


def benchmark_backend(b: Backend, repeats: int = 3, max_tokens: int = MAX_TOKENS):
    """Run the short-prompt suite `repeats` times, then the long-prefill prompt once."""
    short_results = []
    for _ in range(repeats):
        for prompt in PROMPT_SUITE:
            short_results.append(timed_completion(b, prompt, max_tokens))
    long_result = timed_completion(b, LONG_PREFILL_PROMPT, max_tokens)
    return short_results, long_result


def benchmark_demo(repeats: int = 3, save_to: str | None = None) -> None:
    backends = [b for b in discover() if b.available]
    if not backends:
        console.print("[yellow]No live engine on the local endpoint. Start one: make serve-vllm[/yellow]")
        return

    hardware, dtype, max_len = env_context()
    console.print(f"[dim]hardware={hardware} max_model_len={max_len}[/dim]")

    records = []
    table = Table(title="Single stream (concurrency 1)", show_header=True, header_style="bold")
    for col in ("Backend", "TTFT p50", "TTFT p95", "ITL p50", "decode tok/s", "long-prefill TTFT", "errors"):
        table.add_column(col)

    for b in backends:
        console.print(Rule(f"[bold]{b.name}[/bold]"))
        with console.status(f"Benchmarking {b.name}…"):
            short_results, long_result = benchmark_backend(b, repeats)

        # Wall time is meaningless at concurrency 1 (requests are sequential), so
        # aggregate_output_tps is derived from the summed request time instead.
        wall = sum(r.e2e_ms for r in short_results if r.ok) / 1000
        rec = summarize(b, short_results, wall, 1, hardware, dtype, max_len, kind="single")
        rec.note = f"long-prefill TTFT {long_result.ttft_ms:.0f}ms, ITL {long_result.itl_ms:.1f}ms"
        records.append(rec)

        table.add_row(
            b.name,
            f"{rec.ttft_ms['p50']:.0f}ms",
            f"{rec.ttft_ms['p95']:.0f}ms",
            f"{rec.itl_ms['p50']:.1f}ms",
            f"{rec.output_tps_per_req:.1f}",
            f"{long_result.ttft_ms:.0f}ms" if long_result.ok else "err",
            str(rec.errors),
        )

    console.print(table)
    console.print("[dim]TTFT rises with the long prompt while ITL barely moves — prefill and "
                  "decode are different workloads.[/dim]")

    save_to = save_to or os.getenv("BENCH_SAVE_AS", "single_stream.json")
    if save_to:
        path = save_replacing(records, save_to)
        console.print(f"[green]Saved[/green] {path.relative_to(Path.cwd())}"
                      if path.is_relative_to(Path.cwd()) else f"[green]Saved[/green] {path}")


if __name__ == "__main__":
    benchmark_demo()
