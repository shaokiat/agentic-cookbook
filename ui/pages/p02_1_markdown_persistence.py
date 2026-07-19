import streamlit as st

from common import chat_page, load_example

relpath = "examples/02_memory_management/01_markdown_persistence.py"
chat_page(
    "Markdown Persistence",
    "Facts survive 'session restarts' via a markdown file injected into the system prompt. "
    "Reset the conversation to simulate a new session that still remembers.",
    relpath,
    builder="make_agent",
    session_name="UI-Session",
)

mod = load_example(relpath)
with st.expander("memory_store.md"):
    st.code(mod.load_facts(), language="markdown")
    if st.button("Clear persistent memory"):
        if mod.MEMORY_FILE.exists():
            mod.MEMORY_FILE.unlink()
        st.rerun()
