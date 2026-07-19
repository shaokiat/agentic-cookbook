# Parallel Tool Call Execution: Walkthrough

> Placeholder — full execution trace to be written.

## What it does

When the model returns several tool calls in one response, `ParallelAgent` overrides `_act` to dispatch the whole batch through a `ThreadPoolExecutor` instead of executing sequentially. The demo runs the same prompt both ways and shows the wall-clock speedup.

## Key insight

The model already groups independent calls into one response — parallelising *within that batch* cuts latency without changing the loop protocol. All results are still assembled before the next model turn, so the transcript the model sees is identical.

## Run it

```bash
.venv/bin/python examples/04_tool_use_patterns/02_parallel_tool_calls.py
```

UI page: `ui/pages/p04_2_parallel_tools.py`

## References

- Code: [`02_parallel_tool_calls.py`](02_parallel_tool_calls.py)
- Concept: [PROJECT_CONTEXT.md](../../PROJECT_CONTEXT.md) — #13 Parallel Tool Calling
- OpenClaw: [`research/openclaw/src/agents/pi-embedded-subscribe.ts`](../../research/openclaw/src/agents/pi-embedded-subscribe.ts) — concurrent dispatch of a response's tool calls
- Nanobot: [`research/nanobot/nanobot/agent/runner.py`](../../research/nanobot/nanobot/agent/runner.py) — `concurrent_tools=True` in `AgentRunner`
