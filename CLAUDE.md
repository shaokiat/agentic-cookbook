# agentic-cookbook — Claude Instructions

## Project context

Read `PROJECT_CONTEXT.md` before working on this repo. It is the authoritative source for:
- The motivation and design philosophy of the project
- The concept ladder (Levels 1–7) that defines learning order
- The mapping between cookbook examples and production systems (OpenClaw, Nanobot)
- The roadmap of what is built and what is not yet built

## Running Python scripts

Always use the project virtualenv. Never invoke `python` or `python3` directly.

```
.venv/bin/python <script>
```

The virtualenv is at `.venv/` in the repo root. All dependencies are installed there.

## Code style

- No comments unless the WHY is non-obvious.
- No docstrings beyond a single short line.
- No abstractions beyond what the current task requires.
- Prefer editing existing files over creating new ones.

## Documentation

- Walkthrough `.md` files live next to their `.py` file (e.g. `01_orchestrator_worker.md` beside `01_orchestrator_worker.py`).
- Use only relative paths in docs — never absolute local paths.
- Do not create planning or analysis documents; work from conversation context.
