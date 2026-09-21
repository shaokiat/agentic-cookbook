from pathlib import Path

import pandas as pd
import streamlit as st

from common import about_from, load_example, page_tabs, REPO_ROOT

st.title("Log Analyzer")
st.caption("Parses the markdown traces AgentLogger writes and reports steps, tool frequency, and error rates.")

CORE_CONCEPT = """\
**What it is**

Every agent run that's given a `log_path` writes a structured markdown trace to disk via
`AgentLogger`. This example parses those trace files back out and reports per-run steps,
tool-call frequency, error rates, and aggregate stats across every log in a directory — as
plain dicts, so any renderer (a CLI table, a dataframe here) can present the same numbers.

```mermaid
flowchart LR
    A[Agent runs with log_path set] --> L["AgentLogger writes a markdown trace per run"]
    L --> C["collect_stats() parses every trace in the log directory"]
    C --> S[Steps, tool frequency, error rate, aggregates]
    S --> R[Rendered as tables — CLI or Streamlit]
```

**Key insight**

Agents are non-deterministic — the same prompt can take a different path on every run. Post-hoc
log analysis is the cheapest observability you can add on top of that: structured logs you can
grep and aggregate across many runs beat print statements you can only read once, in the
moment, on the one run you happened to be watching.
"""


relpath = "examples/05_evaluation_and_monitoring/01_log_analyzer.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod, about_extra=about_from(CORE_CONCEPT))

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
