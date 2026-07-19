# Dynamic Tool Loading: Walkthrough

> Placeholder — full execution trace to be written.

## What it does

Two runtime registry patterns: **capability-scoped loading** (build a registry containing only the tools the current task needs, shrinking the schema list the model sees) and **plugin discovery** (scan a namespace for functions carrying a `@agent_tool` marker attribute and register them automatically).

## Key insight

`ToolRegistry` is just a dict. You can build, swap, or extend it at any point — tool availability is a runtime decision, not a startup one. Fewer irrelevant schemas also means fewer prompt tokens and fewer confused tool choices.

## Run it

```bash
.venv/bin/python examples/04_tool_use_patterns/04_dynamic_tools.py
```

UI page: `ui/pages/p04_4_dynamic_tools.py`

## References

- Code: [`04_dynamic_tools.py`](04_dynamic_tools.py)
- Registry internals: [`core/registry.py`](../../core/registry.py) — schema generation from type hints
- OpenClaw: [`research/openclaw/src/agents/pi-tools.ts`](../../research/openclaw/src/agents/pi-tools.ts) — tool schemas + policy pipeline
- Nanobot: [`research/nanobot/nanobot/agent/tools/registry.py`](../../research/nanobot/nanobot/agent/tools/registry.py) — the registry this one is modeled on
