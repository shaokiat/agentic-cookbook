import pandas as pd
import streamlit as st

from common import load_example, page_tabs, selected_model

st.title("LLM Judge")
st.caption("A judge model scores agent responses against a rubric — the judge prompt is the eval.")

relpath = "examples/05_evaluation_and_monitoring/03_llm_judge.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod)

with tab_demo:
    mode = st.radio("Mode", ["Single criterion", "Multi-criterion rubric", "Pairwise A/B"], horizontal=True)
    question = st.text_area("Question for the agent", value=mod.DEFAULT_QUESTION, height=100)

    if mode == "Single criterion":
        criterion = st.text_input("Criterion", value="accuracy")
        if st.button("Run", type="primary"):
            with st.spinner("Agent answering…"):
                response = mod._run_agent("You are a helpful ML tutor.", question, selected_model())
            st.markdown(f"**Agent response:**\n\n{response}")
            with st.spinner("Judging…"):
                s = mod.score_single(question, response, criterion)
            st.metric(f"Score — {s.criterion}", f"{s.score}/5")
            st.write(s.justification)

    elif mode == "Multi-criterion rubric":
        default_rubric = "accuracy: Is the answer factually correct?\nclarity: Is it easy to follow?\nconciseness: Is it free of filler?"
        rubric_text = st.text_area("Rubric (criterion: description per line)", value=default_rubric, height=100)
        if st.button("Run", type="primary"):
            rubric = dict(
                line.split(":", 1) for line in rubric_text.strip().splitlines() if ":" in line
            )
            rubric = {k.strip(): v.strip() for k, v in rubric.items()}
            with st.spinner("Agent answering…"):
                response = mod._run_agent("You are a helpful ML tutor.", question, selected_model())
            st.markdown(f"**Agent response:**\n\n{response}")
            with st.spinner("Judging…"):
                r = mod.score_rubric(question, response, rubric)
            st.metric("Overall", f"{r.overall}/5")
            if r.scores:
                st.dataframe(pd.DataFrame([
                    {"Criterion": k, "Score": v, "Justification": r.justifications.get(k, "")}
                    for k, v in r.scores.items()
                ]), hide_index=True)

    else:
        prompt_a = st.text_input("System prompt A", value="You are a concise ML tutor. Answer in 3-4 sentences maximum.")
        prompt_b = st.text_input("System prompt B", value="You are a thorough ML professor. Explain in depth with examples.")
        if st.button("Run", type="primary"):
            model = selected_model()
            with st.spinner("Running both agents…"):
                response_a = mod._run_agent(prompt_a, question, model)
                response_b = mod._run_agent(prompt_b, question, model)
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"**Response A**\n\n{response_a}")
            with col_b:
                st.markdown(f"**Response B**\n\n{response_b}")
            with st.spinner("Judging…"):
                p = mod.compare_responses(question, response_a, response_b)
            st.success(f"Winner: **{p.winner}** — {p.justification}")
