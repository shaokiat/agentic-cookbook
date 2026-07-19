import streamlit as st

from common import load_example, page_tabs, render_events, selected_model

st.title("Stop Conditions")
st.caption("Three ways an agent loop ends: natural stop, terminal tool call, and the max-steps safety cap.")

relpath = "examples/00_primitives/03_stop_condition.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod)

SCENARIOS = {
    "Natural stop": (mod.build_natural_agent, "What is the capital of Japan?"),
    "Terminal tool (finish())": (mod.build_terminal_agent, "What is the population and area of Singapore?"),
    "Step cap (broken tool)": (mod.build_capped_agent, "Use broken_tool to process the string 'hello'."),
}

with tab_demo:
    with st.container(border=True):
        scenario = st.radio("Scenario", list(SCENARIOS), horizontal=True)
        builder, default_prompt = SCENARIOS[scenario]
        prompt = st.text_area("Prompt", value=default_prompt, height=80)
        run = st.button("Run", type="primary")

    if run:
        agent = builder(model=selected_model())
        final = render_events(agent.run_events(prompt))
        st.markdown(f"**Final answer:**\n\n{final}")
        st.info(f"Context ended with {len(agent.memory.get_messages())} messages.")
