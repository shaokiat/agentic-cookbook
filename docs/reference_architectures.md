# Reference Architecture Analysis: OpenClaw & Nanobot

This document analyzes two open-source agentic systems — **OpenClaw** (TypeScript, full-stack production agent) and **Nanobot** (Python, lightweight reference implementation) — and maps their architectural decisions to the concepts introduced in this cookbook.

Both are spiritual descendants of Claude Code, designed to run a coding/personal agent loop. Studying them side-by-side reveals the core patterns any production agent must solve, and which abstractions are genuinely necessary vs. accidental complexity.

---

## Systems at a Glance

| Dimension | OpenClaw | Nanobot |
|:----------|:---------|:--------|
| Language | TypeScript (ESM, Node 22+) | Python 3.11+ |
| Size | Very large (~300+ source files in agents/ alone) | Small (~15 core files) |
| Scope | Full product: CLI, iOS/Android/macOS apps, web gateway | Agent loop + channels + memory |
| Target | Production agent with full platform support | Research-ready, hackable agent |
| Channels | Desktop app, mobile apps, Telegram, Discord, Slack, … | Telegram, Discord, Slack, WeChat, Feishu, Email, WebUI, … |
| Memory | Context compaction + skills + memory search | MEMORY.md + history.jsonl + Dream processor |
| Plugin system | Manifest-based plugins via `openclaw/plugin-sdk` | SKILL.md manifests |
| Tool permission | Per-tool policy pipeline + sandboxing | Config-gated (exec, web, workspace restriction) |
| Multi-agent | Subagent registry with depth limits, topology | SpawnTool + SubagentManager |
| MCP | Stdio + SSE transport | Stdio transport |
| Session | File-backed, per-agent-id, write-locked | JSONL per-session-key, atomic writes |

---

## OpenClaw Architecture

OpenClaw is the TypeScript reference implementation closest to Claude Code itself. Its source is organized into clear layers with strict boundary enforcement.

### 1. Directory Structure

```
src/
├── agents/          # The core agent runtime (~300 files)
│   ├── pi-embedded-runner.ts      # Main agent execution engine
│   ├── pi-embedded-subscribe.ts   # Streaming handler & tool dispatch
│   ├── compaction.ts              # LLM-backed context compression
│   ├── subagent-*.ts              # Sub-agent lifecycle and registry
│   ├── bash-tools.ts              # Shell tool with PTY support
│   ├── pi-tools.ts                # File/read tools with path policy
│   ├── skills.ts                  # Skill discovery & injection
│   └── system-prompt.ts           # System prompt assembly
├── channels/        # Chat platform adapters (Telegram, Discord, Slack…)
├── plugins/         # Plugin loader and manifest scanner
├── plugin-sdk/      # Public SDK for third-party extension authors
├── gateway/         # WebSocket protocol for mobile apps
└── context-engine/  # Prompt construction and context assembly
extensions/          # First-party plugins (each is a self-contained module)
apps/                # iOS, Android, macOS native apps
ui/                  # Web UI
```

### 2. The Agent Execution Engine

**File**: `src/agents/pi-embedded-runner.ts`

OpenClaw's agent runner follows a strict streaming-first loop:

```
build_system_prompt()
    │
    ▼
sanitize_session_history()  ← strip volatile blocks (images, runtime ctx)
    │
    ▼
preflight_token_budget()     ← check soft/hard limits before each call
    │
    ▼
stream_model_response()      ← token-by-token via anthropic-transport-stream.ts
    │
    ├── text_delta? → emit to subscriber
    ├── tool_use?  → collect tool_calls
    └── stop?      → dispatch tool execution
         │
         ▼
pi-embedded-subscribe.ts: handlers/tools.ts
    ├── execute tools (parallel where safe)
    ├── emit tool_result blocks
    └── loop back to model call
```

**Key design choice**: Streaming is mandatory, not optional. Every tool result, text delta, and lifecycle event flows through a subscriber callback chain (`pi-embedded-subscribe.ts`). This allows the mobile gateway, web UI, and CLI to share one execution path.

### 3. Context & Compaction

**File**: `src/agents/compaction.ts`

OpenClaw compaction mirrors what is described in `docs/openclaw_memory_architecture.md`:

- **Soft limit** (configurable, ~182k tokens for Claude): triggers compaction
- **Hard limit** (~195k tokens): stops the agent with `stop_reason='prompt_too_long'`
- The LLM summarizes evicted history into a 9-section compact summary
- A `compact_boundary` marker is inserted so the agent knows a gap exists
- Up to 3 compaction attempts before a circuit breaker fires

**New insight from source**: OpenClaw also has `identifier-preservation` — it specifically tries to keep file paths, function names, and variable names intact through compaction so the agent can still reference them in tool calls after the conversation is compressed.

### 4. Subagent System

**Files**: `src/agents/subagent-*.ts` (registry, spawn, lifecycle, announce, control)

OpenClaw's subagent system is the most sophisticated part:

```
Parent agent
    │
    └── spawns via openclaw-tools.subagents.sessions-spawn.ts
              │
              ▼
        SubagentRegistry (subagent-registry.ts)
              ├── tracks lineage (parent → child → grandchild)
              ├── enforces depth limits (subagent-depth.ts)
              ├── manages lifecycle (pending → running → completed/failed)
              └── routes announces back to parent via announce queue

        SubagentAnnounce (subagent-announce.ts)
              ├── captures completion reply from child
              └── delivers it as a user message to parent's next turn
```

**Key pattern**: Subagents don't return values directly. They "announce" their results by pushing a message into the parent's session via a separate delivery path (`subagent-announce-delivery.ts`). The parent's next turn picks this up as a normal user message. This decouples spawner and worker in time — a subagent can complete minutes after the parent's turn ended.

### 5. Plugin System

**Files**: `src/plugin-sdk/`, `src/plugins/`, `extensions/*/`

OpenClaw uses a manifest-first plugin architecture:

```json
// extensions/<id>/manifest.json
{
  "id": "telegram",
  "hooks": ["beforePrompt", "afterTurn"],
  "tools": ["send_message", "get_updates"],
  "channels": ["telegram"]
}
```

- Plugins cross into core **only** via the public `openclaw/plugin-sdk/*` barrel
- Core is extension-agnostic: no bundled extension IDs in core code
- Lifecycle hooks: `beforePrompt`, `afterTurn`, `onResume`, `beforePersist`
- Hook policy (`tool-policy-pipeline.ts`): allows/denies/asks per tool before execution

### 6. Tool Permission Pipeline

**File**: `src/agents/tool-policy-pipeline.ts`

Every tool call passes through a policy pipeline before execution:

```
tool_call
    │
    ▼
tool-policy.ts        ← match against allowlist/denylist rules
    │
    ▼
sandbox-tool-policy.ts ← enforce workspace path restrictions
    │
    ▼
bash-tools.exec-approval-request.ts ← ask user if "confirm" mode
    │
    ▼
execute
```

This is a **decision tree, not a simple flag**. Each tool can have its own policy override, the sandbox can restrict filesystem paths independently, and interactive approval is a first-class mode.

---

## Nanobot Architecture

Nanobot is the lightweight Python reference implementation. Its codebase is intentionally small enough to read in an afternoon, while still supporting channels, memory, MCP, and sub-agents.

### 1. Directory Structure

```
nanobot/
├── agent/
│   ├── loop.py          # AgentLoop — main message dispatch and orchestration
│   ├── runner.py        # AgentRunner — the inner tool-calling loop
│   ├── context.py       # ContextBuilder — system prompt + message assembly
│   ├── memory.py        # MemoryStore + Consolidator + Dream
│   ├── autocompact.py   # TTL-based session expiry compaction
│   ├── skills.py        # Skill discovery and injection
│   ├── subagent.py      # SubagentManager — spawn and track child agents
│   ├── hook.py          # AgentHook + CompositeHook — lifecycle callbacks
│   └── tools/           # All tool implementations
├── bus/                 # MessageBus — async pub/sub between channels and loop
├── channels/            # Platform adapters (Telegram, Discord, Slack, …)
├── session/             # Session persistence (JSONL per session key)
├── providers/           # LLM provider abstraction (Anthropic, OpenAI, …)
├── config/              # Schema + loader for ~/.nanobot/config.json
├── cron/                # Scheduled task service
└── skills/              # Built-in skill packages (SKILL.md manifests)
```

### 2. The Agent Loop

**File**: `nanobot/agent/loop.py` — `AgentLoop`

Nanobot's architecture is built around a **message bus** (pub/sub) rather than a direct caller-callee chain:

```
Channel (Telegram, Discord, CLI…)
    │
    │ publishes InboundMessage
    ▼
MessageBus.consume_inbound()
    │
    ▼
AgentLoop.run()          ← main loop, non-blocking, task-per-session
    │
    ├── command? → dispatch directly (no LLM)
    │
    ├── active session? → route to pending_queue (mid-turn injection)
    │
    └── new task → asyncio.create_task(_dispatch(msg))
              │
              ▼
         _process_message()
              │
              ├── restore_runtime_checkpoint()    ← crash recovery
              ├── auto_compact.prepare_session()  ← TTL-based compaction
              ├── consolidator.maybe_consolidate() ← token-budget consolidation
              ├── context.build_messages()         ← assemble prompt
              └── _run_agent_loop()
                        │
                        ▼
                   AgentRunner.run()   ← inner loop
                        │
                        ├── LLM call (with retry)
                        ├── parallel tool execution
                        ├── mid-turn injection (pending_queue drain)
                        └── repeat until stop condition
```

**Key design choice**: Sessions are processed serially per-session-key but concurrently across sessions. A `Semaphore` caps total concurrent LLM calls. This gives per-user ordering guarantees without blocking other users.

### 3. Memory System

**File**: `nanobot/agent/memory.py`

Nanobot's memory is the most detailed in any open-source agent implementation:

```
workspace/
├── MEMORY.md        ← long-term facts (agent writes here)
├── USER.md          ← persistent user profile
├── SOUL.md          ← agent personality / system identity
└── memory/
    ├── history.jsonl     ← append-only log of summarized conversations
    └── .dream_cursor     ← tracks which history entries Dream has processed
```

Three components manage this:

**MemoryStore** — pure file I/O:
- Reads/writes `MEMORY.md`, `USER.md`, `SOUL.md`
- Appends timestamped entries to `history.jsonl` (JSONL format, cursor-indexed)
- Auto-migrates legacy `HISTORY.md` on first run

**Consolidator** — token-budget-triggered LLM summarization:
- Monitors session prompt size before each turn
- When over budget: picks a user-turn boundary, summarizes old messages → appends to `history.jsonl`
- Up to 5 consolidation rounds per check, each round targeting 50% of budget
- Falls back to raw-archive if LLM call fails

**Dream** — two-phase background memory processor (runs on a cron):
```
Phase 1: Plain LLM call
    input:  unprocessed history.jsonl entries + current MEMORY.md + USER.md + SOUL.md
    output: analysis of what to add, update, or remove from memory files

Phase 2: AgentRunner with read_file / edit_file tools
    input:  Phase 1 analysis
    output: targeted edits to MEMORY.md, USER.md, SOUL.md, and skills/
    commit: git auto-commit if changes were made
```

Dream is the key differentiator from simpler agents: instead of wholesale rewriting memory files, it delegates incremental editing to the model using its own tool-calling loop. This means memory updates are surgical and auditable via git history.

**Per-line staleness annotation**: Before passing `MEMORY.md` to Dream's Phase 1, each line is annotated with its age in days (e.g. `← 30d`) based on `git blame`. This tells the LLM which facts may be outdated.

### 4. Skills System

**Directory**: `nanobot/skills/`

Skills are self-contained prompt modules, loaded as context for specific domains:

```
skills/
├── summarize/SKILL.md   ← "When asked to summarize…"
├── github/SKILL.md      ← "When working with GitHub…"
├── weather/SKILL.md     ← "When asked about weather…"
└── memory/SKILL.md      ← "How to update MEMORY.md…"
```

`ContextBuilder` automatically discovers and injects relevant skills into the system prompt. Dream can also create new skills when it detects a recurring pattern in `history.jsonl`.

### 5. Sub-agents

**File**: `nanobot/agent/subagent.py` — `SubagentManager`

Nanobot's sub-agent model is simpler than OpenClaw's but functionally equivalent:

```
Parent AgentLoop
    │
    └── SpawnTool.run()
              │
              ▼
        SubagentManager.spawn()
              ├── creates a child AgentLoop with scoped workspace
              ├── runs it as a background asyncio Task
              └── on completion: publishes result as system InboundMessage
                        │
                        ▼
                  Parent AgentLoop receives it via bus
                  (same path as a user message, role="assistant")
```

Results route back through the same message bus, so the parent's next turn sees the sub-agent's output as a continuation of the conversation.

### 6. Session Persistence and Crash Recovery

**File**: `nanobot/agent/loop.py` — checkpoint methods

Nanobot has crash-safe session handling:

1. **Early persist**: The user's message is saved to session before the LLM is called
2. **Runtime checkpoint**: After each tool execution, a checkpoint is saved (`session.metadata["runtime_checkpoint"]`)
3. **Recovery**: On the next message for a session, `_restore_runtime_checkpoint()` replays incomplete tool results before continuing

This means interrupted turns (e.g. process kill) don't lose context — they're reconstructed on the next request.

---

## Architectural Comparison

| Pattern | OpenClaw | Nanobot | Cookbook analogue |
|:--------|:---------|:--------|:-----------------|
| Agent loop | Streaming-first, subscriber chain | Async task-per-session, message bus | `core/agent.py` |
| Tool dispatch | Policy pipeline → sandboxed execution | Config-gated, concurrent | `core/registry.py` |
| Context compaction | LLM summarization + identifier preservation | Consolidator (token budget) + AutoCompact (TTL) | `examples/00_primitives/02_context_window.py` |
| Intermediate memory | `CLAUDE.md` injection via `system-prompt.ts` | `MEMORY.md` + `USER.md` + `SOUL.md` injection | `examples/02_memory_management/01_markdown_persistence.py` |
| Long-term memory | `memory-search.ts` (semantic search) | `history.jsonl` + Dream two-phase processor | `examples/02_memory_management/02_hybrid_search.py` |
| Sub-agents | Registry + announce-based async delivery | SpawnTool + message bus routing | `examples/03_multi_agent_systems/` |
| Plugin/extension | Manifest + SDK boundary + hook policy | SKILL.md manifests + hook system | — |
| Session persistence | Per-agent-id files, write-locked | Per-session-key JSONL, atomic, crash recovery | — |
| Channels | Desktop app, mobile gateway, chat platforms | Chat platforms + WebUI + OpenAI-compatible API | — |

---

## Key Patterns and What They Teach

### Pattern 1: The Message Bus Boundary (Nanobot)

Nanobot's `MessageBus` decouples channels from the agent loop entirely. A channel publishes an `InboundMessage`; the agent loop consumes it; the response is an `OutboundMessage`. Neither side knows about the other.

**Why it matters**: This is what makes multi-channel support trivial to add. A new Telegram adapter publishes `InboundMessage` objects — the agent loop is unchanged.

**Cookbook implication**: The simple `Agent.run()` interface in `core/agent.py` is the synchronous version of this pattern. The bus is the async, multi-channel generalization.

### Pattern 2: The Dream Processor (Nanobot)

Dream is the most novel architectural pattern across both systems. Rather than a single "write to memory" step, memory updates happen asynchronously via a two-phase process: one LLM call to analyze, one tool-using AgentRunner to apply targeted edits.

**Why it matters**:
- Memory updates are incremental rather than destructive rewrites
- Git auto-commit makes memory changes auditable
- Stale-fact detection (per-line ages) is automated
- New skills can be created automatically from patterns in history

**Cookbook implication**: `examples/02_memory_management/01_markdown_persistence.py` demonstrates the file-write pattern. Dream shows how to make that update loop autonomous and intelligent.

### Pattern 3: Announce-Based Subagent Delivery (OpenClaw)

In OpenClaw, subagents don't return values synchronously. They complete asynchronously and "announce" results by pushing a message into the parent's session. The parent sees this as a regular user turn.

**Why it matters**: It removes the need for synchronous blocking across agent boundaries. A subagent can take 10 minutes; the parent's loop can process other sessions in the meantime.

**Cookbook implication**: `examples/03_multi_agent_systems/` will implement the simpler synchronous `delegate_agent` pattern first, then this async-announce pattern as an advanced extension.

### Pattern 4: Manifest-First Extensibility (OpenClaw)

OpenClaw's architecture rule is strict: **core stays extension-agnostic**. All extension-specific behavior lives in its own module, crossing into core only via the published `plugin-sdk` barrel.

**Why it matters**: Third-party plugins work because there are no hidden contracts. The boundary is enforced structurally, not just by convention.

**Cookbook implication**: Tool registration in `core/registry.py` follows the same principle — tools are registered *to* the agent, not built *into* it.

### Pattern 5: Per-Session Concurrency with Ordering Guarantees (Nanobot)

Nanobot processes messages serially within a session (via `asyncio.Lock` per session key) but concurrently across sessions (via a global `Semaphore`). Mid-turn follow-up messages are queued into a `pending_queue` rather than creating a competing task.

**Why it matters**: This prevents race conditions where a second message arrives before the first response is saved, without serializing all users through a single queue.

**Cookbook implication**: The simple `Agent.run()` in `core/agent.py` is single-threaded. Understanding this pattern explains why production agents need an event loop and session-scoped locking.

---

## Mapping to the Cookbook Concept Ladder

| Cookbook Level | Concept | OpenClaw component | Nanobot component |
|:--------------|:--------|:-------------------|:------------------|
| Level 1: Primitives | Tool use | `pi-tools.ts`, `bash-tools.ts` | `tools/` directory |
| Level 1: Primitives | Context window | `compaction.ts`, `context-window-guard.ts` | `autocompact.py`, `Consolidator` |
| Level 1: Primitives | Stop condition | `pi-embedded-runner.ts` turn limits | `AgentRunner.max_iterations` |
| Level 2: Loop patterns | ReAct | `pi-embedded-subscribe.ts` tool dispatch | `AgentRunner.run()` |
| Level 2: Loop patterns | Plan-and-Execute | `runtime-plan/` | — (via sub-agents) |
| Level 2: Loop patterns | Reflexion | — | — |
| Level 3: Memory | Short-term (context) | `compaction.ts` | `Consolidator.maybe_consolidate_by_tokens()` |
| Level 3: Memory | Intermediate (files) | `CLAUDE.md` via `system-prompt.ts` | `MEMORY.md` / `SOUL.md` / `USER.md` |
| Level 3: Memory | Long-term (retrieval) | `memory-search.ts` | `Dream` + `history.jsonl` |
| Level 4: Tool patterns | Tiered permissions | `tool-policy-pipeline.ts` + sandbox | Config-gated enable flags |
| Level 4: Tool patterns | Parallel tool calls | `pi-embedded-subscribe.ts` | `concurrent_tools=True` in `AgentRunner` |
| Level 4: Tool patterns | Error recovery | `compaction.retry.ts`, failover | `AgentRunner` retry + `restore_runtime_checkpoint()` |
| Level 5: Multi-agent | Orchestrator/worker | `subagent-registry.ts` + announce | `SubagentManager` + `SpawnTool` |
| Level 5: Multi-agent | Session persistence | Per-agent-id files, write-locked | Per-session-key JSONL, atomic |
| Level 5: Multi-agent | Background agents | Subagent async lifecycle | Background asyncio tasks |
| Level 6: Observability | Tracing | `anthropic-payload-log.ts`, `cache-trace.ts` | `loguru` + tool events |
| Level 7: Extensibility | Plugin system | `plugin-sdk/` + manifests | SKILL.md + `AgentHook` |
| Level 7: Extensibility | MCP | `mcp-stdio-transport.ts` + SSE | `tools/mcp.py` stdio transport |

---

## Design Principles Shared by Both Systems

1. **The context window is the only working memory.** Everything the agent knows must fit there. Memory systems (compaction, summarization, retrieval) are context window management strategies.

2. **Tools are first-class, not afterthoughts.** Both systems register tools as structured objects with schemas, not ad-hoc function pointers. This enables policy enforcement, parallel dispatch, and schema-based validation.

3. **Sessions must survive crashes.** Both systems persist session state durably before risky operations and provide recovery paths. This is essential for long-running tasks.

4. **Memory is a separate concern from context.** Context is ephemeral (one run). Memory persists across runs. The two are connected by compaction/summarization pipelines that translate context events into durable memory updates.

5. **Channels are adapters, not architecture.** Both systems isolate channel-specific code (Telegram formatting, Discord rate limits) from the agent loop. The agent loop sees `InboundMessage`/`OutboundMessage`, never Telegram objects.

6. **Extension boundary enforcement.** Both systems define a clear boundary between core and plugins/skills/extensions. Crossing this boundary in the wrong direction is a bug, not a shortcut.

---

_Created: 2026-04-29_
