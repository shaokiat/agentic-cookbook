# Log Analyzer: Walkthrough

> Placeholder — full execution trace to be written.

## What it does

Parses the markdown trace files `AgentLogger` writes to `examples/logs/` and reports per-run steps, tool-call frequency, error rates, and aggregate stats. `collect_stats()` returns plain dicts so any renderer (rich tables in the CLI, dataframes in Streamlit) can present them.

## Key insight

Agents are non-deterministic; post-hoc log analysis is the cheapest observability you can add. Structured logs you can grep and aggregate beat print statements you can only read once.

## Run it

```bash
.venv/bin/python examples/05_evaluation_and_monitoring/01_log_analyzer.py --log-dir examples/logs
```

UI page: `ui/pages/p05_1_log_analyzer.py`

## References

- Code: [`01_log_analyzer.py`](01_log_analyzer.py)
- Log producer: [`core/logger.py`](../../core/logger.py) — `AgentLogger`
- Concept: [PROJECT_CONTEXT.md](../../PROJECT_CONTEXT.md) — #22 Tracing and Structured Logging
- OpenClaw: [`research/openclaw/src/agents/anthropic-payload-log.ts`](../../research/openclaw/src/agents/anthropic-payload-log.ts) — payload-level structured logging
