# agentic-cookbook Project Context

This document serves as the primary source of truth for the motivation, architecture, and learning roadmap of the `agentic-cookbook` project. It is intended for both human contributors and AI assistants.

---

## Motivation

The core goal of `agentic-cookbook` is to **demystify agentic architectures by building up from first principles**.

In an era of increasingly complex frameworks like LangChain, AutoGPT, and CrewAI, this project takes a step back. Inspired by the lean, readable cores of **Claude Code**, **OpenClaw** (TypeScript, full-stack production agent), and **Nanobot** (Python, lightweight reference implementation), `agentic-cookbook` provides barebones implementations of the patterns that underpin real production agents — making the "thinking" process fully visible and controllable.

### Why build this?

1. **Educational**: Understand exactly how tool-calling, memory management, and feedback loops interact without layers of abstraction.
2. **Prototyping**: A minimal but functional playground for testing new agentic concepts.
3. **Foundation for reading production agents**: Every pattern in this cookbook is a building block toward understanding real systems like [OpenClaw](research/openclaw/) and [Nanobot](research/nanobot/).

---

## The North Stars: OpenClaw and Nanobot

The reference repositories in `research/` are the production targets this cookbook builds toward. Study them together — Nanobot for its readable Python core, OpenClaw for its full-scale TypeScript architecture.

**Nanobot** (`research/nanobot/`) — lightweight Python agent that keeps the core small while supporting channels, memory, MCP, and deployment:
- Async ReAct loop with per-session concurrency (Lock + Semaphore + pending queue)
- Multi-stage context governance pipeline (orphan cleanup → microcompact → budgeting → snip → compact)
- Three-tier memory: `MemoryStore` (file I/O) + `Consolidator` (reactive token-budget summarization) + `Dream` (proactive two-phase background processor with git commits)
- Skills as SKILL.md prompt modules; message bus decoupling channels from the agent loop

**OpenClaw** (`research/openclaw/`) — TypeScript production agent with full platform support:
- Streaming-first design: every text delta, tool event, and lifecycle phase flows through a subscriber chain
- Manifest-first plugin SDK with strict core/extension boundary enforcement
- Multi-stage tool policy pipeline (allowlist → workspace guard → sandbox → approval)
- Subagent registry with depth limits, lineage tracking, and async announce-based result delivery

Every concept in this cookbook maps directly to a subsystem in one or both of these systems.

---

## Concept Ladder

Learn these concepts in order. Each level is a prerequisite for the next.

### Level 1: Primitives

**1. Tool Use / Function Calling**
The mechanism by which a model emits a structured request to call an external function, then receives the result back as an observation. This is the foundation of all agentic behavior — without it, the model can only generate text.

- Key idea: the model does not _execute_ tools; it _requests_ them. Your loop executes them.
- In this project: `core/registry.py` auto-generates JSON schemas from Python type hints.
- In OpenClaw: `src/agents/pi-tools.ts` — tools have schemas and a policy pipeline. In Nanobot: `nanobot/agent/tools/base.py` — Tool ABC with JSON Schema parameters.

**2. The Context Window as Working Memory**
Everything the agent "knows" at any moment is what fits in the context window. This is the agent's only working memory during a run. If something is not in the context, the agent cannot reason about it.

- Key idea: context is finite and expensive. Managing it is not optional.
- In OpenClaw: `src/agents/compaction.ts`, `src/context-engine/`. In Nanobot: `nanobot/agent/autocompact.py`, `nanobot/agent/runner.py` (context governance stages).

**3. The Stop Condition Problem**
How does an agent know it is done? Without a clear termination signal, agents loop indefinitely or stop prematurely. Every agent loop needs an explicit stop condition: a `max_steps` guard, a terminal tool call, or a model-emitted signal.

- In this project: `Agent.run()` in `core/agent.py` uses `max_steps`.
- In OpenClaw: turn limits and tool-call caps. In Nanobot: `AgentRunner.max_iterations` plus `stop_reason` signals (`completed`, `max_iterations`, `error`, `ask_user`).

**4. Streaming-First Design**
Both OpenClaw and Nanobot treat token-by-token streaming as a first-class architectural concern, not an afterthought. The agent loop dispatches tool calls as soon as the model finishes emitting them — before the full response is complete — and propagates text deltas to the UI in real time.

- Key idea: designing for streaming changes your data flow: you need incremental parsers, partial-reply routing, and stream-end signals (`resuming=True` means tools follow; `resuming=False` means the turn is done).
- Failure mode if ignored: buffering entire responses before acting adds latency proportional to output length; UIs feel unresponsive.
- In OpenClaw: `src/agents/pi-embedded-subscribe.ts` — subscriber chain for text deltas, tool events, and lifecycle phases. In Nanobot: `AgentHook.on_stream` / `on_stream_end`, `_wants_stream` metadata flag.

---

### Level 2: Core Loop Patterns

**5. ReAct (Reason + Act)**
The foundational loop: Thought → Tool Call → Observation → Thought. The model reasons about what to do, acts via a tool, observes the result, and repeats.

- Failure mode: loses track in long tasks as context fills with old observations ("forgetfulness").
- Example: `examples/01_agent_patterns/01_react_basic.py`
- In OpenClaw: `src/agents/pi-embedded-subscribe.ts` tool dispatch. In Nanobot: `nanobot/agent/runner.py` `AgentRunner.run()`.

**6. Plan-and-Execute**
Separates the planning step from execution. A Planner agent produces a global plan; an Executor agent works through it step-by-step and re-plans when the world diverges from expectations.

- Failure mode: rigid plans break on unexpected observations; re-planning adds latency.
- Solves: the "forgetfulness" problem of pure ReAct on long-horizon tasks.
- In production: often implemented via sub-agent delegation rather than a separate planner class — the orchestrator delegates plan steps to worker agents.
- Example: `examples/01_agent_patterns/02_plan_and_execute.py`
- In OpenClaw: `src/agents/runtime-plan/`.

**7. Reflexion (Self-Correction)**
Adds a self-critique phase: Generate → Critique → Revise → Output. The agent reviews its own output before finalizing it, mimicking a human "draft and edit" process.

- Failure mode: diminishing returns after 2–3 reflection cycles; can over-correct or oscillate.
- Solves: low-quality first-pass outputs in high-precision tasks (code, structured data).
- **Research note**: Neither OpenClaw nor Nanobot implements Reflexion as a named production subsystem. Both prefer error recovery and tool retry loops over an explicit critique-and-revise cycle. Reflexion is worth understanding as a conceptual pattern but expect to encounter it more in research agents than in deployed systems.
- Example: `examples/01_agent_patterns/03_reflexion.py`

---

### Level 3: Memory Management

**8. Context Governance Pipeline**
The active conversation transcript is the agent's working memory, but keeping it within budget requires more than a single "prune old messages" step. Production agents run a multi-stage pipeline before every model call:

1. **Orphan cleanup** — drop tool results that have no matching tool call (can happen after cancellation).
2. **Microcompact** — compress recent repetitive tool calls (e.g., 10 identical `read_file` results compressed to a summary).
3. **Tool result budgeting** — truncate individual tool outputs that exceed a per-result character cap.
4. **Snipping** — drop oldest messages when the total token count approaches the soft limit (free, but lossy).
5. **Full compaction** — summarize evicted history via an LLM call before discarding (costly but preserves semantic content).

- Key idea: each stage has a different cost/benefit profile. Apply cheaper stages first; reserve the LLM call for when cheaper options are exhausted.
- In OpenClaw: `src/agents/compaction.ts` (identifier-preservation during summaries). In Nanobot: `nanobot/agent/runner.py` (`_drop_orphan_tool_results`, `_microcompact`, `_apply_tool_result_budget`, `_snip_history`) and `nanobot/agent/autocompact.py` (TTL-based session compaction).

**9. Intermediate Memory (Persistent Files)**
Durable facts written to markdown files in the workspace. Survives session restarts. Human-readable and version-controllable via git. Injected into the system prompt at the start of every turn.

- In OpenClaw: `CLAUDE.md` files discovered by walking the directory tree upward; injected via `src/agents/system-prompt.ts`. In Nanobot: `MEMORY.md`, `USER.md`, `SOUL.md` injected via `nanobot/agent/context.py`.
- Key idea: the injection point matters. Facts in persistent files are always present; facts in conversation history are subject to compaction.

**10. Skills and Prompt Modules**
Reusable, domain-specific prompt fragments stored as manifest files (e.g., `SKILL.md`) and injected into the system prompt on demand. Skills sit between ephemeral context and always-on persistent files: they are stable enough to live in files but narrow enough that injecting all of them at once would pollute the context.

- Key idea: a skill is not a tool (no code executes) and not a fact (it is procedural guidance, not a datum). It tells the agent *how* to behave in a specific domain — "when working with GitHub PRs, always…".
- In OpenClaw: `src/agents/skills/` — YAML-fronted markdown, filtered at runtime by relevance. In Nanobot: `nanobot/skills/` — `SKILL.md` manifests; Dream can auto-create new skills from patterns in conversation history.
- Failure mode: too many skills injected unconditionally → context bloat; too few → the agent lacks domain guidance and invents its own (often wrong) conventions.

**11. Memory Consolidation Pipeline**
Long-running agents accumulate more conversation history than fits in any context window. The consolidation pipeline translates old conversation turns into durable summary records that survive compaction.

- **Reactive consolidation** (Consolidator): triggered by token pressure. Picks a user-turn boundary, summarizes the old chunk via LLM, appends the summary to a structured append-only log (`history.jsonl`), and advances a cursor so the same messages are never re-summarized. Falls back to raw-archiving if the LLM call fails.
- **Proactive consolidation** (Dream): runs on a cron schedule, independent of conversation pressure. Two phases: (1) a plain LLM call analyzes recent history entries against current memory files and produces an edit plan; (2) an `AgentRunner` with `read_file`/`edit_file` tools applies surgical, incremental edits to `MEMORY.md`, `USER.md`, `SOUL.md`, and the skills directory. Changes are git-committed automatically, making memory evolution auditable.
- Key idea: consolidation decouples *when* something is learned from *when* the context window forces a decision. The Dream processor can take minutes; the Consolidator must be fast.
- In Nanobot: `nanobot/agent/memory.py` — `Consolidator`, `Dream`, `MemoryStore`. In OpenClaw: `src/agents/memory-search.ts` (retrieval layer for consolidated history).

---

### Level 4: Tool Use Patterns

**12. Tool Policy Pipeline**
Enforcing safe tool execution is not a single flag — it is a pipeline of decisions applied in sequence before any tool runs:

1. **Allowlist/denylist match** — does the agent's current config permit this tool?
2. **Workspace path guard** — does the tool's target path stay within the allowed directory?
3. **Sandbox enforcement** — if a container sandbox is configured, does the path resolve inside it?
4. **Interactive approval** — in "confirm" mode, pause and ask the user before executing.

- Key idea: each stage can independently block execution. The first blocking stage wins; later stages are not reached.
- In OpenClaw: `src/agents/tool-policy-pipeline.ts`, `src/agents/sandbox-tool-policy.ts`, `src/agents/bash-tools.exec-approval-request.ts`. In Nanobot: config-gated enable flags (`exec_config.enable`, `restrict_to_workspace`, `exec_config.sandbox`).

**13. Parallel Tool Calling**
When a model needs multiple independent pieces of information, it can emit several tool calls in one turn. The loop executes them in parallel and returns all results before the next reasoning step.

- Reduces latency for independent sub-tasks dramatically.
- Example: `examples/04_tool_use_patterns/`
- In Nanobot: `concurrent_tools=True` in `AgentRunner`. In OpenClaw: parallel execution in the tool dispatch layer of `src/agents/pi-embedded-subscribe.ts`.

**14. Tool Error Recovery**
Tools fail. A robust agent loop must handle tool errors gracefully: surface the error as an observation, let the model reason about it, and retry or pivot — without crashing the loop.

- In OpenClaw: compaction retry on context overflow, continuation on `finish_reason=length`. In Nanobot: `AgentRunner` provider retry with exponential backoff, `_restore_runtime_checkpoint()` for crash recovery across process restarts.

---

### Level 5: Multi-Agent Systems

**15. Orchestrator / Worker Pattern**
The orchestrator agent decomposes a task and delegates sub-tasks to specialized worker agents. Workers have narrower context, focused tools, and return summaries to the orchestrator.

- In OpenClaw: `sessions_spawn` tool + subagent registry (`src/agents/subagent-registry.ts`) with depth limits and lineage tracking. In Nanobot: `SpawnTool` + `SubagentManager` (`nanobot/agent/subagent.py`).

**16. Message Bus / Event-Driven Architecture**
In multi-channel agents, the agent loop must be decoupled from the message source. A message bus (async pub/sub queue) sits between channels and the agent: channels publish `InboundMessage` objects; the agent loop consumes them; responses are `OutboundMessage` objects routed back through the bus.

- Key idea: the agent loop never imports Telegram, Discord, or Slack. It only sees `InboundMessage`. Adding a new channel means writing a new publisher, not touching the agent.
- Why it matters: enables per-session serial processing (one lock per session key), cross-session concurrency (a Semaphore caps total concurrent LLM calls), and background task delivery (sub-agent results re-enter the bus as system messages).
- In Nanobot: `nanobot/bus/` — `MessageBus`, `InboundMessage`, `OutboundMessage`. In OpenClaw: the gateway RPC layer routes messages to agent sessions by `session_key`.

**17. Per-Session Concurrency Model**
Multi-user agents must process messages for the same user in order while handling different users concurrently. The standard pattern: a `Lock` per session key serializes turns within a session; a global `Semaphore` caps total simultaneous LLM calls across all sessions; a `pending_queue` per session buffers messages that arrive while a turn is in progress, enabling mid-turn injection rather than spawning a competing task.

- Key idea: without per-session locking, a rapid second message can start a new turn before the first turn's results are persisted, producing a corrupted session.
- Failure mode if using a global lock: all users queue behind the slowest session.
- In Nanobot: `nanobot/agent/loop.py` — `asyncio.Lock` per `session_key`, `asyncio.Semaphore` global gate, `asyncio.Queue` per session for pending messages.

**18. Async Agent Communication (Announce Pattern)**
In synchronous sub-agent models, the parent blocks until the child returns. In the async announce pattern, sub-agents complete independently and "announce" their results by publishing a message back into the bus — which the parent's session picks up as a normal user turn. The parent never blocks; it can process other sessions or other sub-agents in the meantime.

- Key idea: the announce pattern decouples spawner and worker in time. A sub-agent can take minutes; the parent's turn has already ended and its context has been persisted.
- Trade-off: results arrive out of order if multiple sub-agents are running. The parent must be designed to handle partial results arriving as separate turns.
- In OpenClaw: `src/agents/subagent-announce.ts` — results delivered as messages to the parent session. In Nanobot: sub-agent publishes result as a `system` channel `InboundMessage`; parent's loop processes it on the next cycle.
- Example: `examples/03_multi_agent_systems/`

**19. Session Persistence and Crash Recovery**
Agents must survive process restarts without losing in-progress work. This requires three layers beyond simple "serialize to disk":

1. **Early persist** — write the user's incoming message to the session file *before* calling the LLM. If the process crashes mid-turn, the message is not lost.
2. **Runtime checkpoint** — after each tool execution completes, write the in-flight state (assistant message, completed tool results, pending tool calls) to session metadata. If the process is killed mid-tool, the partial progress survives.
3. **Restore on resume** — when the next message arrives for a session, check for a checkpoint and replay it into the session history before building the new prompt. Pending tool calls become error results ("interrupted before completion").

- In Nanobot: `nanobot/agent/loop.py` — `_mark_pending_user_turn`, `_set_runtime_checkpoint`, `_restore_runtime_checkpoint`, `_restore_pending_user_turn`. In OpenClaw: session write-lock (`src/agents/session-write-lock.ts`), session file repair (`src/agents/session-file-repair.ts`).

**20. Worktree / Isolated Execution**
For tasks that require file system mutations (code edits, refactors), agents can run inside an isolated git worktree. The worktree is cleaned up if no changes are made, and the branch is returned to the orchestrator on success. This decouples experimentation from the main workspace.

- Most relevant for coding agents. Non-coding agents typically use workspace path restrictions instead (Nanobot's `restrict_to_workspace` flag).
- In OpenClaw: `src/agents/tools/sessions-spawn-tool.ts` with workspace isolation.

**21. Workflow and Background Agents**
Long-running or asynchronous work can be handed off to background agents that execute outside the main turn loop. Cron-scheduled agents handle periodic tasks (daily memory consolidation, scheduled reports). Remote triggers allow external systems (webhooks, schedulers) to wake an agent and resume work.

- In OpenClaw: `src/agents/cron/`, channel-level cron tools. In Nanobot: `nanobot/cron/` — `CronService`, `CronTool`; Dream processor runs as a cron job.

---

### Level 6: Observability and Evaluation

**22. Tracing and Structured Logging**
Agents are non-deterministic. The only way to debug them is to capture every step: the reasoning trace, each tool call with its inputs and outputs, token counts, and wall-clock time.

- In this project: `core/logger.py`, structured markdown logs in `examples/logs/`.
- In OpenClaw: `src/agents/anthropic-payload-log.ts`, `src/agents/cache-trace.ts`. In Nanobot: `loguru` structured logs, tool events emitted via `AgentHookContext`.

**23. Evaluation**
How do you know if your agent is working correctly? Unlike deterministic functions, agents require task-level evaluation: did the agent complete the goal? How many steps did it take? What was the cost?

- Example: `examples/05_evaluation_and_monitoring/`

---

### Level 7: Extensibility

**24. MCP (Model Context Protocol)**
A standard protocol for exposing tools and resources to agents via a server/client interface. Allows third-party tools to be integrated without modifying the agent core.

- In OpenClaw: `src/mcp/` — stdio and SSE transport; OpenClaw can act as both MCP client and MCP server. In Nanobot: `nanobot/agent/tools/mcp.py` — stdio transport, multiple servers, full MCP v1.0 compliance.

**25. Plugin System and Hook Policy**
Manifest-based plugins inject logic at specific lifecycle points: before the system prompt is assembled, after each turn, before session persistence, before delegation. Separate from plugins, a *hook policy* layer governs each tool call: it can allow, deny, or prompt the user for permission before the tool executes — this is the primary mechanism for the permission tier system.

- **Core boundary rule**: core must stay extension-agnostic. Extensions cross into core only via a published SDK (`openclaw/plugin-sdk/*` or `AgentHook`). No extension IDs, dependency strings, or recovery logic in core.
- In OpenClaw: `src/plugin-sdk/`, lifecycle hooks (`beforePrompt`, `afterTurn`, `onResume`, `beforePersist`), `src/agents/tool-policy-pipeline.ts`. In Nanobot: `nanobot/agent/hook.py` — `AgentHook`, `CompositeHook`; SKILL.md manifests as the lightweight plugin primitive.

---

## Architectural Rationale

The project is built around four core components:

### 1. Agent Loop (`core/agent.py`)

A sequential **Think-Act-Observe** (ReAct) cycle. We use a simple loop rather than a complex state machine to keep the execution flow predictable and debuggable. Corresponds to `AgentLoop` in Nanobot and `pi-embedded-runner.ts` in OpenClaw.

### 2. Tool Registry (`core/registry.py`)

Dynamic JSON schema generation from Python type hints and docstrings. **Configuration over boilerplate** — if you can write a Python function, you can write a tool. Corresponds to `nanobot/agent/tools/registry.py` in Nanobot and `src/agents/pi-tools.ts` in OpenClaw.

### 3. Model Abstraction (`core/model.py`)

Multi-provider support via **LiteLLM**. **Provider agnosticism** — swap between OpenAI, Anthropic, or local models (Ollama, vLLM) with a single config change. Corresponds to `nanobot/providers/` in Nanobot (30+ providers) and `src/agents/provider-transport-stream.ts` in OpenClaw.

### 4. Memory (`core/memory.py`)

Simple list-based message history in the standard `[{"role": "...", "content": "..."}]` format. Compatible with virtually all modern LLM APIs. The starting point for the multi-tier memory system in Nanobot (`MemoryStore`, `Consolidator`, `Dream`) and the context engine in OpenClaw.

---

## Design Principles

- **Minimize Abstractions**: If a plain dictionary or list works, use it. Do not wrap data in classes unless they provide functional utility.
- **Inversion of Control**: Tools are registered _to_ the agent, not built _into_ it.
- **Visible Internals**: Use structured logging and rich output to keep every step of the agent's reasoning inspectable.
- **Safe by Default**: Destructive capabilities require explicit opt-in. Read-only is always the default.

---

## Learning Roadmap

Work through the examples in this order. Each directory builds on the previous.

| Step | Directory                                | Concept                                                                   |
| :--- | :--------------------------------------- | :------------------------------------------------------------------------ |
| 1    | `examples/01_agent_patterns/`            | Core loop architectures: ReAct, Plan-and-Execute, Reflexion               |
| 2    | `examples/02_memory_management/`         | Context governance, intermediate memory, skills, consolidation pipelines  |
| 3    | `examples/03_multi_agent_systems/`       | Orchestrator/worker, message bus, async announce, per-session concurrency |
| 4    | `examples/04_tool_use_patterns/`         | Parallel tools, tool policy pipeline, error recovery                      |
| 5    | `examples/05_evaluation_and_monitoring/` | Tracing, structured logging, task-level evaluation                        |
| 6    | `research/nanobot/`                      | Lightweight Python reference — all concepts integrated, readable core     |
| 7    | `research/openclaw/`                     | Full production agent — streaming-first, plugin SDK, subagent registry    |

---

## Cookbook → Reference Architecture Map

| Concept                    | This Cookbook                                         | OpenClaw (`research/openclaw/`)                                           | Nanobot (`research/nanobot/`)                                       |
| :------------------------- | :---------------------------------------------------- | :------------------------------------------------------------------------ | :------------------------------------------------------------------ |
| Agent loop                 | `core/agent.py`                                       | `src/agents/pi-embedded-runner.ts`                                        | `nanobot/agent/loop.py` — `AgentLoop`                               |
| Inner tool-calling loop    | `core/agent.py`                                       | `src/agents/pi-embedded-subscribe.ts`                                     | `nanobot/agent/runner.py` — `AgentRunner`                           |
| Tool registry              | `core/registry.py`                                    | `src/agents/pi-tools.ts`                                                  | `nanobot/agent/tools/registry.py`                                   |
| System tools               | `tools/system_tools.py`                               | `src/agents/bash-tools.ts`, `src/agents/tools/`                           | `nanobot/agent/tools/` (filesystem, exec, web, spawn…)              |
| Model abstraction          | `core/model.py` (LiteLLM)                             | `src/agents/provider-transport-stream.ts`                                 | `nanobot/providers/base.py`, `nanobot/providers/factory.py`         |
| Streaming                  | —                                                     | `src/agents/pi-embedded-subscribe.ts`                                     | `nanobot/agent/hook.py` — `AgentHook.on_stream`                     |
| Context governance         | `examples/00_primitives/02_context_window.py`         | `src/agents/compaction.ts`, `src/context-engine/`                         | `nanobot/agent/runner.py` (5-stage pipeline), `nanobot/agent/autocompact.py` |
| Intermediate memory        | `examples/02_memory_management/01_markdown_persistence.py` | `CLAUDE.md` via `src/agents/system-prompt.ts`                        | `MEMORY.md` / `USER.md` / `SOUL.md` via `nanobot/agent/context.py` |
| Skills / prompt modules    | —                                                     | `src/agents/skills/` — YAML-fronted markdown                              | `nanobot/skills/` — `SKILL.md` manifests; `nanobot/agent/skills.py` |
| Memory consolidation       | `examples/02_memory_management/02_hybrid_search.py`   | `src/agents/memory-search.ts`                                             | `nanobot/agent/memory.py` — `Consolidator`, `Dream`, `MemoryStore`  |
| Tool policy pipeline       | —                                                     | `src/agents/tool-policy-pipeline.ts`, `src/agents/sandbox-tool-policy.ts` | Config-gated flags + `restrict_to_workspace`                        |
| Parallel tool calling      | `examples/04_tool_use_patterns/`                      | `src/agents/pi-embedded-subscribe.ts` dispatch                            | `concurrent_tools=True` in `AgentRunner`                            |
| Message bus                | —                                                     | Gateway RPC session routing                                               | `nanobot/bus/` — `MessageBus`, `InboundMessage`, `OutboundMessage`  |
| Per-session concurrency    | —                                                     | Per-session queue in `pi-embedded-runner.ts`                              | `asyncio.Lock` + `asyncio.Semaphore` in `nanobot/agent/loop.py`     |
| Multi-agent / spawn        | `examples/03_multi_agent_systems/`                    | `src/agents/subagent-registry.ts`, `sessions_spawn` tool                  | `nanobot/agent/subagent.py` — `SubagentManager`, `SpawnTool`        |
| Async announce delivery    | —                                                     | `src/agents/subagent-announce.ts`                                         | System `InboundMessage` via `nanobot/bus/`                          |
| Session persistence        | —                                                     | `src/agents/session-write-lock.ts`, transcript JSONL                      | `nanobot/session/manager.py` — per-key JSONL                        |
| Crash recovery             | —                                                     | `src/agents/session-file-repair.ts`                                       | `_restore_runtime_checkpoint` in `nanobot/agent/loop.py`            |
| Worktree isolation         | —                                                     | `sessions_spawn` with workspace isolation                                 | `restrict_to_workspace` flag                                        |
| Background / cron agents   | —                                                     | `src/agents/cron/`                                                        | `nanobot/cron/` — `CronService`; Dream as cron job                  |
| Tracing / logging          | `core/logger.py`, `examples/logs/`                    | `src/agents/anthropic-payload-log.ts`, `cache-trace.ts`                   | `loguru` + `AgentHookContext` tool events                           |
| MCP                        | —                                                     | `src/mcp/` — client + server, stdio + SSE                                 | `nanobot/agent/tools/mcp.py` — stdio, MCP v1.0                      |
| Plugin system / hooks      | —                                                     | `src/plugin-sdk/`, `src/plugins/`, lifecycle hooks                        | `nanobot/agent/hook.py` — `AgentHook`, `CompositeHook`              |

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

- [x] `examples/00_primitives/` — tool use, context window, stop conditions
- [x] `examples/01_agent_patterns/` — ReAct, Plan-and-Execute, Reflexion
- [x] `examples/02_memory_management/01_markdown_persistence.py` — intermediate memory injection
- [x] `examples/02_memory_management/02_hybrid_search.py` — long-term retrieval pattern
- [x] Terminal access tool (`tools/system_tools.py` — `execute_command`)
- [x] File system tools (`tools/system_tools.py` — `list_files`, `read_file`)
- [ ] `examples/02_memory_management/` — context governance pipeline, skills, consolidation
- [ ] `examples/03_multi_agent_systems/` — orchestrator/worker, message bus, async announce
- [ ] `examples/04_tool_use_patterns/` — parallel tools, tool policy pipeline, error recovery
- [ ] `examples/05_evaluation_and_monitoring/` — structured evals, cost tracking
- [ ] Session persistence and crash recovery
- [ ] Streaming-first agent loop

---

_Created: 2026-04-12 | Updated: 2026-04-29_
