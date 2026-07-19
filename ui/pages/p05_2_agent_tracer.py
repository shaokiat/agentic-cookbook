import streamlit as st

from common import load_example, page_tabs, selected_model

st.title("Agent Tracer")
st.caption(
    "Monkeypatches agent.run / model.generate / registry.call_tool to build a step-by-step "
    "trace tree with latency, tokens, and cost — no changes to core."
)

relpath = "examples/05_evaluation_and_monitoring/02_agent_tracer.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod)

with tab_demo:
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
