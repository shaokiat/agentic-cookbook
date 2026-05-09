# 03 Multi-Agent Systems

Coordinate multiple agents to solve problems that are too large or complex for a single agent. Each example isolates one coordination pattern so the tradeoffs are clear.

---

## Concept Ladder

| Level | Pattern | File |
| :---- | :------ | :--- |
| 1 | Orchestrator delegates to specialist workers via a tool | `01_orchestrator_worker.py` |
| 2 | Independent subtasks run concurrently; results aggregated | `02_parallel_subagents.py` |
| 3 | Specialized agents chained in sequence; each builds on the last | `03_sequential_pipeline.py` |
| 4 | Workers run in the background; results arrive asynchronously | `04_async_announce.py` |

---

## Examples

### `01_orchestrator_worker.py` — Orchestrator-Worker

An orchestrator agent has a `delegate_to_agent` tool. When it calls the tool, a fresh worker agent is created with a specific role, runs the subtask, and returns the result as a tool observation.

**Key insight**: tools can spawn agents. The orchestrator needs no special wiring — worker results arrive through the ordinary tool-observation channel.

```
Orchestrator (Agent)
    │
    └── calls delegate_to_agent(role="researcher", task="...")
              │
              ▼
        Worker Agent (fresh Memory, scoped role)
              │ runs and returns result
              ▼
    Tool observation → Orchestrator synthesizes
```

**When to use**: Tasks that decompose into clearly separable subtasks with different expertise requirements.

**Reference**: OpenClaw `subagent-registry.ts`, Nanobot `SubagentManager`.

---

### `02_parallel_subagents.py` — Fan-Out

Multiple independent workers run concurrently via `ThreadPoolExecutor`. Results are collected as they complete and passed to an aggregator agent for synthesis. Wall-clock time is measured for both sequential and parallel execution to make the speedup concrete.

```
Orchestrator
    ├── Worker A ──┐
    ├── Worker B ──┼── (concurrent) ──► Aggregator ──► Summary
    └── Worker C ──┘
```

**When to use**: Subtasks are independent (no data dependency between them). Parallelism cuts wall-clock time proportionally to worker count.

**Reference**: Nanobot `concurrent_tools=True` in `AgentRunner`, OpenClaw parallel tool dispatch in `pi-embedded-subscribe.ts`.

---

### `03_sequential_pipeline.py` — Baton-Pass

Three specialized agents run in sequence: **Researcher → Writer → Editor**. Each agent receives the previous agent's output as its input. Narrow, well-defined roles produce better results than a single agent attempting all three tasks.

```
Researcher  ──►  Writer  ──►  Editor  ──►  Final Article
  (facts)        (draft)      (polish)
```

**When to use**: Tasks with hard data dependencies between stages, or where quality improves by separating concerns (e.g. research vs. writing vs. critique).

**Reference**: Nanobot message bus chaining, Reflexion pattern (`01_agent_patterns/03_reflexion.py`) for the self-critique variant.

---

### `04_async_announce.py` — Async Announce

Workers run in background threads and post an `Announcement` to a shared queue when they complete. The parent event loop polls for announcements between ticks and can process other work in the meantime. Results arrive in completion order, not spawn order.

```
Parent loop (non-blocking)
    │
    ├── spawns Worker A ──────────────────────────► posts Announcement
    ├── spawns Worker B ──────────────────► posts Announcement
    ├── spawns Worker C ──────────────────────────────────────► posts Announcement
    │
    └── tick loop: drain queue, process each arrival, do other work
              │
              ▼
          Synthesizer (once all arrived)
```

**Key difference from `02_parallel_subagents.py`**: The parent does not block waiting for all workers. It processes each result the moment it arrives. This enables streaming UX and frees the parent to handle new requests between completions.

**Reference**: OpenClaw `subagent-announce.ts` + `subagent-announce-delivery.ts`. Production agents use this pattern so a subagent completing 10 minutes later doesn't block other sessions.

---

## Core Concepts

### Why multiple agents?

A single agent with a large context window can handle many tasks. Multi-agent systems make sense when:

1. **Specialization** — a narrow system prompt outperforms a general one for each subtask
2. **Parallelism** — independent subtasks can run concurrently to reduce latency
3. **Context isolation** — each worker gets a clean context; the orchestrator is not polluted with subtask details
4. **Scale** — tasks too long to fit in one context window can be split across agents

### The context injection pattern

Worker agents reuse the parent's `model` via `context.model` (passed through the tool's `context` argument). This avoids re-initializing a provider and lets workers share the same model configuration.

### Shared state and thread safety

`Memory` objects are not thread-safe. Each agent must have its own `Memory` instance. The `ModelProvider` wraps `litellm.completion()` which is thread-safe for concurrent calls.

---

## How Production Systems Approach This Differently

OpenClaw and Nanobot both solve multi-agent coordination, but their design constraints pushed them toward very different architectures. Understanding why illuminates the tradeoffs in these patterns.

### Subagent delivery: synchronous return vs. async announce

The most fundamental difference is how a child agent's result reaches the parent.

**Nanobot** routes the result back through the same `MessageBus` that handles user messages. A child `AgentLoop` completes, posts an `OutboundMessage`, and the bus delivers it to the parent's session as if a user had spoken. This is simple and consistent — one delivery mechanism for everything — but it means the parent's loop must be active and listening when the child finishes.

**OpenClaw** separates delivery from execution entirely. When a child completes, `subagent-announce-delivery.ts` pushes the result into the parent's session store as a pending message. The parent picks it up on its *next* turn, regardless of whether it was running when the child finished. This decoupling is essential for OpenClaw's mobile/multi-platform architecture: a subagent can complete 10 minutes after the parent's turn ended, while the user is on their phone. The announce queue bridges that temporal gap.

The `04_async_announce.py` example models this queue-based pattern in Python threads. The key property isn't concurrency itself — it's that the parent is never blocked *waiting* for a specific child.

### Subagent scoping: registry-tracked vs. fire-and-forget

**OpenClaw** maintains a full `SubagentRegistry` that tracks every child agent's lineage (parent → child → grandchild), enforces depth limits to prevent runaway recursion, and manages lifecycle states (pending → running → completed/failed). This overhead is justified because OpenClaw supports long-running background agents that outlive a single session and need to be recoverable after a crash.

**Nanobot** takes a lighter approach: `SubagentManager` spawns a child `AgentLoop` as a background `asyncio.Task` and tracks it only until it posts its result. No lineage graph, no depth enforcement by default. The tradeoff is simplicity for single-server deployments, at the cost of being harder to audit or cap in recursive scenarios.

The `01_orchestrator_worker.py` example sits closer to Nanobot's model — spawn, run, return — which is the right default when you control the prompt and depth isn't a concern.

### Parallel execution: tool-level vs. agent-level

Both systems support parallelism, but at different granularities.

**OpenClaw** parallelises at the *tool* level within a single agent turn: `pi-embedded-subscribe.ts` dispatches all tool calls in a response concurrently, then waits for all results before continuing. The agent itself is still a single sequential loop.

**Nanobot** supports both: `concurrent_tools=True` for within-turn tool parallelism, and independent `asyncio.Tasks` for separate agent sessions running simultaneously. A global `Semaphore` caps total concurrent LLM calls to prevent overload.

`02_parallel_subagents.py` models the agent-level case with `ThreadPoolExecutor`. This is appropriate when each subtask is substantial enough to warrant a full agent loop (multi-step reasoning, tool use), not just a single tool call.

### Sequential pipelines: explicit handoff vs. structured planning

**Nanobot** doesn't have a dedicated sequential pipeline primitive. Chains are assembled by the caller: run agent A, pass its output to agent B, and so on. This is exactly what `03_sequential_pipeline.py` does — simple and transparent.

**OpenClaw** has a `runtime-plan/` module that formalises multi-step execution into a plan structure the agent can introspect and modify. This is more powerful but adds overhead: the plan must be serialised, stored, and recovered on crash. It's warranted when tasks are long-running enough that a mid-execution restart is a real risk.

For tasks that complete in a single session, the explicit handoff pattern is simpler and easier to debug.

---

See [`docs/reference_architectures.md`](../../docs/reference_architectures.md) for the full architectural analysis of both systems.
