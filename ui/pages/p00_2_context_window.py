import streamlit as st

from common import cost_metric, load_example, page_tabs, render_events, selected_model, tool_list_expander

st.title("Context Window")
st.caption("How the context fills up under three memory strategies: unbounded, windowed, auto-compact.")

relpath = "examples/00_primitives/02_context_window.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod)

with tab_demo:
    tool_list_expander(mod.build_agent("unbounded", model=selected_model()))
    with st.container(border=True):
        strategy = st.radio("Memory strategy", mod.STRATEGIES, horizontal=True)
        window_size = st.slider("Window size", 2, 12, 6) if strategy == "windowed" else 6
        threshold = st.slider("Compact threshold", 4, 12, 6) if strategy == "autocompact" else 6
        prompt = st.text_area("Prompt", value=mod.DEFAULT_PROMPT, height=100)
        run = st.button("Run", type="primary")

    if run:
        agent = mod.build_agent(strategy, model=selected_model(),
                                window_size=window_size, threshold=threshold)
        final = render_events(agent.run_events(prompt))
        st.markdown(f"**Final answer:**\n\n{final}")
        cost_metric(agent)

        messages = agent.memory.get_messages()
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        st.info(f"Final context: **{len(messages)} messages**, ~{total_chars} chars kept under `{strategy}`.")
        with st.expander("Full message list"):
            st.json(messages)
