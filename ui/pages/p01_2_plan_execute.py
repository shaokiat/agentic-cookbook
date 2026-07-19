import streamlit as st

from common import load_example, page_tabs, render_events, selected_model

st.title("Plan & Execute")
st.caption("A planner call produces a global plan; a ReAct executor works through it step by step.")

relpath = "examples/01_agent_patterns/02_plan_and_execute.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod)

with tab_demo:
    goal = st.text_area("Goal", value=mod.DEFAULT_GOAL, height=100)

    if st.button("Run", type="primary"):
        model = selected_model()
        with st.spinner("Planning…"):
            plan = mod.make_plan(goal, model)
        st.subheader("Plan")
        st.markdown(plan)

        st.subheader("Execution")
        executor = mod.build_executor(plan, model)
        final = render_events(executor.run_events("Begin executing the plan."))
        st.markdown(f"**Final answer:**\n\n{final}")
