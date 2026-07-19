# Agent Tracer: Walkthrough

> Placeholder — full execution trace to be written.

## What it does

A context manager that monkeypatches `agent.run`, `model.generate`, and `registry.call_tool` to capture a per-step trace tree — thoughts, tool calls with arguments and latency, token counts, and estimated cost — without modifying `core/` at all.

## Key insight

Interception beats instrumentation when you don't own the code (or don't want to pollute it). The tracer patches the seams the agent already exposes; because it patches `run`, callers must drive `agent.run()` (not `run_events()` directly) for the trace to capture.

## Run it

```bash
.venv/bin/python examples/05_evaluation_and_monitoring/02_agent_tracer.py
```

UI page: `ui/pages/p05_2_agent_tracer.py`

## References

- Code: [`02_agent_tracer.py`](02_agent_tracer.py)
- Concept: [PROJECT_CONTEXT.md](../../PROJECT_CONTEXT.md) — #22 Tracing and Structured Logging
- OpenClaw: [`research/openclaw/src/agents/cache-trace.ts`](../../research/openclaw/src/agents/cache-trace.ts) — cache-level tracing
- Nanobot: [`research/nanobot/nanobot/agent/hook.py`](../../research/nanobot/nanobot/agent/hook.py) — `AgentHook`, the "official seam" version of what this tracer does by patching
