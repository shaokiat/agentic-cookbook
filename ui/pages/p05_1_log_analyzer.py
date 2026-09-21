from pathlib import Path

import pandas as pd
import streamlit as st

from common import REPO_ROOT, load_example, page_tabs

st.title("Log Analyzer")
st.caption("Parses the markdown traces AgentLogger writes and reports steps, tool frequency, and error rates.")

relpath = "examples/05_evaluation_and_monitoring/01_log_analyzer.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod)

with tab_demo:
    log_dir = Path(st.text_input("Log directory", value=str(REPO_ROOT / "examples/logs")))

    stats = mod.collect_stats(log_dir)
    if not stats["log_files"]:
        st.warning(f"No .md log files found in `{log_dir}`. Run any example first — agents with a log_path write traces there.")
        st.stop()

    st.write(f"Analyzed **{len(stats['log_files'])}** log file(s), **{len(stats['runs'])}** run(s)")

    st.subheader("Run Summary")
    st.dataframe(pd.DataFrame([
        {
            "File": log_file.name,
            "Agent": run.agent_name,
            "Steps": run.steps,
            "Tool Calls": len(run.tool_calls),
            "Errors": run.error_count,
            "User Input": run.user_input[:60],
        }
        for log_file, run in stats["runs"]
    ]), hide_index=True)

    if stats["tool_freq"]:
        st.subheader("Tool Frequency")
        st.dataframe(pd.DataFrame([
            {
                "Tool": name,
                "Calls": count,
                "Errors": stats["tool_errors"].get(name, 0),
                "Error Rate": f"{stats['tool_errors'].get(name, 0) / count * 100:.0f}%",
            }
            for name, count in sorted(stats["tool_freq"].items(), key=lambda x: -x[1])
        ]), hide_index=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Runs", len(stats["runs"]))
    c2.metric("Total steps", stats["total_steps"])
    c3.metric("Tool calls", stats["total_tools"])
    c4.metric("Error rate", f"{stats['error_rate']:.1f}%")
