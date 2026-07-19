# Sequential Pipeline (Baton-Pass Pattern): Walkthrough

> Placeholder — full execution trace to be written. Structure follows [01_orchestrator_worker.md](01_orchestrator_worker.md).

## What it does

Chains three specialist agents — Researcher → Writer → Editor — where each stage's output becomes the next stage's input. Specialization via narrow system prompts beats one generalist agent asked to do all three jobs.

## Key insight

The "pipeline" is nothing more than function composition over `agent.run()` return values. No framework, no message schema — a string passed forward. `pipeline_steps()` exposes the stages as a generator so any frontend (CLI, Streamlit) can render intermediate results as they complete.

## Run it

```bash
.venv/bin/python examples/03_multi_agent_systems/03_sequential_pipeline.py
```

UI page: `ui/pages/p03_3_sequential_pipeline.py`

## References

- Code: [`03_sequential_pipeline.py`](03_sequential_pipeline.py)
- Concept: [PROJECT_CONTEXT.md](../../PROJECT_CONTEXT.md) — Level 5, Multi-Agent Systems
- Nanobot: [`research/nanobot/nanobot/agent/loop.py`](../../research/nanobot/nanobot/agent/loop.py) — message-bus chaining between agent turns
- Related: [03_reflexion.py](../01_agent_patterns/03_reflexion.py) — same chaining shape, but for self-critique rather than specialization
