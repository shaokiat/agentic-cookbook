import streamlit as st

from common import about_from, cost_metric, load_example, page_tabs, selected_model, tool_list_expander

CORE_CONCEPT = """\
**What it is**

Tools marked `@dangerous` don't execute immediately. The agent's loop pauses mid-step, yields
an `approval_request` event, and waits — resuming only once the surrounding UI answers with a
plain `bool`. A terminal run asks with a y/n prompt; this Streamlit page holds the paused
generator in session state and resumes it from Allow/Deny buttons.

```mermaid
flowchart TD
    T[Model requests a dangerous tool] --> R["Loop yields approval_request, pauses"]
    R --> H{Human decides}
    H -->|Allow| Run[Tool executes normally] --> O[Result added as observation]
    H -->|Deny| D["Denial string added as observation"]
    O --> M[Model continues reasoning]
    D --> M
```

**Key insight**

Approval is **loop policy, not tool internals**. The tool functions themselves stay pure and
unaware that anything is being gated — the pause lives entirely in the tool-execution step of
the agent loop, so any frontend gets to decide how it wants to ask (a terminal prompt, buttons
on a page, a Slack approval). And crucially, a denial still arrives as an ordinary `tool`
observation, not an exception — the model's view of "how do I find things out" never changes,
it just sometimes gets told no.
"""


relpath = "examples/04_tool_use_patterns/01_human_approval.py"
mod = load_example(relpath)

KEY = "approval_page"
if KEY not in st.session_state:
    st.session_state[KEY] = {"agent": None, "gen": None, "log": [], "pending": None}
P = st.session_state[KEY]

col_title, col_reset = st.columns([5, 1])
with col_title:
    st.title("Human Approval")
with col_reset:
    st.write("")
    if st.button("Reset conversation"):
        st.session_state.pop(KEY, None)
        st.rerun()
st.caption(
    "Dangerous tools pause the loop with an approval_request event. "
    "The generator is held in session state; Allow/Deny resumes it via generator.send()."
)
tab_demo = page_tabs(relpath, mod, about_extra=about_from(CORE_CONCEPT))


def pump(sent=None):
    """Advance the generator until it needs approval or finishes."""
    try:
        ev = P["gen"].send(sent)
        while True:
            if ev.kind == "approval_request":
                P["pending"] = ev
                return
            P["log"].append(ev)
            ev = P["gen"].send(None)
    except StopIteration:
        P["pending"] = None
        P["gen"] = None


with tab_demo:
    tool_list_expander(
        P["agent"] or mod.build_agent(model=selected_model()),
        note="⚠️ tools marked dangerous pause for approval before running.",
    )
    if P["agent"] is not None:
        cost_metric(P["agent"])
    for ev in P["log"]:
        if ev.kind == "user":
            with st.chat_message("user"):
                st.markdown(ev.content)
        elif ev.kind == "assistant":
            with st.chat_message("assistant"):
                st.markdown(ev.content)
        elif ev.kind == "tool_call":
            st.markdown(f"&nbsp;&nbsp;🔧 `{ev.tool}({ev.args})`")
        elif ev.kind == "observation":
            st.markdown(f"&nbsp;&nbsp;👀 {ev.content}")
        elif ev.kind == "max_steps":
            st.warning("Reached max steps safety limit.")

    if P["pending"] is not None:
        ev = P["pending"]
        st.error(f"**Approval required** — the agent wants to run `{ev.tool}({ev.args})`")
        col_allow, col_deny = st.columns(2)
        if col_allow.button("✅ Allow", type="primary"):
            P["pending"] = None
            pump(True)
            st.rerun()
        if col_deny.button("🚫 Deny"):
            P["pending"] = None
            pump(False)
            st.rerun()
        st.stop()

    default = (
        "Create a temporary file at '/tmp/hil_demo.txt' with the content "
        "'Hello from the agent!', then list /tmp to confirm it exists, "
        "and finally delete the file."
    )
    if P["gen"] is None:
        if prompt := st.chat_input("Ask the file agent… (try the demo task below)"):
            if P["agent"] is None:
                P["agent"] = mod.build_agent(model=selected_model())
                P["agent"].verbose = False
            P["gen"] = P["agent"].run_events(prompt)
            pump()
            st.rerun()
        st.caption(f"Demo task: *{default}*")
