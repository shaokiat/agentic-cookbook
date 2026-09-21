import streamlit as st

from common import about_from, cost_metric, load_example, page_tabs, render_events, selected_model, tool_list_expander

st.title("Stop Conditions")
st.caption("Three ways an agent loop ends: natural stop, terminal tool call, and the max-steps safety cap.")

CORE_CONCEPT = """\
**What it is**

How does an agent know it's done? Without an explicit termination signal, an agent loop either
runs forever or stops prematurely. This is a correctness requirement, not a minor
implementation detail — an agent with no stop condition runs until it exhausts the context
window, the token budget, or the patience of whoever is paying the bill.

**Three kinds of stop conditions, all active at once**

1. **Step cap (`max_steps`)** — the simplest guard. The loop exits after a fixed number of
   iterations no matter what the agent has done. It's a last-resort safety net, not the primary
   stop mechanism: too low and the agent gives up on hard tasks, too high and a stuck agent
   burns tokens before anyone notices.
2. **Terminal tool call** — the agent signals completion by calling a designated `finish()` tool
   instead of stopping mid-sentence. More reliable than detecting "no tool call," because it
   forces the model to make an explicit, structured decision to stop.
3. **Model-emitted stop signal (natural stop)** — the model simply stops calling tools and
   emits plain text; the loop treats the absence of a tool call as "done." This is the default
   mechanism here — it works well conversationally but is fragile: the model can stop early if
   it's unsure what to do next, even with the task unfinished.

```mermaid
flowchart TD
    Start([Loop iteration]) --> Cap{"steps < max_steps?"}
    Cap -->|No| StepCapExit["Step cap exit — safety net, task may be incomplete"]
    Cap -->|Yes| Gen[Model generates response]
    Gen --> Finish{"Called finish()?"}
    Finish -->|Yes| Done([Terminal tool exit — explicit completion])
    Finish -->|No| ToolCall{"Any tool call?"}
    ToolCall -->|Yes| Exec[Execute tools, add observations] --> Start
    ToolCall -->|No| Natural([Natural stop — no tool call])
```

The natural stop handles the happy path, the step cap handles infinite loops, and the terminal
tool handles tasks where explicit confirmation matters. Picking `max_steps` is task-dependent —
a couple of tool calls for simple Q&A, 15-30 for multi-step research or code-generation loops,
higher still (with cost monitoring) for open-ended planning.

**Failure modes**

- **Premature stop** — the model emits text mid-task when it should have called another tool,
  often from an ambiguous or too-permissive system prompt.
- **Infinite tool loop** — the model keeps calling the same failing tool; the step cap prevents
  a crash, but the final output is incomplete.
- **Silent truncation** — the agent hits `max_steps` and the caller gets back whatever the last
  message happened to be, with no signal the task was cut short. Always check *how* the loop
  exited, not just what it returned.
"""


relpath = "examples/00_primitives/03_stop_condition.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod, about_extra=about_from(CORE_CONCEPT))

SCENARIOS = {
    "Natural stop": (mod.build_natural_agent, "What is the capital of Japan?"),
    "Terminal tool (finish())": (mod.build_terminal_agent, "What is the population and area of Singapore?"),
    "Step cap (broken tool)": (mod.build_capped_agent, "Use broken_tool to process the string 'hello'."),
}

with tab_demo:
    with st.container(border=True):
        scenario = st.radio("Scenario", list(SCENARIOS), horizontal=True)
        builder, default_prompt = SCENARIOS[scenario]
        tool_list_expander(builder(model=selected_model()))
        prompt = st.text_area("Prompt", value=default_prompt, height=80)
        run = st.button("Run", type="primary")

    if run:
        agent = builder(model=selected_model())
        final = render_events(agent.run_events(prompt))
        st.markdown(f"**Final answer:**\n\n{final}")
        st.info(f"Context ended with {len(agent.memory.get_messages())} messages.")
        cost_metric(agent)
