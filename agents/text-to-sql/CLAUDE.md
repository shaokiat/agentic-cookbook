# text-to-sql — Claude Instructions

Self-contained agent under `agents/`. Own venv, own dependencies — don't reach into the
cookbook root's `.venv` or `core/` for this one.

## Running

```
uv sync
uv run text-to-sql
python -m tests.test_agent            # self-checks; add --live to hit the real API
python -m text_to_sql.eval --variants baseline,full   # prompt ablation
```

## Code style

- No comments unless the WHY is non-obvious.
- No abstractions beyond what the current task requires.
- `guard()` in `text_to_sql/agent.py` is the one place that decides what SQL is allowed to
  execute — extend it there, not per-caller.
