# 01 Agent Patterns

The three fundamental loop architectures. Each pattern answers a different question about how an agent should organise its reasoning.

---

## Concept Ladder

| Level | Pattern | File |
| :---- | :------ | :--- |
| 1 | Think-Act-Observe loop driven by tool availability | `01_react_basic.py` |
| 2 | Decouple planning from execution; planner produces a plan, executor follows it | `02_plan_and_execute.py` |
| 3 | Generate a draft, critique it, revise — quality improvement through self-evaluation | `03_reflexion.py` |

---

## Examples

### `01_react_basic.py` — ReAct

The baseline agent loop: the model thinks, calls a tool, observes the result, and repeats until it has enough information to answer. Two filesystem tools (`list_files`, `read_file_content`) are registered; the model decides when and how to use them.

**Key concept**: the loop structure in `core/agent.py` is the same across all examples. Patterns differ in how they compose multiple loops or constrain the planner.

[Guide →](01_react_basic.md)

---

### `02_plan_and_execute.py` — Plan-and-Execute

A dedicated planner call produces a numbered plan before any tools are used. The plan is injected into an executor agent's system prompt, focusing it on following steps rather than deciding strategy mid-run.

**Key concept**: separating planning from execution reduces in-flight course correction, which is useful when the task structure is known upfront. The tradeoff is flexibility — the executor follows the plan even when discovery suggests a better path.

[Guide →](02_plan_and_execute.md)

---

### `03_reflexion.py` — Reflexion

Three agents in sequence: Writer produces a draft, Critic evaluates it, Editor revises. Each has an isolated `Memory()` so the Critic is not anchored to the Writer's assumptions, and the Editor sees both the draft and the critique without the full conversation history.

**Key concept**: narrow, isolated system prompts outperform a single general-purpose agent for quality-sensitive tasks. The cost is 2–3× the model calls.

[Guide →](03_reflexion.md)

---

## How production systems approach these patterns

### The ReAct loop: synchronous vs. streaming-first

This cookbook implements a synchronous request-response loop: `model.generate()` blocks until the full response arrives, then tool calls are dispatched sequentially.

**OpenClaw** (`pi-embedded-runner.ts`) is streaming-first by design. Every token, tool call, and lifecycle event flows through a subscriber callback chain (`pi-embedded-subscribe.ts`). Text deltas reach the UI as they arrive; tool dispatch happens only after the full stop token is received. This single execution path is shared by the mobile gateway, CLI, and web UI. The constraint driving it is latency perception — a user on a mobile app sees tokens appearing rather than waiting 20 seconds for a complete response.

**Nanobot** (`AgentRunner.run()`) also processes streaming responses, but wraps each session in its own `asyncio.Task` with a global `Semaphore` capping concurrent LLM calls. Per-session serial ordering is preserved; cross-session parallelism is free. The streaming connection is managed inside the runner; callers see a complete result.

The cookbook's synchronous approach is right for learning — the full response is inspectable in one place. In production, streaming is required for any interface where the user waits longer than a few seconds.

### Tool dispatch: sequential vs. parallel within a turn

When the model returns multiple tool calls in one response, this cookbook executes them sequentially. Both production systems dispatch them concurrently where safe.

**OpenClaw** dispatches all tool calls from a single response in parallel (`pi-embedded-subscribe.ts`), collecting results before the next model call. **Nanobot** supports `concurrent_tools=True` via `asyncio.gather`. The tradeoff is latency vs. debuggability: parallel dispatch can cut a 4-tool turn from 8s to 2s, but errors are harder to attribute when calls run simultaneously. For read-only tools (filesystem inspection, search) parallelism is safe. For tools that write state, ordering matters.

### Plan-and-Execute: free-form text vs. structured plan objects

This cookbook's planner produces a numbered list as free-form text, injected into the executor's system prompt. There is no structured representation — the executor reads it as natural language.

**OpenClaw** formalises plans in `runtime-plan/`: typed data structures with discrete steps, completion states, and checksums. A partially-executed plan survives a crash and can be reloaded. The overhead is justified when tasks span hours or require restart resilience. **Nanobot** has no plan primitive — multi-step plans are implemented by chaining sub-agents, coupling plan structure to agent topology.

The free-form approach is the right default for tasks that complete in a single session. Structured plans become necessary when execution spans multiple sessions or when partial completion must be recoverable.

### Reflexion: absent from both production systems — and why

Neither OpenClaw nor Nanobot implements a Reflexion pattern. This is deliberate.

Both systems invest in robust tool-error recovery: an error from a shell command or failed file write is unambiguous, and the agent retries with corrected arguments. Quality improvement through explicit self-critique is not their primary mechanism. **OpenClaw** relies on identifier preservation in compaction to keep the agent's context coherent across turns. **Nanobot** uses the Dream processor — a two-phase background job that analyses completed sessions and updates memory files — which improves the agent's future behaviour rather than the current response.

Reflexion adds value for tasks where the failure mode is subtle quality loss (writing, analysis, open-ended code generation) rather than a hard tool error. The 2–3× model call cost is worth it when the deliverable is the response itself, not the side effects of tool calls.
