import streamlit as st

from core.model import ModelProvider

from common import about_from, cost_metric, load_example, page_tabs, render_events, selected_model, tool_list_expander

st.title("Plan & Execute")
st.caption("A planner call produces a global plan; a ReAct executor works through it step by step.")

CORE_CONCEPT = """\
**What it is**

Plan-and-Execute is a two-phase pattern that separates high-level strategy from low-level
execution. Unlike a pure ReAct agent that decides its next move on the fly, this pattern uses a
Planner to decompose the goal into a concrete list of steps up front, then hands that plan to an
Executor that carries it out — particularly effective on goals with several distinct steps.

```mermaid
flowchart TD
    G[Goal] --> P["Planner (single model call, no tools)"]
    P --> Plan["Structured step-by-step plan"]
    Plan --> E["Executor = standard ReAct agent, plan as its system prompt"]
    subgraph Executor loop
    T[Think] --> A[Act: execute tool] --> O[Observe: result to memory] --> T
    end
    E --> T
    O --> F[Final answer]
```

**The two phases**

- **Planning** — a single model call, with a system prompt that enforces strategic thinking,
  produces a numbered list of steps. No tools are executed in this phase; it's pure decomposition.
- **Execution** — the plan becomes part of the Executor's system prompt, and the Executor is
  just the standard `Agent` running its normal Think → Act → Observe loop, focused entirely on
  carrying out the planned steps with its available tools.

**What this buys you over plain ReAct**

Because the strategy is committed to before execution starts, the model doesn't have to
re-derive "what should I do next" from scratch at every step — it's already been decided. In a
real run analyzing a codebase, this showed up as: explore the directory structure, drill into
`core/`, then fire off **4 parallel tool calls in a single turn** to read the source files it
had identified — reducing LLM round-trips rather than executing tools concurrently (the
Python loop still runs them one at a time). The loop terminates the same way as any ReAct
agent: it stops issuing tool calls once it has gathered enough to answer.
"""


relpath = "examples/01_agent_patterns/02_plan_and_execute.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod, about_extra=about_from(CORE_CONCEPT))

with tab_demo:
    tool_list_expander(mod.build_registry(), note="Used by the executor once planning is done.")
    goal = st.text_area("Goal", value=mod.DEFAULT_GOAL, height=100)

    if st.button("Run", type="primary"):
        provider = ModelProvider(selected_model())
        with st.spinner("Planning…"):
            plan = mod.make_plan(goal, model_provider=provider)
        st.subheader("Plan")
        st.markdown(plan)

        st.subheader("Execution")
        executor = mod.build_executor(plan, model_provider=provider)
        final = render_events(executor.run_events("Begin executing the plan."))
        st.markdown(f"**Final answer:**\n\n{final}")
        cost_metric(provider)
