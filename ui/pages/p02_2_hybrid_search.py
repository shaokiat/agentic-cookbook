import streamlit as st

from common import chat_page, load_example

relpath = "examples/02_memory_management/02_hybrid_search.py"
chat_page(
    "Hybrid Search Memory",
    "Long-term memory with BM25 + vector retrieval: remember() indexes facts, recall() fetches "
    "only what's relevant. Needs an embeddings API key.",
    relpath,
    builder="make_agent",
    session_name="UI-Session",
)

mod = load_example(relpath)
with st.expander("Memory store"):
    st.write(f"{len(mod._store)} indexed entries")
    if st.button("Clear store"):
        if mod.STORE_FILE.exists():
            mod.STORE_FILE.unlink()
        mod._store = mod.HybridMemoryStore()
        st.rerun()
