import streamlit as st

from common import about_from, chat_page, load_example

CORE_CONCEPT = """\
**What it is**

The context window is wiped when a session ends — an agent that helped you yesterday
remembers nothing today. Intermediate memory fixes that by writing facts to disk during a
session and re-injecting them into the system prompt at the *next* session's start. The new
agent has a completely empty conversation history; it only "remembers" because the facts were
persisted and read back before it ever ran.

```mermaid
flowchart LR
    subgraph Session 1
    U1[User states facts] --> S1["save_fact() tool"] --> F[(memory_store.md)]
    end
    F --> L["load_facts() at startup"]
    L --> P[Injected into system prompt]
    subgraph Session 2
    P --> A2["New Agent — empty conversation memory"]
    A2 --> R[Recalls facts correctly]
    end
```

**Three moving parts**

- **`memory_store.md`** — a plain markdown file, one bullet per fact. Human-readable and
  git-diffable, unlike a database or vector store.
- **`save_fact` tool** — appends a bullet to the file; the agent itself decides what's worth
  keeping.
- **System-prompt injection** — at session start, the file's contents are read and embedded
  directly into the system prompt, before the agent takes its first step.

**Why this counts as a distinct memory tier**

It's a middle ground between the context window (survives nothing) and hybrid retrieval
(scales to thousands of facts, surfaces only what's relevant). Everything here is injected on
every session regardless of relevance — fine for dozens of facts, but the system prompt gets
unwieldy and the model's attention dilutes once you're into the hundreds. That scaling limit is
exactly what long-term hybrid retrieval (Hybrid Search Memory) is built to solve.
"""


relpath = "examples/02_memory_management/01_markdown_persistence.py"
chat_page(
    "Markdown Persistence",
    "Facts survive 'session restarts' via a markdown file injected into the system prompt. "
    "Reset the conversation to simulate a new session that still remembers.",
    relpath,
    builder="make_agent",
    session_name="UI-Session",
    about_extra=about_from(CORE_CONCEPT),
)

mod = load_example(relpath)
with st.expander("memory_store.md"):
    st.code(mod.load_facts(), language="markdown")
    if st.button("Clear persistent memory"):
        if mod.MEMORY_FILE.exists():
            mod.MEMORY_FILE.unlink()
        st.rerun()
