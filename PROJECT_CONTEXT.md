# agentic-cookbook Project Context

This document serves as the primary source of truth for the motivation, architecture, and learning roadmap of the `agentic-cookbook` project. It is intended for both human contributors and AI assistants.

---

## Motivation

The core goal of `agentic-cookbook` is to **demystify agentic architectures by building up from first principles**.

In an era of increasingly complex frameworks like LangChain, AutoGPT, and CrewAI, this project takes a step back. Inspired by the lean approaches of **Claude Code** and **Open Claw** (a Python reimplementation of Claude Code), `agentic-cookbook` provides barebones implementations of the patterns that underpin real production agents — making the "thinking" process fully visible and controllable.

### Why build this?

1. **Educational**: Understand exactly how tool-calling, memory management, and feedback loops interact without layers of abstraction.
2. **Prototyping**: A minimal but functional playground for testing new agentic concepts.
3. **Foundation for Open Claw**: Every pattern in this cookbook is a building block toward a full coding agent like [Open Claw](research/claw-code-agent/README.md) — a Python reimplementation of the Claude Code agent architecture.

---

## The North Star: Open Claw

The ultimate goal of this cookbook is to give you the foundational knowledge to understand and contribute to **Open Claw** (`research/claw-code-agent/`), a Python reimplementation of the Claude Code npm agent that:

- Runs a full agentic coding loop with tool calling and iterative reasoning
- Manages tiered memory (short-term context, markdown files, hybrid search index)
- Enforces a permission system (read-only → write → shell → unsafe)
- Supports nested agent delegation with dependency-aware topological batching
- Handles context compaction, token budgeting, and session persistence
- Is extensible via a manifest-based plugin system and MCP (Model Context Protocol)

Every concept introduced in this cookbook maps directly to a subsystem in Open Claw.

---

## Concept Ladder

Learn these concepts in order. Each level is a prerequisite for the next.

### Level 1: Primitives

**1. Tool Use / Function Calling**
The mechanism by which a model emits a structured request to call an external function, then receives the result back as an observation. This is the foundation of all agentic behavior — without it, the model can only generate text.

- Key idea: the model does not _execute_ tools; it _requests_ them. Your loop executes them.
- In this project: `core/registry.py` auto-generates JSON schemas from Python type hints.
- In Open Claw: `agent_tools.py` — all tools inherit from a common base with an OpenAI-compatible schema.

**2. The Context Window as Working Memory**
Everything the agent "knows" at any moment is what fits in the context window. This is the agent's only working memory during a run. If something is not in the context, the agent cannot reason about it.

- Key idea: context is finite and expensive. Managing it is not optional.
- In Open Claw: `compact.py`, `token_budget.py`, `agent_context.py`.

**3. The Stop Condition Problem**
How does an agent know it is done? Without a clear termination signal, agents loop indefinitely or stop prematurely. Every agent loop needs an explicit stop condition: a `max_steps` guard, a terminal tool call, or a model-emitted signal.

- In this project: `Agent.run()` in `core/agent.py` uses `max_steps`.
- In Open Claw: turn limits, cost budgets, and tool-call caps all enforce stopping.

---

### Level 2: Core Loop Patterns

**4. ReAct (Reason + Act)**
The foundational loop: Thought → Tool Call → Observation → Thought. The model reasons about what to do, acts via a tool, observes the result, and repeats.

- Failure mode: loses track in long tasks as context fills with old observations ("forgetfulness").
- Example: `examples/01_agent_patterns/01_react_basic.py`

**5. Plan-and-Execute**
Separates the planning step from execution. A Planner agent produces a global plan; an Executor agent works through it step-by-step and re-plans when the world diverges from expectations.

- Failure mode: rigid plans break on unexpected observations; re-planning adds latency.
- Solves: the "forgetfulness" problem of pure ReAct on long-horizon tasks.
- Example: `examples/01_agent_patterns/02_plan_and_execute.py`
- In Open Claw: `plan_runtime.py`, `task_runtime.py`.

**6. Reflexion (Self-Correction)**
Adds a self-critique phase: Generate → Critique → Revise → Output. The agent reviews its own output before finalizing it, mimicking a human "draft and edit" process.

- Failure mode: diminishing returns after 2-3 reflection cycles; can over-correct or oscillate.
- Solves: low-quality first-pass outputs in high-precision tasks (code, structured data).
- Example: `examples/01_agent_patterns/03_reflexion.py`

---

### Level 3: Memory Management

**7. Short-Term Memory (Context Window)**
The active conversation transcript. Every message, tool call, and observation lives here. It is fast but bounded.

- Strategies: prune old messages, summarize intermediate steps, compact verbose tool outputs.
- In Open Claw: auto-snip (remove old messages at a threshold), auto-compact (compress history), reactive compaction (retry on "prompt too long" errors).

**8. Intermediate Memory (Persistent Files)**
Durable facts written to markdown files in the workspace. Survives session restarts. Human-readable and version-controllable via git.

- In Open Claw: `MEMORY.md` (global project context), daily journal files (session discoveries), `CLAUDE.md` (workspace instructions injected into every system prompt).

**9. Long-Term Memory (Archival / Retrieval)**
A searchable index of past conversations and documentation. Retrieved on demand via hybrid search (vector similarity + BM25 keyword matching) without flooding the context window.

- In Open Claw: `history.py`, the hybrid search backend.
- Key idea: retrieval-augmented memory decouples _storage_ from _context usage_.

---

### Level 4: Tool Use Patterns

**10. Tiered Permissions**
A "safe by default" philosophy: tools that read are always available; tools that write, execute shell commands, or perform destructive operations require explicit opt-in.

- In Open Claw: Read → Write (`--allow-write`) → Shell (`--allow-shell`) → Unsafe (`--unsafe`).
- Key idea: the permission tier is a trust boundary, not just a capability boundary.

**11. Parallel Tool Calling**
When a model needs multiple independent pieces of information, it can emit several tool calls in one turn. The loop executes them in parallel and returns all results before the next reasoning step.

- Reduces latency for independent sub-tasks dramatically.
- Example: `examples/04_tool_use_patterns/`

**12. Tool Error Recovery**
Tools fail. A robust agent loop must handle tool errors gracefully: surface the error as an observation, let the model reason about it, and retry or pivot — without crashing the loop.

- In Open Claw: reactive compaction on "prompt too long", continuation on `finish_reason=length`.

---

### Level 5: Multi-Agent Systems

**13. Orchestrator / Worker Pattern**
The orchestrator agent decomposes a task and delegates sub-tasks to specialized worker agents. Workers have narrower context, focused tools, and return summaries to the orchestrator.

- In Open Claw: the `delegate_agent` tool, `agent_manager.py` with lineage tracking, topological batching for dependency-aware execution.

**14. Agent Communication Protocols**
How agents hand off work. Key concerns: what context to pass (full vs. summary), how to aggregate results, and how to handle partial failures in a multi-agent run.

- Example: `examples/03_multi_agent_systems/`

**15. Worktree / Isolated Execution**
For tasks that require file system mutations (code edits, refactors), agents can run inside an isolated git worktree. The worktree is cleaned up if no changes are made, and the branch is returned to the orchestrator on success. This decouples experimentation from the main workspace.

- In Open Claw: `worktree_runtime.py`.

**16. Workflow and Background Agents**
Long-running or asynchronous work can be handed off to background agents that execute outside the main turn loop. Remote triggers allow external systems (webhooks, schedulers) to wake an agent and resume work.

- In Open Claw: `workflow_runtime.py`, `background_runtime.py`, `remote_runtime.py`, `remote_trigger_runtime.py`.

**17. Session Persistence**
Agents can serialize their full state (context, tool history, metadata) to disk and resume a previous session. This is essential for long-horizon tasks that span multiple user interactions or restarts.

- In Open Claw: `session_store.py`, `agent_session.py`.

---

### Level 6: Observability and Evaluation

**18. Tracing and Structured Logging**
Agents are non-deterministic. The only way to debug them is to capture every step: the reasoning trace, each tool call with its inputs and outputs, token counts, and wall-clock time.

- In this project: `core/logger.py`, structured markdown logs in `examples/logs/`.
- In Open Claw: `transcript.py`, `query_engine.py`, `cost_tracker.py`.

**19. Evaluation**
How do you know if your agent is working correctly? Unlike deterministic functions, agents require task-level evaluation: did the agent complete the goal? How many steps did it take? What was the cost?

- Example: `examples/05_evaluation_and_monitoring/`

---

### Level 7: Extensibility

**20. MCP (Model Context Protocol)**
A standard protocol for exposing tools and resources to agents via a server/client interface. Allows third-party tools to be integrated without modifying the agent core.

- In Open Claw: `mcp_runtime.py`, real stdio MCP transport.

**21. Plugin System and Hook Policy**
Manifest-based plugins inject logic at specific lifecycle points: before the system prompt is assembled, after each turn, before session persistence, before delegation. Separate from plugins, a *hook policy* layer governs each tool call: it can allow, deny, or prompt the user for permission before the tool executes — this is the primary mechanism for the permission tier system.

- In Open Claw: `plugin_runtime.py`, lifecycle hooks (`beforePrompt`, `afterTurn`, `onResume`, `beforePersist`); `hook_policy.py` for per-tool allow/deny/ask decisions.

---

## Architectural Rationale

The project is built around four core components:

### 1. Agent Loop (`core/agent.py`)

A sequential **Think-Act-Observe** (ReAct) cycle. We use a simple loop rather than a complex state machine to keep the execution flow predictable and debuggable. Corresponds to `agent_runtime.py` in Open Claw.

### 2. Tool Registry (`core/registry.py`)

Dynamic JSON schema generation from Python type hints and docstrings. **Configuration over boilerplate** — if you can write a Python function, you can write a tool. Corresponds to `agent_tools.py` in Open Claw.

### 3. Model Abstraction (`core/model.py`)

Multi-provider support via **LiteLLM**. **Provider agnosticism** — swap between OpenAI, Anthropic, or local models (Ollama, vLLM) with a single config change. Open Claw targets any OpenAI-compatible API directly.

### 4. Memory (`core/memory.py`)

Simple list-based message history in the standard `[{"role": "...", "content": "..."}]` format. Compatible with virtually all modern LLM APIs. The foundation for the tiered memory system in Open Claw.

---

## Design Principles

- **Minimize Abstractions**: If a plain dictionary or list works, use it. Do not wrap data in classes unless they provide functional utility.
- **Inversion of Control**: Tools are registered _to_ the agent, not built _into_ it.
- **Visible Internals**: Use structured logging and rich output to keep every step of the agent's reasoning inspectable.
- **Safe by Default**: Destructive capabilities require explicit opt-in. Read-only is always the default.

---

## Learning Roadmap

Work through the examples in this order. Each directory builds on the previous.

| Step | Directory                                | Concept                                                     |
| :--- | :--------------------------------------- | :---------------------------------------------------------- |
| 1    | `examples/01_agent_patterns/`            | Core loop architectures: ReAct, Plan-and-Execute, Reflexion |
| 2    | `examples/02_memory_management/`         | Short-term, intermediate, and long-term memory strategies   |
| 3    | `examples/03_multi_agent_systems/`       | Orchestrator/worker, nested delegation, handoff protocols   |
| 4    | `examples/04_tool_use_patterns/`         | Parallel tools, error recovery, tiered permissions          |
| 5    | `examples/05_evaluation_and_monitoring/` | Tracing, structured logging, task-level evaluation          |
| 6    | `research/claw-code-agent/`              | Full production agent — all of the above, integrated        |

---

## Cookbook → Open Claw Architecture Map

| Concept               | This Cookbook                  | Open Claw                                                       |
| :-------------------- | :----------------------------- | :-------------------------------------------------------------- |
| Agent loop            | `core/agent.py`                | `agent_runtime.py`                                              |
| Tool registry         | `core/registry.py`             | `agent_tools.py`                                                |
| System tools          | `tools/system_tools.py`        | `tools.py`                                                      |
| Model abstraction     | `core/model.py` (LiteLLM)     | `openai_compat.py` (OpenAI-compatible)                          |
| Short-term memory     | `core/memory.py`               | `compact.py`, `token_budget.py`                                 |
| Windowed memory       | `examples/02_memory_management/01_windowed_memory.py` | `compact.py` (auto-snip)              |
| Intermediate memory   | —                              | `MEMORY.md`, journal files                                      |
| Long-term memory      | —                              | `history.py` (hybrid search)                                    |
| Permissions           | —                              | `permissions.py`                                                |
| Hook policy           | —                              | `hook_policy.py`                                                |
| Multi-agent           | —                              | `agent_manager.py`, `delegate_agent` tool                       |
| Worktree isolation    | —                              | `worktree_runtime.py`                                           |
| Workflow / background | —                              | `workflow_runtime.py`, `background_runtime.py`                  |
| Remote agents         | —                              | `remote_runtime.py`, `remote_trigger_runtime.py`                |
| Session persistence   | —                              | `session_store.py`, `agent_session.py`                          |
| Observability         | `core/logger.py`               | `transcript.py`, `query_engine.py`, `cost_tracker.py`           |
| Plugins / MCP         | —                              | `plugin_runtime.py`, `mcp_runtime.py`                           |

---

## Contributing

> **Minimalist first.** Before adding a dependency or a complex design pattern, ask: "Can this be done with a standard Python list or function?"

### Documentation Standards

- **Relative Paths Only**: Never use absolute local file paths (e.g., `/Users/...`) in documentation or links.
- **Link Integrity**: Test all relative links before committing.

### Adding New Features

- **Tools**: Define in `tools/` as standard Python functions; register in `main.py`.
- **Model Features**: Update `ModelProvider` without breaking the core generation interface.
- **Agent Logic**: Keep "Step" output in `Agent.run` clean and informative.

### Roadmap

- [x] `examples/02_memory_management/01_windowed_memory.py` — sliding window context management
- [ ] `examples/02_memory_management/` — context summarization, markdown persistence
- [ ] `examples/03_multi_agent_systems/` — orchestrator/worker, `delegate_agent`
- [ ] `examples/04_tool_use_patterns/` — parallel tools, error recovery
- [ ] `examples/05_evaluation_and_monitoring/` — structured evals, cost tracking
- [x] Terminal access tool (`tools/system_tools.py` — `execute_command`)
- [x] File system tools (`tools/system_tools.py` — `list_files`, `read_file`)
- [ ] Session persistence (save and resume agent runs)
- [ ] Context compaction (auto-snip and auto-compact)

---

_Created: 2026-04-12 | Updated: 2026-04-27_
