import streamlit as st

from common import about_from, chat_page, load_example

CORE_CONCEPT = """\
**What it is**

Long-term memory is a searchable archive the agent queries on demand, rather than a pile of
facts dumped into every system prompt. Unlike markdown persistence — which injects everything,
every session — this tier only surfaces what's *relevant* to the current query, so context
usage stays bounded no matter how many facts have accumulated over time.

```mermaid
flowchart LR
    S[Session start — clean system prompt] --> Q["Agent calls recall(query)"]
    Q --> H["Hybrid search: BM25 + vector"]
    H --> K[Top-k relevant facts only]
    K --> C[Added to context]
    W["Agent calls remember(fact)"] --> Idx[(Indexed store on disk)]
    Idx --> H
```

**Why hybrid — neither method works well alone**

- **BM25 (keyword)** catches exact matches — names, IDs, URLs, literal tokens like "AWS" — but
  misses semantic paraphrasing.
- **Vector (cosine similarity)** catches semantic matches — concepts and synonyms — but misses
  exact tokens a keyword search would nail.
- **Hybrid** combines both, weighted (this example follows Open Claw's community extension
  split of 30% BM25 + 70% vector), so a query like *"deployment infrastructure"* still surfaces
  a fact phrased as *"GitHub Actions for CI/CD."*

**Two tools, one store**

`remember(fact)` embeds and persists a fact to disk; `recall(query)` scores every stored fact
by combined BM25 + vector similarity and returns only the top-k. The store survives restarts —
a new session's agent reloads it from disk — but every session's system prompt stays clean
until the agent actually decides it needs to look something up.

**Trade-off vs markdown persistence:** retrieval is only *good* (top-k can miss an edge case),
where full injection is *perfect* (everything is always present) — but hybrid search is the
only tier of the three that scales to thousands of facts instead of dozens.
"""


relpath = "examples/02_memory_management/02_hybrid_search.py"
chat_page(
    "Hybrid Search Memory",
    "Long-term memory with BM25 + vector retrieval: remember() indexes facts, recall() fetches "
    "only what's relevant. Needs an embeddings API key.",
    relpath,
    builder="make_agent",
    session_name="UI-Session",
    about_extra=about_from(CORE_CONCEPT),
)

mod = load_example(relpath)
with st.expander("Memory store"):
    st.write(f"{len(mod._store)} indexed entries")
    if st.button("Clear store"):
        if mod.STORE_FILE.exists():
            mod.STORE_FILE.unlink()
        mod._store = mod.HybridMemoryStore()
        st.rerun()
