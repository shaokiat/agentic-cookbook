"""Shared helpers for the Streamlit UI: example loading, model picker, event rendering."""
import importlib.util
import sys
from pathlib import Path

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[1]

GITHUB_BLOB = "https://github.com/shaokiat/agentic-cookbook/blob/main"

BLOG_PATTERNS_URL = "https://shaokiat.github.io/shaokiat-blog/docs/genai-agents/agent_design_patterns"

# relpath -> (pattern name on the blog, URL anchor)
BLOG_ANCHORS = {
    "examples/00_primitives/01_tool_use.py": ("Tool Use / Function Calling", "4-tool-use--function-calling"),
    "examples/00_primitives/02_context_window.py": ("Context Window Management", "context-window-management"),
    "examples/01_agent_patterns/01_react_basic.py": ("ReAct (Reason + Act)", "1-react-reason--act"),
    "examples/01_agent_patterns/02_plan_and_execute.py": ("Plan and Execute", "2-plan-and-execute"),
    "examples/01_agent_patterns/03_reflexion.py": ("Reflection / Self-Critique", "3-reflection--self-critique"),
    "examples/02_memory_management/01_markdown_persistence.py": ("Memory Management", "9-memory-management"),
    "examples/02_memory_management/02_hybrid_search.py": ("Memory Management", "9-memory-management"),
    "examples/03_multi_agent_systems/01_orchestrator_worker.py": ("Orchestrator–Subagent", "5-orchestratorsubagent"),
    "examples/03_multi_agent_systems/02_parallel_subagents.py": ("Parallelization / Fan-out", "6-parallelization--fan-out"),
    "examples/03_multi_agent_systems/03_sequential_pipeline.py": ("Pipeline / DAG", "7-pipeline--dag"),
    "examples/03_multi_agent_systems/04_async_announce.py": ("Orchestrator–Subagent", "5-orchestratorsubagent"),
    "examples/04_tool_use_patterns/01_human_approval.py": ("Human in the Loop (HITL)", "8-human-in-the-loop-hitl"),
    "examples/04_tool_use_patterns/02_parallel_tool_calls.py": ("Parallelization / Fan-out", "6-parallelization--fan-out"),
    "examples/04_tool_use_patterns/03_error_recovery.py": ("Error Recovery", "error-recovery"),
    "examples/04_tool_use_patterns/04_dynamic_tools.py": ("Tool Use / Function Calling", "4-tool-use--function-calling"),
    "examples/05_evaluation_and_monitoring/01_log_analyzer.py": ("Observability and Tracing", "observability-and-tracing"),
    "examples/05_evaluation_and_monitoring/02_agent_tracer.py": ("Observability and Tracing", "observability-and-tracing"),
    "examples/05_evaluation_and_monitoring/03_llm_judge.py": ("Guardrails and Validation", "10-guardrails-and-validation"),
}

MODELS = [
    "anthropic/claude-haiku-4-5",
    "anthropic/claude-sonnet-4-5",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
]

DEFAULT_MODEL = "anthropic/claude-haiku-4-5"


def load_example(relpath: str):
    """Import an example module by repo-relative path (numbered dirs aren't packages)."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    key = relpath.replace("/", ".").removesuffix(".py")
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, REPO_ROOT / relpath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


def live_panel(label: str):
    """A bordered, always-visible container with mutable label/body slots — replaces st.status,
    which auto-collapses once marked complete. Returns (label_slot, body_slot); update via
    label_slot.markdown(f"**...**") / body_slot.markdown(...) as progress comes in."""
    container = st.container(border=True)
    with container:
        label_slot = st.empty()
        body_slot = st.empty()
    label_slot.markdown(f"**{label}**")
    return label_slot, body_slot


def _about_content(relpath: str | None, mod=None, *, walkthrough_path: str | None = None,
                    reference_paths: list[str] | None = None) -> None:
    """Body of the 'About' tab: blog pattern link, Docs/Reference citation, GitHub links.

    Deliberately avoids dumping the walkthrough .md or source .py inline — that's what made the
    old expander huge. Everything here is a short link out to GitHub or the blog instead."""
    pattern = BLOG_ANCHORS.get(relpath)
    if pattern:
        name, anchor = pattern
        st.markdown(f"**Pattern:** {name}  \n[Read on the blog ↗]({BLOG_PATTERNS_URL}#{anchor})")
        st.divider()

    doc = (mod.__doc__ or "") if mod is not None else ""
    ref_lines = [ln.strip() for ln in doc.splitlines() if ln.strip().startswith("Reference:")]
    if ref_lines:
        for ln in ref_lines:
            _, _, rest = ln.partition(":")
            st.caption(f"**Reference:** {rest.strip()}")

    wp_rel = walkthrough_path or (relpath.replace(".py", ".md") if relpath else None)
    wp = REPO_ROOT / wp_rel if wp_rel else None
    has_walkthrough = wp is not None and wp.exists()
    sp = REPO_ROOT / relpath if relpath else None
    has_source = sp is not None and sp.exists() and sp.suffix == ".py"

    if has_walkthrough or has_source or reference_paths:
        st.divider()
    col_walk, col_src = st.columns(2)
    if has_walkthrough:
        col_walk.link_button("Walkthrough ↗", f"{GITHUB_BLOB}/{wp_rel}", use_container_width=True)
    if has_source:
        col_src.link_button("Source ↗", f"{GITHUB_BLOB}/{relpath}", use_container_width=True)
    for p in reference_paths or []:
        st.link_button(f"{Path(p).name} ↗", f"{GITHUB_BLOB}/{p}", use_container_width=True)


def page_tabs(relpath: str | None, mod=None, *, walkthrough_path: str | None = None,
              reference_paths: list[str] | None = None):
    """Creates the ['Demo', 'About'] tabs every page uses, rendering the About tab immediately.

    Returns the Demo tab context manager — callers put their existing page body inside
    `with tab_demo:`."""
    tab_demo, tab_about = st.tabs(["Demo", "📖 About"])
    with tab_about:
        _about_content(relpath, mod, walkthrough_path=walkthrough_path, reference_paths=reference_paths)
    return tab_demo


def model_picker() -> str:
    """Global sidebar model selector; defaults to DEFAULT_MODEL."""
    return st.sidebar.selectbox("Model", MODELS, index=MODELS.index(DEFAULT_MODEL), key="model_choice")


def selected_model() -> str:
    return st.session_state.get("model_choice", DEFAULT_MODEL)


def render_events(gen) -> str:
    """Drive an Agent.run_events generator, rendering each event inline, fully expanded, separated by step dividers."""
    final = ""
    first_step = True
    for ev in gen:
        if ev.kind == "step_start":
            if not first_step:
                st.divider()
            first_step = False
            st.markdown(f"**Step {ev.step}**")
        elif ev.kind == "tool_call":
            st.write(f"🔧 `{ev.tool}({ev.args})`")
        elif ev.kind == "observation":
            st.write(f"👀 {ev.content}")
        elif ev.kind == "assistant":
            st.markdown(ev.content)
        elif ev.kind == "max_steps":
            st.warning("Reached max steps safety limit.")
        elif ev.kind == "final":
            final = ev.content
    return final


def chat_page(title: str, caption: str, relpath: str, builder: str = "build_agent", **build_kwargs):
    """Multi-turn chat page: one persistent agent per session, chat input drives run_events."""
    mod = load_example(relpath)
    model = selected_model()
    state_key = f"chat::{relpath}::{model}::{sorted(build_kwargs.items())}"

    col_title, col_reset = st.columns([5, 1])
    with col_title:
        st.title(title)
    with col_reset:
        st.write("")
        if st.button("Reset conversation", key=f"reset::{relpath}"):
            st.session_state.pop(state_key, None)
    st.caption(caption)
    tab_demo = page_tabs(relpath, mod)

    if state_key not in st.session_state:
        st.session_state[state_key] = {
            "agent": getattr(mod, builder)(model=model, **build_kwargs),
            "history": [],
        }
    chat = st.session_state[state_key]

    with tab_demo:
        for role, content in chat["history"]:
            with st.chat_message(role):
                st.markdown(content)

        if prompt := st.chat_input("Message the agent…"):
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                final = render_events(chat["agent"].run_events(prompt))
            chat["history"].append(("user", prompt))
            chat["history"].append(("assistant", final))


def single_run_page(title: str, caption: str, relpath: str, builder: str = "build_agent",
                    default_prompt_attr: str = "DEFAULT_PROMPT", **build_kwargs):
    """One-shot demo page: prefilled prompt, Run button, events streamed inline."""
    st.title(title)
    st.caption(caption)

    mod = load_example(relpath)
    tab_demo = page_tabs(relpath, mod)

    with tab_demo:
        prompt = st.text_area("Prompt", value=getattr(mod, default_prompt_attr, ""), height=120)

        if st.button("Run", type="primary"):
            agent = getattr(mod, builder)(model=selected_model(), **build_kwargs)
            final = render_events(agent.run_events(prompt))
            st.success("Run complete")
            st.markdown(f"**Final answer:**\n\n{final}")
