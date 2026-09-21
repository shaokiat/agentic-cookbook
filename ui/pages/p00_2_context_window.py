import streamlit as st

from common import about_from, cost_metric, load_example, page_tabs, render_events, selected_model, tool_list_expander

st.title("Context Window")
st.caption("How the context fills up under three memory strategies: unbounded, windowed, auto-compact.")

CORE_CONCEPT = """\
**What it is**

Everything the agent "knows" at any moment is what fits in the context window — it's the
agent's *only* working memory during a run. If something isn't in the context, the agent
cannot reason about it. The window is finite and expensive, so managing its growth is one of
the central engineering problems in production agents, not an optional extra.

**What actually fills it up**

The context window is a flat, growing list of chat messages. Every step adds to it:

| Message type | Role | Grows with |
| :--- | :--- | :--- |
| System prompt | `system` | Fixed, written once |
| User input | `user` | Number of user turns |
| Model reasoning | `assistant` | Steps taken |
| Tool call requests | `assistant` + `tool_calls` | Tools called per step |
| Tool results | `tool` | Tools called, output size |

Tool results are usually the biggest consumer — a tool that returns a large file or a long web
page can burn thousands of tokens in a single step. With a 200k token limit and ~1k-token tool
outputs, that's roughly 200 steps before hitting the wall.

```mermaid
flowchart LR
    A[System prompt] --> B[User turn]
    B --> C[Assistant + tool call]
    C --> D[Tool result]
    D --> E[Assistant + tool call]
    E --> F[Tool result]
    F --> G[... repeats every step ...]
    G --> H{Token limit}
```

**Strategies to manage the growth**

- **Auto-snip (sliding window)** — keep only the last N messages, always preserving the system
  prompt. Simple and cheap, but the agent loses awareness of early steps; if step 15 depends on
  an observation evicted from step 2, it fails or hallucinates.
- **Auto-compact (summarization)** — replace old messages with a model-generated summary before
  they'd be evicted, preserving tool results, decisions, and open tasks. Costs extra latency and
  tokens, and the summary can still drop details that matter later.
- **Output truncation** — cap how much of a tool's raw output ever enters memory in the first
  place, rather than truncating the conversation after the fact.
- **Token budget signaling (proactive)** — the only strategy that acts *before* overflow: inject
  the remaining token budget into the system prompt each turn so the model self-regulates its
  own verbosity instead of you reacting after the fact.

**Failure modes**

Context overflow (the message list exceeds the token limit and the API errors out), lost
observations (auto-snip evicts something the model still needed), and repetitive loops (the
agent can't see its earlier attempts, so it re-calls the same tool with the same arguments).
"""


relpath = "examples/00_primitives/02_context_window.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod, about_extra=about_from(CORE_CONCEPT))

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
