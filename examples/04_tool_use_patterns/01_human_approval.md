# Human-in-the-Loop Tool Approval: Walkthrough

> Placeholder — full execution trace to be written.

## What it does

Tools marked `@dangerous` don't execute immediately: `ApprovalAgent._act` yields an `approval_request` event and the loop pauses until the surrounding UI answers via `generator.send(bool)`. Terminal runs answer with a y/n prompt; the Streamlit page holds the paused generator in session state and resumes it from Allow/Deny buttons.

## Key insight

Approval is **loop policy, not tool internals**. The tools stay pure; the gate lives in the tool-execution step, so any frontend decides how to ask. Denial still arrives as an ordinary observation — the model's view of the world is unchanged.

## Run it

```bash
.venv/bin/python examples/04_tool_use_patterns/01_human_approval.py
```

UI page: `ui/pages/p04_1_human_approval.py`

## References

- Code: [`01_human_approval.py`](01_human_approval.py)
- Concept: [PROJECT_CONTEXT.md](../../PROJECT_CONTEXT.md) — #12 Tool Policy Pipeline
- OpenClaw: [`research/openclaw/src/agents/tool-policy-pipeline.ts`](../../research/openclaw/src/agents/tool-policy-pipeline.ts) — multi-stage allow/deny/prompt pipeline; [`bash-tools.exec-approval-request.ts`](../../research/openclaw/src/agents/bash-tools.exec-approval-request.ts) — the interactive-approval stage
- Chapter overview: [README.md](README.md)
