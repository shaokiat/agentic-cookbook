# Async Announce Pattern: Walkthrough

> Placeholder — full execution trace to be written. Structure follows [01_orchestrator_worker.md](01_orchestrator_worker.md).

## What it does

Workers run in daemon threads and push `Announcement` objects onto a shared `queue.Queue` when they finish. The parent polls the queue between ticks without blocking, so results arrive in completion order — not spawn order — and a slow worker never blocks a fast one.

## Key insight

The announce pattern decouples spawner and worker *in time*: the parent's turn can end (and its context persist) before a sub-agent finishes. In production systems the queue is a message bus and the announcement re-enters the parent's session as an ordinary message.

## Run it

```bash
.venv/bin/python examples/03_multi_agent_systems/04_async_announce.py
```

UI page: `ui/pages/p03_4_async_announce.py`

## References

- Code: [`04_async_announce.py`](04_async_announce.py)
- Concept: [PROJECT_CONTEXT.md](../../PROJECT_CONTEXT.md) — #18 Async Agent Communication (Announce Pattern)
- OpenClaw: [`research/openclaw/src/agents/subagent-announce.ts`](../../research/openclaw/src/agents/subagent-announce.ts) — results delivered as messages to the parent session
- Nanobot: [`research/nanobot/nanobot/agent/subagent.py`](../../research/nanobot/nanobot/agent/subagent.py) — sub-agent publishes results via the bus as a system `InboundMessage`
