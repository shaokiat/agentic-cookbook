import pandas as pd
import streamlit as st

from core.model import ModelProvider

from common import about_from, cost_metric, load_example, page_tabs, selected_model

st.title("LLM Judge")
st.caption("A judge model scores agent responses against a rubric — the judge prompt is the eval.")

CORE_CONCEPT = """\
**What it is**

A second model call — the judge — scores a first agent's response, in one of three modes:
single-criterion rating (1-5 plus a justification), multi-criterion rubric (structured JSON per
criterion), or pairwise A/B comparison between two responses to the same question.

```mermaid
flowchart LR
    Q[Question] --> A["Agent under test produces a response"]
    A --> J["Judge model scores it against a rubric prompt"]
    J --> S["Structured score — rating, JSON per criterion, or A/B verdict"]
```

**Key insight**

The judge prompt **is** the eval — it deserves the same version control and scrutiny as code,
because changing its wording changes what "good" means for every response it scores. Structured
JSON output (rather than free-form prose) is what makes results machine-readable, so evals can
run unattended in CI across hundreds of cases instead of relying on someone eyeballing outputs
one at a time.
"""


relpath = "examples/05_evaluation_and_monitoring/03_llm_judge.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod, about_extra=about_from(CORE_CONCEPT))

with tab_demo:
    mode = st.radio("Mode", ["Single criterion", "Multi-criterion rubric", "Pairwise A/B"], horizontal=True)
    question = st.text_area("Question for the agent", value=mod.DEFAULT_QUESTION, height=100)

    if mode == "Single criterion":
        criterion = st.text_input("Criterion", value="accuracy")
        if st.button("Run", type="primary"):
            agent_provider, judge_provider = ModelProvider(selected_model()), ModelProvider(mod.JUDGE_MODEL)
            with st.spinner("Agent answering…"):
                response = mod._run_agent("You are a helpful ML tutor.", question, model_provider=agent_provider)
            st.markdown(f"**Agent response:**\n\n{response}")
            with st.spinner("Judging…"):
                s = mod.score_single(question, response, criterion, model_provider=judge_provider)
            st.metric(f"Score — {s.criterion}", f"{s.score}/5")
            st.write(s.justification)
            cost_metric(agent_provider, judge_provider)

    elif mode == "Multi-criterion rubric":
        default_rubric = "accuracy: Is the answer factually correct?\nclarity: Is it easy to follow?\nconciseness: Is it free of filler?"
        rubric_text = st.text_area("Rubric (criterion: description per line)", value=default_rubric, height=100)
        if st.button("Run", type="primary"):
            rubric = dict(
                line.split(":", 1) for line in rubric_text.strip().splitlines() if ":" in line
            )
            rubric = {k.strip(): v.strip() for k, v in rubric.items()}
            agent_provider, judge_provider = ModelProvider(selected_model()), ModelProvider(mod.JUDGE_MODEL)
            with st.spinner("Agent answering…"):
                response = mod._run_agent("You are a helpful ML tutor.", question, model_provider=agent_provider)
            st.markdown(f"**Agent response:**\n\n{response}")
            with st.spinner("Judging…"):
                r = mod.score_rubric(question, response, rubric, model_provider=judge_provider)
            st.metric("Overall", f"{r.overall}/5")
            if r.scores:
                st.dataframe(pd.DataFrame([
                    {"Criterion": k, "Score": v, "Justification": r.justifications.get(k, "")}
                    for k, v in r.scores.items()
                ]), hide_index=True)
            cost_metric(agent_provider, judge_provider)

    else:
        prompt_a = st.text_input("System prompt A", value="You are a concise ML tutor. Answer in 3-4 sentences maximum.")
        prompt_b = st.text_input("System prompt B", value="You are a thorough ML professor. Explain in depth with examples.")
        if st.button("Run", type="primary"):
            agent_provider = ModelProvider(selected_model())  # shared across both responses
            judge_provider = ModelProvider(mod.JUDGE_MODEL)
            with st.spinner("Running both agents…"):
                response_a = mod._run_agent(prompt_a, question, model_provider=agent_provider)
                response_b = mod._run_agent(prompt_b, question, model_provider=agent_provider)
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"**Response A**\n\n{response_a}")
            with col_b:
                st.markdown(f"**Response B**\n\n{response_b}")
            with st.spinner("Judging…"):
                p = mod.compare_responses(question, response_a, response_b, model_provider=judge_provider)
            st.success(f"Winner: **{p.winner}** — {p.justification}")
            cost_metric(agent_provider, judge_provider)
