"""Streamlit entry point: streamlit run ui/app.py (from the repo root)."""
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

UI_DIR = Path(__file__).resolve().parent
REPO_ROOT = UI_DIR.parent
for p in (str(UI_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

load_dotenv(REPO_ROOT / ".env")

from common import model_picker

st.set_page_config(page_title="agentic-cookbook", page_icon="🍳", layout="wide")

nav_pages = {
    "Primitives": [
        st.Page("pages/p00_1_tool_use.py", title="Tool Use"),
        st.Page("pages/p00_2_context_window.py", title="Context Window"),
        st.Page("pages/p00_3_stop_condition.py", title="Stop Conditions"),
    ],
    "Agent Patterns": [
        st.Page("pages/p01_1_react_chat.py", title="ReAct Chat"),
        st.Page("pages/p01_2_plan_execute.py", title="Plan & Execute"),
        st.Page("pages/p01_3_reflexion.py", title="Reflexion"),
    ],
    "Memory": [
        st.Page("pages/p02_1_markdown_persistence.py", title="Markdown Persistence"),
        st.Page("pages/p02_2_hybrid_search.py", title="Hybrid Search"),
    ],
    "Multi-Agent": [
        st.Page("pages/p03_1_orchestrator.py", title="Orchestrator / Worker"),
        st.Page("pages/p03_2_parallel_subagents.py", title="Parallel Subagents"),
        st.Page("pages/p03_3_sequential_pipeline.py", title="Sequential Pipeline"),
        st.Page("pages/p03_4_async_announce.py", title="Async Announce"),
    ],
    "Tool Use Patterns": [
        st.Page("pages/p04_1_human_approval.py", title="Human Approval"),
        st.Page("pages/p04_2_parallel_tools.py", title="Parallel Tool Calls"),
        st.Page("pages/p04_3_error_recovery.py", title="Error Recovery"),
        st.Page("pages/p04_4_dynamic_tools.py", title="Dynamic Tools"),
    ],
    "Evaluation": [
        st.Page("pages/p05_1_log_analyzer.py", title="Log Analyzer"),
        st.Page("pages/p05_2_agent_tracer.py", title="Agent Tracer"),
        st.Page("pages/p05_3_llm_judge.py", title="LLM Judge"),
    ],
    "Agents": [
        st.Page("pages/p90_mini_researcher.py", title="Mini Researcher"),
    ],
}

# st.navigation's built-in sidebar menu can't collapse per section — only its
# flat page-count cap does. Register pages with position="hidden" for routing
# and build the accordion ourselves with expanders + page_link.
page_list = [p for pages in nav_pages.values() for p in pages]
nav = st.navigation(page_list, position="hidden")

st.sidebar.title("🍳 agentic-cookbook")
model_picker()
st.sidebar.divider()

for chapter, pages in nav_pages.items():
    with st.sidebar.expander(chapter, expanded=(nav in pages)):
        for p in pages:
            st.page_link(p, label=p.title)

st.sidebar.caption(f"{len(page_list)} examples across {len(nav_pages)} chapters")
nav.run()
