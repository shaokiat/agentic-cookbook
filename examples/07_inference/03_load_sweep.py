"""
Concurrency Load Sweep

The point of the whole section. Fires 1, 2, 4, 8, 16, 32 simultaneous requests at each
backend and records what happens to aggregate throughput and per-request latency.

A server with continuous batching (vLLM) keeps climbing as concurrency rises: finished
sequences leave the batch at every decode iteration and queued ones join, so the GPU
stays saturated. A server without it flattens almost immediately.

Then the KV cache fills. The scheduler starts queueing, latency degrades sharply, and
throughput stops improving. That inflection is the knee, and it is the only number that
matters for capacity planning:

    aggregate tok/s
         │              ╭─────────   ← saturated: queueing
         │        ╭─────╯
         │   ╭────╯                  ← the knee
         │╭──╯
         └──────────────────────────  concurrency

Key insight: "tokens per second" quoted without a concurrency level is not a measurement.

Docs: examples/07_inference/03_load_sweep.md
Reference: docs/inference_serving.md
"""
import os
import sys
import threading
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from rich.console import Console
from rich.rule import Rule
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import (PROMPT_SUITE, Backend, discover, env_context, knee, run_concurrent,
                     save_replacing, summarize, timed_completion)

load_dotenv()
console = Console()

# Overridable: BENCH_LEVELS=1,2,4,8 for a quick pass on a busy laptop. The top level
# is the expensive one — 64 concurrent requests against a serializing engine can take
# tens of minutes and mostly measures your queue.
LEVELS = [int(x) for x in os.getenv("BENCH_LEVELS", "1,2,4,8,16,32").split(",")]
MAX_TOKENS = 128


def vllm_metrics(b: Backend) -> dict[str, float]:
    """Scrape vLLM's Prometheus endpoint for scheduler state.

    num_requests_running / num_requests_waiting / kv_cache_usage_perc are what turn the
    knee from a number into something you can watch happen.
    """
    base = (b.api_base or "").rstrip("/").removesuffix("/v1")
    wanted = ("vllm:num_requests_running", "vllm:num_requests_waiting",
              "vllm:gpu_cache_usage_perc", "vllm:kv_cache_usage_perc")
    try:
        body = httpx.get(f"{base}/metrics", timeout=3.0).text
    except Exception:
        return {}
    out = {}
    for line in body.splitlines():
        if line.startswith("#"):
            continue
        for key in wanted:
            if line.startswith(key):
                try:
                    out[key] = float(line.rsplit(" ", 1)[1])
                except (IndexError, ValueError):
                    pass
    return out


def _sample_peaks(b: Backend, stop: threading.Event, peaks: dict) -> None:
    """Poll /metrics while the batch is in flight.

    Scraping after the batch drains reads zeros — the scheduler state you care about
    only exists while requests are running.
    """
    while not stop.is_set():
        for key, value in vllm_metrics(b).items():
            peaks[key] = max(peaks.get(key, 0.0), value)
        time.sleep(0.25)


def sweep_backend(b: Backend, levels: list[int] = LEVELS, max_tokens: int = MAX_TOKENS,
                  on_level=None) -> list:
    hardware, dtype, max_len = env_context()

    # One throwaway call first. Without it the c=1 level absorbs cold-start cost
    # (lazy weight paging, first Metal kernel compile) and reports a TTFT several
    # times its steady-state value, which bends the bottom of the curve.
    timed_completion(b, PROMPT_SUITE[0], max_tokens=16)

    records = []
    for c in levels:
        peaks: dict[str, float] = {}
        stop = threading.Event()
        sampler = threading.Thread(target=_sample_peaks, args=(b, stop, peaks), daemon=True)
        sampler.start()
        try:
            results, wall = run_concurrent(b, PROMPT_SUITE, c, max_tokens)
        finally:
            stop.set()
            sampler.join(timeout=2)

        rec = summarize(b, results, wall, c, hardware, dtype, max_len)
        if peaks:
            rec.note = "peak " + " ".join(f"{k.split(':')[-1]}={v:g}" for k, v in sorted(peaks.items()))
        records.append(rec)
        if on_level:
            on_level(rec)
    return records


def load_sweep_demo(levels: list[int] = LEVELS, save_to: str | None = None) -> None:
    backends = [b for b in discover() if b.available]
    if not backends:
        console.print("[yellow]No live engine on the local endpoint. Start one: make serve-vllm[/yellow]")
        return

    hardware, dtype, max_len = env_context()
    console.print(f"[dim]hardware={hardware} max_model_len={max_len}[/dim]")

    all_records = []
    for b in backends:
        console.print(Rule(f"[bold]{b.name}[/bold]"))
        table = Table(show_header=True, header_style="bold")
        for col in ("Concurrency", "Aggregate tok/s", "Per-req tok/s", "TTFT p50", "e2e p95", "errors"):
            table.add_column(col)

        def add_row(rec):
            table.add_row(
                str(rec.concurrency),
                f"{rec.aggregate_output_tps:.1f}",
                f"{rec.output_tps_per_req:.1f}",
                f"{rec.ttft_ms['p50']:.0f}ms",
                f"{rec.e2e_ms['p95']:.0f}ms",
                str(rec.errors),
            )
            console.print(f"[dim]  c={rec.concurrency}: {rec.aggregate_output_tps:.1f} tok/s "
                          f"{rec.note}[/dim]")

        records = sweep_backend(b, levels, on_level=add_row)
        all_records.extend(records)
        console.print(table)

        k = knee(records)
        peak = max(records, key=lambda r: r.aggregate_output_tps)
        console.print(f"Knee at concurrency [bold]{k.concurrency}[/bold]: "
                      f"[bold]{k.aggregate_output_tps:.1f} tok/s[/bold] "
                      f"at e2e p95 {k.e2e_ms['p95']:.0f}ms")
        if peak.concurrency != k.concurrency:
            gain = (peak.aggregate_output_tps / k.aggregate_output_tps - 1) * 100
            cost = peak.e2e_ms["p95"] / max(k.e2e_ms["p95"], 1)
            console.print(f"[dim]Pushing to concurrency {peak.concurrency} buys {gain:.1f}% more "
                          f"throughput for {cost:.1f}x the p95 latency — past the knee, you are "
                          f"paying latency for nothing.[/dim]")

    save_to = save_to or os.getenv("BENCH_SAVE_AS", "load_sweep.json")
    if save_to:
        path = save_replacing(all_records, save_to)
        console.print(f"[green]Saved[/green] {path}")


if __name__ == "__main__":
    load_sweep_demo()
