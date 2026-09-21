import streamlit as st

from common import about_from, load_example, page_tabs, selected_model, tool_list_expander

st.title("Agent Tracer")
st.caption(
    "Monkeypatches agent.run / model.generate / registry.call_tool to build a step-by-step "
    "trace tree with latency, tokens, and cost — no changes to core."
)

CORE_CONCEPT = """\
**What it is**

A context manager that monkeypatches `agent.run`, `model.generate`, and `registry.call_tool` to
capture a per-step trace tree — thoughts, tool calls with their arguments and latency, token
counts, and estimated cost — without touching `core/` at all.

```mermaid
flowchart TD
    E["with AgentTracer(): ..."] --> P["Patches agent.run, model.generate, registry.call_tool"]
    P --> Run[Agent runs normally, unaware it's being observed]
    Run --> T["Each call recorded: latency, tokens, cost, arguments"]
    T --> Tree[Assembled into a per-step trace tree]
```

**Key insight**

Interception beats instrumentation when you don't own the code, or don't want to pollute it
with logging calls. The tracer patches the seams the agent already exposes at its call
boundaries, rather than editing agent internals to add hooks. The trade-off: because it patches
`run` specifically, callers must drive the agent through `agent.run()` — not `run_events()`
directly — for the trace to actually capture anything.
"""


relpath = "examples/05_evaluation_and_monitoring/02_agent_tracer.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod, about_extra=about_from(CORE_CONCEPT))

with tab_demo:
    tool_list_expander(mod.build_agent(model=selected_model()))
    prompt = st.text_area("Prompt", value=mod.DEFAULT_PROMPT, height=100)

    if st.button("Run traced", type="primary"):
        with st.spinner("Running under tracer…"):
            result, tracer = mod.run_traced(prompt, selected_model())

        st.markdown(f"**Final answer:** {result}")

        trace = tracer.trace
        if trace:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Steps", len(trace.steps))
            c2.metric("Tool calls", sum(len(s.tool_events) for s in trace.steps))
            c3.metric("Latency", f"{trace.total_latency_ms:.0f}ms")
            c4.metric("Est. cost", f"${trace.estimated_cost_usd:.4f}")

            for step in trace.steps:
                label = f"Step {step.index} ({step.latency_ms:.0f}ms)"
                if step.thought:
                    label += f" — {step.thought[:60]}"
                with st.expander(label, expanded=True):
                    if step.thought:
                        st.markdown(step.thought)
                    for te in step.tool_events:
                        icon = "🔴" if te.is_error else "🟢"
                        st.markdown(f"{icon} `{te.name}({te.arguments})` → {te.result} *({te.latency_ms:.0f}ms)*")

            with st.expander("Raw trace JSON"):
                st.json(tracer.to_dict())
