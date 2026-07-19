# 06 Frameworks

This section bridges the cookbook's from-scratch examples with real-world
production frameworks. After building each primitive by hand in `00–05`,
reading a framework becomes straightforward: you recognize every pattern and
can evaluate the trade-offs the framework author made.

---

## Available Frameworks

| Framework | Source | Guide |
|---|---|---|
| **pi-agent / pi-mono** | https://github.com/badlogic/pi-mono | `pi_agent/README.md` |

---

## How to Use This Section

1. **Do not start here.** Complete `00_primitives` through `05_evaluation_and_monitoring` first.
2. Read the framework guide — it maps each framework concept back to the cookbook example it mirrors.
3. Clone the framework source into `research/` and read the annotated files listed in the guide.
4. Build something: port one of your cookbook examples to use the framework's primitives and observe what the framework simplifies vs. constrains.

---

## Why Frameworks?

Frameworks exist because the same patterns keep appearing:

| Pattern | Cookbook | Framework |
|---|---|---|
| LLM abstraction | `core/model.py` | pi-ai |
| Agent loop | `core/agent.py` | pi-agent-core |
| Tool registry | `core/registry.py` | pi-agent-core `Tool[]` |
| HIL approval | `04_tool_use_patterns/01_human_approval.py` | pi-coding-agent permission tiers |
| Parallel tool calls | `04_tool_use_patterns/02_parallel_tool_calls.py` | pi-agent-core `Promise.all()` |
| Plugin discovery | `04_tool_use_patterns/04_dynamic_tools.py` | pi-coding-agent Pi Packages |
| Async multi-agent | `03_multi_agent_systems/04_async_announce.py` | openclaw `subagent-announce.ts` |
| LLM judge | `05_evaluation_and_monitoring/03_llm_judge.py` | evals-as-a-service (external) |

The value of building from scratch first is that you understand *why* each
abstraction exists — you felt the pain the framework is solving.
