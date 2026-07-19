import queue
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import streamlit as st

from common import live_panel, page_tabs

_SUBFIELD_RE = re.compile(r"^(For|Against):\s*(.*)$")
_LABEL_COLON_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 /-]{1,40}):\s+(.*)$")
_LABEL_COLUMN_RE = re.compile(r"^([A-Z][A-Z0-9 /]{1,40}?)\s{2,}(.*)$")


def _theta_to_markdown(text: str) -> str:
    """theta-agent's system prompt deliberately outputs plain text (ALL CAPS labels,
    column-aligned scores, blank-line-separated sections) for a terminal — this reformats
    that structure into markdown (bold labels, bullets, headings) for the Streamlit UI."""
    blocks = text.strip("\n").split("\n\n")
    out_blocks = []
    for block in blocks:
        lines = []
        for raw in block.split("\n"):
            stripped = raw.strip()
            if not stripped:
                continue
            sub = _SUBFIELD_RE.match(stripped)
            if sub:
                lines.append(f"- **{sub.group(1)}:** {sub.group(2)}")
                continue
            m = _LABEL_COLON_RE.match(stripped) or _LABEL_COLUMN_RE.match(stripped)
            if m:
                label, rest = m.group(1).strip(), m.group(2).strip()
                if rest.startswith("|"):
                    parts = [p.strip() for p in rest.split("|") if p.strip()]
                    lines.append(f"#### {label} — {' — '.join(parts)}" if parts else f"#### {label}")
                    continue
                lines.append(f"**{label}:** {rest}" if rest else f"**{label}**")
                continue
            lines.append(stripped)
        out_blocks.append("  \n".join(lines))
    return "\n\n".join(out_blocks)

st.title("theta-agent")
st.caption(
    "ticker → agentic research loop (price, news, financials, options chain, earnings) → "
    "options strategy summary → follow-up chat. Runs the same ThetaAgent used by the CLI/TUI."
)
tab_demo = page_tabs(
    None,
    walkthrough_path="agents/theta-agent/README.md",
    reference_paths=["agents/theta-agent/docs/OVERVIEW.md"],
)

THETA_DIR = Path(__file__).resolve().parents[2] / "agents" / "theta-agent"

with tab_demo:
    if str(THETA_DIR) not in sys.path:
        sys.path.insert(0, str(THETA_DIR))
    try:
        import anthropic

        from theta.agent import ThetaAgent
        from theta.tools import TOOLS
    except ImportError:
        st.error(
            "theta-agent is not installed in this environment. From the repo root run:\n\n"
            "`uv pip install --python .venv/bin/python -e agents/theta-agent`"
        )
        st.stop()

    import os

    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.error("ANTHROPIC_API_KEY is not set — add it to `.env` at the repo root.")
        st.stop()

    with st.expander(f"Tools available ({len(TOOLS)})"):
        for tool in TOOLS:
            st.markdown(f"**`{tool['name']}`** — {tool['description']}")
        st.caption(
            "Runs a 5-signal scorecard (directional bias, event clarity, IV regime, conviction, "
            "liquidity) over the fetched data, then derives an options strategy from the composite."
        )

    with st.container(border=True):
        ticker = st.text_input("Ticker", placeholder="e.g. AAPL").strip().upper()
        position = st.text_input(
            "Current position (optional)", placeholder="e.g. Long 100 shares @ $178"
        ).strip()
        run = st.button("Research", type="primary")

    state_key = f"theta::{ticker}"

    if run and ticker:
        st.session_state.pop(state_key, None)
        client = anthropic.Anthropic()
        events: queue.Queue = queue.Queue()

        agent = ThetaAgent(
            ticker=ticker,
            client=client,
            positions=position or None,
            on_output=lambda text: events.put(("output", text)),
            on_tool_call=lambda name, preview: events.put(("tool_call", f"{name}({preview})")),
            on_status=lambda text: events.put(("status", text)),
        )

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(agent.run_research)

            status_label, status_body = live_panel(f"Researching {ticker}…")
            tool_lines: list[str] = []

            while not (future.done() and events.empty()):
                try:
                    kind, payload = events.get(timeout=0.1)
                except queue.Empty:
                    continue
                if kind == "tool_call":
                    tool_lines.append(f"🔧 {payload}")
                    status_body.markdown("\n\n".join(tool_lines))
                elif kind == "status":
                    status_label.markdown(f"**{payload}**")

            summary, messages = future.result()
            status_label.markdown(f"**{ticker} research complete**")

        st.session_state[state_key] = {"agent": agent, "messages": messages, "summary": summary}

    if state_key in st.session_state:
        chat = st.session_state[state_key]
        st.divider()
        st.metric("Cost", f"${chat['agent'].total_cost:.4f}")
        st.markdown(_theta_to_markdown(chat["summary"]))

        st.divider()
        st.markdown("**Follow-up chat** — try `/summary`, `/scorecard`, `/strategy`, `/position`")
        for msg in chat["messages"][1:]:
            if msg["role"] not in ("user", "assistant") or not isinstance(msg["content"], str):
                continue
            with st.chat_message(msg["role"]):
                st.markdown(_theta_to_markdown(msg["content"]))

        if prompt := st.chat_input("Ask a follow-up…"):
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Thinking…"):
                    reply = chat["agent"].send_message(prompt, chat["messages"])
                st.markdown(_theta_to_markdown(reply))
