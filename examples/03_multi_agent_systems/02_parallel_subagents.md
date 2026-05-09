# Parallel Subagents (Fan-Out Pattern): Walkthrough

This document walks through `examples/03_multi_agent_systems/02_parallel_subagents.py` — its mechanics, what happened during a real execution, and the design decisions behind it.

---

## What it does

Three independent worker agents are spawned concurrently, each answering a different domain question. The same tasks run sequentially first so the wall-clock difference is measurable. After both modes complete, a fourth aggregator agent synthesises the parallel results into a unified summary.

The three tasks:

- **Python Expert** — *"What are Python's biggest strengths for data science in 2025?"*
- **Go Expert** — *"What are Go's biggest strengths for backend services in 2025?"*
- **Rust Expert** — *"What are Rust's biggest strengths for systems programming in 2025?"*

---

## Execution trace

### Sequential run

Workers executed one after another: Python → Go → Rust. Each blocked the next.

**Total time: 8.3 s**

### Parallel run

All three workers were submitted to a `ThreadPoolExecutor` at the same moment. The slowest worker determined wall-clock time — the other two finished before it and waited for `as_completed` to drain.

**Total time: 1.7 s — a 5.0× speedup**

```
Execution Time Comparison
┏━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┓
┃ Mode       ┃ Time (s) ┃ Speedup ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━┩
│ Sequential │     8.3s │    1.0× │
│ Parallel   │     1.7s │    5.0× │
└────────────┴──────────┴─────────┘
```

The speedup approaches the number of workers (3) because the bottleneck is network latency to the model API, not CPU. Each worker spends most of its time waiting for a response — time that overlaps completely when run in parallel.

### Worker outputs (parallel run)

**Go Expert** — goroutines and channels for concurrency; performance close to lower-level languages; growing ecosystem; static typing and GC for reliability.

**Python Expert** — NumPy/Pandas/scikit-learn ecosystem; TensorFlow/PyTorch for deep learning; readable syntax; interoperability with diverse tech stacks.

**Rust Expert** — memory safety without a GC; borrow checker prevents data races at compile time; Cargo for package management; active governance and community.

### Aggregation step

A fourth `Agent` received all three reports concatenated and produced a unified summary comparing Go, Python, and Rust across their respective domains. The aggregator did not call any tools — it only synthesised text. Its output highlighted each language's differentiated niche: Go for backend scalability, Python for data-centric tasks, Rust for secure concurrent systems programming.

---

## How the code works

### `run_worker`

```python
def run_worker(role: str, task: str) -> tuple[str, str]:
    worker = Agent(
        model=model,
        memory=Memory(),
        registry=ToolRegistry(),
        system_prompt=f"You are a {role}. Answer the question concisely in 3-5 sentences.",
        name=role,
        verbose=False,
    )
    return role, worker.run(task)
```

Each call creates a fully independent agent with empty memory and no tools. Workers are pure question-answerers — they receive one task and return one string. Returning `(role, result)` as a tuple keeps the result labelled for aggregation.

### `run_parallel` with `ThreadPoolExecutor`

```python
def run_parallel(tasks):
    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {executor.submit(run_worker, role, task): role for role, task in tasks}
        for future in as_completed(futures):
            role, result = future.result()
            results[role] = result
```

`executor.submit` is non-blocking — all tasks are submitted before any has a chance to complete. `as_completed` yields futures in arrival order (whichever finishes first), not submission order. The dict `futures` maps each future back to its role for logging; the actual role is also carried in the `(role, result)` return value.

`max_workers=len(tasks)` allocates exactly one thread per task. There is no queuing — all workers start simultaneously. For larger fan-outs, cap `max_workers` to avoid overwhelming the API with simultaneous connections.

### Why `ThreadPoolExecutor` rather than `asyncio`

The short answer: `Agent.run()` is synchronous and blocking, and `asyncio` cannot make blocking code concurrent without wrapping it in threads anyway.

#### What asyncio actually does

`asyncio` achieves concurrency through cooperative multitasking on a single thread. A coroutine yields control back to the event loop at every `await` point, allowing other coroutines to run in the gap. This works extremely well when every layer of the call stack is async-aware:

```python
# This works — httpx is async-native, so every network wait is an await point
async def fetch(url):
    async with httpx.AsyncClient() as client:
        return await client.get(url)

async def main():
    results = await asyncio.gather(fetch(url1), fetch(url2), fetch(url3))
```

While `fetch(url1)` is blocked on the network, the event loop runs `fetch(url2)` and `fetch(url3)`. No threads, no GIL contention, low overhead.

#### Why asyncio breaks with blocking calls

If any function in the call chain blocks without yielding — a synchronous `requests.get()`, a blocking `time.sleep()`, the Anthropic SDK's sync client — it stalls the entire event loop. No other coroutine can progress until the blocking call returns:

```python
# BROKEN — requests.get() blocks the event loop; only one runs at a time
async def bad_fetch(url):
    return requests.get(url).text   # blocks the whole event loop

async def main():
    # Despite gather, these run sequentially — the event loop is frozen
    # while each requests.get() waits for the network
    results = await asyncio.gather(bad_fetch(url1), bad_fetch(url2))
```

`Agent.run()` calls the Anthropic SDK's synchronous client internally. Wrapping it in `async def` does not make it non-blocking — it just hides the problem:

```python
# BROKEN — looks async, but Agent.run() still blocks the event loop
async def run_worker_async(role, task):
    worker = Agent(...)
    return role, worker.run(task)   # synchronous blocking call inside a coroutine

async def main():
    # This runs sequentially, not in parallel
    await asyncio.gather(
        run_worker_async("Python Expert", task1),
        run_worker_async("Go Expert", task2),
    )
```

#### Why `ThreadPoolExecutor` directly is cleaner here

When the codebase is synchronous throughout, using `ThreadPoolExecutor` directly is both correct and simpler:

```python
# Clean — no event loop required, no run_in_executor indirection
with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
    futures = {executor.submit(run_worker, role, task): role for role, task in tasks}
    for future in as_completed(futures):
        role, result = future.result()
        results[role] = result
```

There is no hidden blocking, no event loop to manage, and no layering of async over sync. Each thread blocks independently on its own network call — the OS schedules them in parallel. The GIL is released during I/O, so threads genuinely overlap on network-bound work.

#### When you would reach for asyncio instead

If `Agent` were rewritten with an async-native interface — using `httpx.AsyncClient` or the async Anthropic SDK — `asyncio.gather` would be the idiomatic choice and would outperform threads for very large fan-outs (hundreds of workers), since coroutines have lower per-task overhead than OS threads. Nanobot's `AgentRunner` is async for exactly this reason: its design assumes many concurrent sessions sharing one event loop.

The rule: **match the concurrency primitive to the call stack**. Async code → `asyncio.gather`. Sync blocking code → `ThreadPoolExecutor`.

#### Why this project is sync and Nanobot is async — the call chain

The difference starts at the model provider, not the agent loop. Trace the path from `run_worker` down to the network socket in each system:

**This project** — every layer is a regular `def`, no `await` anywhere:

```
run_worker()
  └── Agent.run()                    # def  — core/agent.py
        └── ModelProvider.generate() # def  — core/model.py
              └── litellm.completion()       # sync, blocks the OS thread
                    └── httpx sync transport
                          └── socket.recv() # thread is parked here
```

**Nanobot** — every layer is `async def`, with an `await` at each I/O boundary:

```
AgentRunner.run()                    # async def — runner.py:231
  └── _request_model()              # async def — runner.py:586
        └── await provider.chat_with_retry()  # yields to event loop here
              └── await httpx.AsyncClient.post()
                    └── await asyncio.wait_for(coro, timeout_s)
```

Because Nanobot yields at every `await`, a single OS thread can interleave many concurrent sessions. While session A waits for the API, the event loop runs session B, then C. No extra threads are needed.

This async design also enables Nanobot's `concurrent_tools=True` flag, which fans out parallel tool calls using `asyncio.gather` directly — no threads involved:

```python
# runner.py:705 — parallel tool execution inside one event loop thread
batch_results = await asyncio.gather(*(
    self._run_tool(spec, tool_call, external_lookup_counts)
    for tool_call in batch
))
```

The root cause is the provider layer:

| | This project | Nanobot |
|:--|:--|:--|
| Model call | `litellm.completion()` — sync | `provider.chat_with_retry()` — `async def` |
| HTTP client | `httpx` sync transport | `httpx.AsyncClient` |
| Yield point | none — blocks the thread | `await` — releases the event loop |
| Concurrency primitive | `ThreadPoolExecutor` | `asyncio.gather` |

LiteLLM does expose `litellm.acompletion()` — an async variant. Switching `ModelProvider.generate` to `async def` and calling `await litellm.acompletion()` would make the entire call chain async, at which point `asyncio.gather` would replace `ThreadPoolExecutor` here with no other logic changes required.

### Aggregator design

The aggregator is a plain `Agent` with a synthesis-focused system prompt and no tools. It receives the combined worker outputs as a single user message. There is no streaming or partial aggregation — all parallel work must complete before synthesis begins.

This is a deliberate simplification: aggregation requires the full picture. If partial results were acceptable, you could stream aggregation as futures complete using `as_completed`.

---

## What the execution reveals about the pattern

### Speedup is bounded by the slowest worker

The parallel run takes as long as the slowest individual worker, not the sum. If one worker takes 5 s and two others take 1 s each, parallel time is ~5 s regardless. The sequential baseline in this example (8.3 s) was close to the sum of three roughly equal workers (~2.7 s each), which is why the 5× speedup almost equals the worker count.

For fan-outs with highly variable worker durations, parallel execution still wins — it just doesn't reach the theoretical maximum speedup.

### Workers are isolated by design

Each worker has `Memory()` — an empty context. The Go Expert's answer cannot be influenced by what the Python Expert said. For independent questions this is correct; each worker produces an uncontaminated assessment.

If tasks were dependent (worker B needs worker A's output), this pattern breaks down. Use `03_sequential_pipeline.py` for dependent chains.

### Aggregation is a separate concern from coordination

In `01_orchestrator_worker.py`, the orchestrator both coordinates workers and synthesises results — it is the same agent doing both jobs sequentially. Here, coordination (fan-out via `ThreadPoolExecutor`) is handled in Python code, and synthesis is delegated to a dedicated aggregator agent. Neither approach is strictly better; the right choice depends on whether the coordination logic itself needs LLM reasoning.

---

## Tradeoffs

| Property | This pattern | Alternative |
|:---------|:-------------|:------------|
| Worker execution | All parallel — wall time = max(worker times) | Sequential — see `01_orchestrator_worker.py` |
| Coordination logic | Plain Python (`ThreadPoolExecutor`) | LLM orchestrator decides fan-out dynamically |
| Worker awareness | Fully isolated — no shared context | Chain workers — see `03_sequential_pipeline.py` |
| Aggregation timing | After all workers complete | Stream as futures arrive (`as_completed` + partial synthesis) |
| API concurrency | One request per worker simultaneously | Rate-limit with `max_workers` cap |

---

## Extensions

**Cap concurrency for rate limits**: Replace `max_workers=len(tasks)` with a fixed ceiling (e.g. `min(len(tasks), 5)`) to avoid hitting per-minute token limits when fan-out is large.

**Stream partial results**: Move the aggregator inside the `as_completed` loop and update a running summary as each worker finishes. This reduces time-to-first-output at the cost of a more complex aggregation prompt.

**Add per-worker tools**: Pass a non-empty `ToolRegistry` to specific workers — a researcher worker might have web search, while an analyst worker has only reasoning. The fan-out infrastructure does not change.

**Dynamic task generation**: Let an LLM generate the `(role, task)` list from a high-level goal before the fan-out begins. The parallel execution stage is then data-driven rather than hard-coded.

**Structured outputs**: Have each worker return a typed object (e.g. a Pydantic model) instead of raw text. The aggregator receives structured data it can reliably parse, rather than prose it must interpret.

---

_Example_: `02_parallel_subagents.py`  
_Contrast with_: `01_orchestrator_worker.py` (sequential delegation), `03_sequential_pipeline.py` (dependent chain)
