# 06 Frameworks — pi-agent / pi-mono

This section maps the concepts you built from scratch in `00–05` onto a
production framework: **pi-mono** (https://github.com/badlogic/pi-mono).
Understanding how a framework formalizes the same primitives you implemented
by hand is the fastest path to reading production codebases confidently.

> **Before reading this**: complete `00_primitives` through `05_evaluation_and_monitoring`.
> Every pattern below maps directly to an example you have already run.

---

## The Layer Cake

```
openclaw (real-world application)
    │  consumes pi-coding-agent as an SDK
    ▼
pi-coding-agent  (@mariozechner/pi-coding-agent)
    │  coding-specific harness: default tools, Skills, Extensions, RPC
    ▼
pi-agent-core  (@mariozechner/pi-agent-core)
    │  stateful agent runtime: AgentState, events, tool dispatch
    ▼
pi-ai  (@mariozechner/pi-ai)
       unified LLM provider abstraction: 20+ providers, streaming, cost tracking
```

Each layer adds exactly one concern. Read them in order and the whole stack
becomes legible.

---

## Layer 1 — `pi-ai`: LLM Abstraction

**Cookbook equivalent**: `core/model.py` + `core/registry.py`

`pi-ai` solves the same problem as your `ModelProvider`: hide provider-specific
API shapes behind a single interface. Where your `ModelProvider` uses litellm
as the abstraction layer, `pi-ai` implements it directly.

### Core interface (TypeScript)

```typescript
// packages/ai/src/index.ts
export interface Model {
  complete(messages: Message[], tools?: Tool[]): Promise<CompletionResult>
  streamSimple(messages: Message[], onChunk: (chunk: string) => void): Promise<string>
}

export interface CompletionResult {
  content: string | null
  toolCalls: ToolCall[]
  usage: { promptTokens: number; completionTokens: number; cost: number }
}
```

Compare to your `ModelProvider.generate()` → `ModelResponse`:

| pi-ai | your `core/model.py` |
|---|---|
| `Model.complete()` | `ModelProvider.generate()` |
| `CompletionResult.toolCalls` | `ModelResponse.tool_calls` |
| `CompletionResult.usage` | `ModelResponse.usage` |
| Built-in for 20+ providers | litellm handles provider routing |

**Key addition in pi-ai**: OAuth flows for hosted providers and a
`streamSimple()` path that delivers token-by-token chunks — your `ModelProvider`
currently blocks until the full response arrives.

### Tool schema generation

pi-ai defines `Tool` as a plain object with a JSON schema:

```typescript
interface Tool {
  name: string
  description: string
  inputSchema: JSONSchema
  execute(args: unknown): Promise<string>
}
```

Your `ToolRegistry._generate_schema()` does the same thing from Python type
hints. The difference is location: pi-ai puts `execute` inside the `Tool`
object; your design separates schema (registry) from execution (the Python
function). Both are valid — pi-ai's colocation is more portable, yours is
easier to unit-test the schema separately from the side effect.

---

## Layer 2 — `pi-agent-core`: The Agent Runtime

**Cookbook equivalent**: `core/agent.py`

`pi-agent-core` formalizes the ReAct loop you built in `01_agent_patterns/01_react_basic.py`
into a stateful runtime with an event system.

### AgentState and the loop

```typescript
// packages/agent/src/agent.ts (simplified)
export interface AgentState {
  messages: Message[]
  toolCalls: ToolCallRecord[]
  status: "idle" | "thinking" | "acting" | "done" | "error"
  usage: Usage
}

export async function runAgentLoop(
  model: Model,
  tools: Tool[],
  state: AgentState,
  onEvent: (event: AgentEvent) => void
): Promise<AgentState> {
  while (state.status !== "done") {
    const result = await model.complete(state.messages, tools)
    onEvent({ type: "think", content: result.content, toolCalls: result.toolCalls })

    if (result.toolCalls.length === 0) {
      state.status = "done"
      break
    }

    for (const tc of result.toolCalls) {
      const tool = tools.find(t => t.name === tc.name)
      const observation = await tool.execute(tc.args)
      onEvent({ type: "act", tool: tc.name, observation })
      state.messages.push({ role: "tool", content: observation, toolCallId: tc.id })
    }
  }
  return state
}
```

Compare to your `Agent.run()` loop in `core/agent.py`:

| pi-agent-core | your `core/agent.py` |
|---|---|
| `AgentState` struct | Implicit state in `Memory` + local vars |
| `onEvent` callback | `AgentLogger.log_event()` + Rich prints |
| `status` field | `steps < max_steps` condition |
| Tool execution in loop | Same pattern, sequential by default |

**Key addition**: the `onEvent` stream lets callers subscribe to every step
in real time — the UI can render thinking and tool calls as they happen.
Your `verbose=True` path prints to stdout; pi-agent-core makes the same events
first-class so any consumer (UI, logger, tracer) can subscribe. This is the
same idea as your `02_agent_tracer.py` but built into the framework core.

### Parallel tool execution

```typescript
// packages/agent/src/agent-loop.ts
const results = await Promise.all(
  result.toolCalls.map(tc => executeToolCall(tc, tools))
)
```

This is exactly the `ParallelAgent` pattern from
`04_tool_use_patterns/02_parallel_tool_calls.py`. pi-agent-core makes it
the default for all tool calls in a single turn — sequential is the special
case.

### beforeToolCall / afterToolCall hooks

```typescript
interface AgentOptions {
  beforeToolCall?: (tc: ToolCall) => Promise<ToolCall | null>  // null = deny
  afterToolCall?: (tc: ToolCall, result: string) => Promise<string>
}
```

`beforeToolCall` is the HIL approval gate from
`04_tool_use_patterns/01_human_approval.py` at the framework level.
Returning `null` denies the call; the framework injects a refusal string as
the tool observation. You don't need per-tool approval wrappers.

---

## Layer 3 — `pi-coding-agent`: The Coding Harness

**Cookbook equivalent**: Combines `01_agent_patterns/` + `04_tool_use_patterns/04_dynamic_tools.py`

`pi-coding-agent` is a batteries-included coding agent built on `pi-agent-core`.
It adds the domain-specific layer: default tools, extensibility primitives,
and multiple execution modes.

### Default tools

| Tool | Cookbook equivalent |
|---|---|
| `read_file` | `tools/system_tools.py:read_file_content` |
| `write_file` | HIL-gated write in `01_human_approval.py` |
| `edit_file` | Not in cookbook (diff-based edit) |
| `bash` | Requires `--allow-shell` (permission tier) |

The permission tier system (`always` / `write` / `shell` / `unsafe`) is the
production version of the `require_approval()` wrapper from
`04_tool_use_patterns/01_human_approval.py`. Instead of wrapping each tool,
all tools carry a tier tag and a central gate checks it before dispatch.

### Extensibility primitives

pi-coding-agent has four extension points. Map each to a cookbook concept:

| pi-coding-agent | Cookbook concept |
|---|---|
| **Skill** | A named, prompts-driven capability: `03_reflexion.py` self-critique loop as a reusable module |
| **Extension** | Lifecycle hooks: `beforePrompt`, `afterTurn` — same as the `onEvent` pattern in `02_agent_tracer.py` |
| **Pi Package** | Plugin discovery: same as `@agent_tool` pattern in `04_dynamic_tools.py` |
| **Prompt Template** | Parameterized system prompts with variable injection |

### Execution modes

```typescript
// Four ways to run pi-coding-agent:
piAgent.runInteractive()     // REPL: reads from stdin, streams to stdout
piAgent.runPrint(task)       // one-shot: run task, print JSON result
piAgent.runRpc(port)         // JSON-RPC server: used by IDE integrations
piAgent.runSdk(task, hooks)  // embed in another process (openclaw does this)
```

The `runSdk` mode is how openclaw consumes pi-coding-agent. It passes
lifecycle hooks to intercept events — exactly what `AgentTracer` does in
`05_evaluation_and_monitoring/02_agent_tracer.py`.

---

## Layer 4 — openclaw: Real-World Application

**Cookbook equivalent**: All of `03_multi_agent_systems/` combined

openclaw is a full coding assistant application that uses pi-coding-agent's
SDK mode. Reading it shows how all the patterns you've studied compose at scale.

### How openclaw uses the layers

```
openclaw UI (TypeScript/Svelte)
    │  user types a message
    ▼
Session Manager
    │  routes to active agent session
    ▼
pi-coding-agent (SDK mode, runSdk())
    │  core agent loop with default tools
    ▼
pi-agent-core  (parallel tool dispatch, event stream)
    │
    ▼
pi-ai  (Anthropic / OpenAI / Google provider)
```

### Multi-agent patterns in openclaw

openclaw implements all four patterns from `03_multi_agent_systems/`:

| Pattern | openclaw implementation | Cookbook example |
|---|---|---|
| Orchestrator-Worker | `subagent-registry.ts` tracks child agents; parent calls `delegate_agent` tool | `01_orchestrator_worker.py` |
| Parallel fan-out | `pi-embedded-subscribe.ts` `Promise.all()` on tool calls | `02_parallel_subagents.py` |
| Sequential pipeline | `runtime-plan/` formalises multi-step execution into a serialisable plan | `03_sequential_pipeline.py` |
| Async announce | `subagent-announce.ts` + `subagent-announce-delivery.ts`: results pushed to session store, parent picks up on next turn | `04_async_announce.py` |

The async announce pattern is openclaw's most distinctive design: a subagent
can complete 10 minutes after the parent's turn ended (while the user is on
their phone), and the result is still delivered correctly because it's queued
in the session store rather than blocking the parent loop.

### Memory architecture

openclaw implements the same three-tier memory model documented in
`research/AGENT_ARCHITECTURE.md`:

```
Core context (active messages)
    │  context compaction when approaching token limit
    ▼
Project-scoped markdown (MEMORY.md, journal files)
    │  auto-written by the agent at checkpoints
    ▼
Archival hybrid search (vector + BM25)
    │  retrieved on-demand without flooding context
```

Compare to `02_memory_management/`:
- `01_markdown_persistence.py` → project-scoped markdown tier
- `02_hybrid_search.py` → archival hybrid search tier
- Context compaction → not in cookbook yet (advanced topic)

---

## Learning Path Summary

```
00_primitives           → understand the raw API: tools, context, stop
01_agent_patterns       → build agent loops by hand: ReAct, Plan, Reflexion
02_memory_management    → add persistence: markdown, hybrid search
03_multi_agent_systems  → coordinate agents: delegate, fan-out, pipeline, async
04_tool_use_patterns    → advanced tool patterns: HIL, parallel, retry, dynamic
05_evaluation           → measure what you built: logs, traces, LLM judge
    │
    ▼  you are here
06_frameworks/pi_agent  → see how pi-mono formalizes all of the above
    │
    ▼  next steps
Read pi-mono source:
  packages/ai/src/index.ts        (Layer 1: your ModelProvider)
  packages/agent/src/agent.ts     (Layer 2: your Agent)
  packages/coding-agent/src/      (Layer 3: your tools + registry)
Read openclaw source:
  src/subagent-registry.ts        (orchestrator-worker at scale)
  src/subagent-announce*.ts       (async announce in production)
  src/runtime-plan/               (sequential pipeline with crash recovery)
```

---

## Where to Find the Code

```
research/openclaw/      ← openclaw source (already cloned)
research/AGENT_ARCHITECTURE.md  ← architecture notes from prior research
```

To clone pi-mono for reference:
```bash
git clone https://github.com/badlogic/pi-mono research/pi-mono
```
(Keep research material under `research/`, not `/tmp`.)
