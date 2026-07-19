# Tool Error Recovery: Walkthrough

> Placeholder — full execution trace to be written.

## What it does

Two resilience layers around flaky tools: a `with_retry` decorator retries the raw function with exponential backoff (transient failures stay invisible to the agent), and if retries are exhausted, the error *string* becomes an ordinary observation the agent reasons around — falling back to cached data or a degraded answer.

## Key insight

Returning a descriptive error string always beats raising out of a tool: the agent can act on a string; an uncaught exception just crashes the turn.

## Run it

```bash
.venv/bin/python examples/04_tool_use_patterns/03_error_recovery.py
```

UI page: `ui/pages/p04_3_error_recovery.py`

## References

- Code: [`03_error_recovery.py`](03_error_recovery.py)
- Concept: [PROJECT_CONTEXT.md](../../PROJECT_CONTEXT.md) — #14 Tool Error Recovery
- Nanobot: [`research/nanobot/nanobot/agent/runner.py`](../../research/nanobot/nanobot/agent/runner.py) — provider retry with exponential backoff, `_restore_runtime_checkpoint()` crash recovery
- OpenClaw: [`research/openclaw/src/agents/compaction.ts`](../../research/openclaw/src/agents/compaction.ts) — compaction retry on context overflow
