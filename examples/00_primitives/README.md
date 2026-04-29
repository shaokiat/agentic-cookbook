# 00 Primitives

The three building blocks every agent loop depends on. Each example isolates one concept so the mechanics are visible before they are composed into a full pattern.

---

## Concept Ladder

| Level | Concept | File |
| :---- | :------ | :--- |
| 1 | Register functions as tools; model decides when to call them | `01_tool_use.py` |
| 2 | The context window is working memory; three strategies to manage it | `02_context_window.py` |
| 3 | Three ways a loop terminates; what happens when it does not | `03_stop_condition.py` |

---

## Examples

### `01_tool_use.py` — Tool Use / Function Calling

The full tool use lifecycle in one file: define a plain Python function, register it, watch the model decide when to call it and in what order.

Four tools are registered: `add`, `multiply`, `count_words`, and `summarize_history`. The last one uses the `context` injection pattern — it receives the agent itself as a parameter, letting it inspect the live conversation. The model chains all four tools in the correct order to answer a multi-step arithmetic question.

**Key concept**: `ToolRegistry` auto-generates JSON schemas from Python type hints and `:param` docstrings. You write ordinary functions; the framework handles the API contract.

[Walkthrough →](01_tool_use_walkthrough.md)

---

### `02_context_window.py` — The Context Window as Working Memory

Runs the same research task three times with three different memory strategies, printing the message count after every addition so the growth is visible.

| Strategy | Behaviour | Tradeoff |
| :-------- | :-------- | :-------- |
| `InstrumentedMemory` | Unbounded — everything accumulates | Simple; breaks at scale |
| `WindowedMemory` | Evicts oldest messages past `window_size` | Bounded cost; loses early context |
| `AutoCompactMemory` | Summarises old messages via LLM when over `threshold` | Preserves meaning; costs one extra LLM call per compaction |

**Key concept**: The context window is the agent's only working memory. All memory management strategies — windowing, compaction, retrieval — are just different ways to decide what stays in that window.

[Walkthrough →](02_context_window_walkthrough.md)

---

### `03_stop_condition.py` — The Stop Condition Problem

Three separate scenarios, each with a different termination mechanism:

1. **Natural stop** — model produces text with no tool calls; loop exits via `break`
2. **Terminal tool** — model must explicitly call `finish()`; `TerminalToolAgent` watches for this call and returns immediately
3. **Step cap** — a permanently broken tool causes infinite retries; `max_steps` is the safety net

**Key concept**: Agents do not stop themselves by default. The loop must decide when to stop. Getting this wrong leads to either premature termination (useful work abandoned) or infinite loops (runaway cost).

[Walkthrough →](03_stop_condition_walkthrough.md)

---

## Core Concepts

### How tool schemas are generated

`ToolRegistry.register(func)` calls `_generate_schema(func)` which:
1. Takes the first line of the docstring as the tool description
2. Maps Python types (`int`, `str`, `list`) to JSON Schema types
3. Parses `:param name: description` lines for parameter descriptions
4. Skips `context` — it is injected at call time and never exposed to the model

The model sees a standard OpenAI-compatible function schema. No manual schema writing needed.

### The context injection pattern

Any tool whose signature includes a `context` parameter receives the live `Agent` instance when called. This gives the tool access to `context.model`, `context.memory`, and `context.registry` — enabling tools that inspect conversation state, spawn sub-agents, or call the model themselves.

### Why max_steps matters

`max_steps` is not a quality constraint — it is a safety net. In normal operation the loop exits naturally (no tool calls) well before the limit. The cap only fires when something goes wrong: an infinite tool loop, a broken external service, or a confused model. Set it high enough to allow complex tasks, low enough to bound cost in failure cases.

---

## How production systems approach these primitives

### Tool registration: auto-schema vs. explicit manifests

This cookbook auto-generates tool schemas from Python type hints and docstrings — you write an ordinary function and the registry infers the JSON contract. Both production systems take a more explicit stance.

**OpenClaw** uses a manifest-first plugin architecture (`manifest.json` per extension). Every tool is declared with an explicit schema, and core is extension-agnostic by design: no tool IDs are hardcoded into core files. Plugins cross into core only through the published `openclaw/plugin-sdk/*` barrel. The constraint driving this is third-party extensibility — explicit manifests mean external plugin authors have a stable, enforced contract.

**Nanobot** uses `SKILL.md` manifests: plain-text files that `ContextBuilder` discovers automatically. Lighter than OpenClaw's JSON manifests, but the same principle: tools are declared separately from the agent loop. The constraint is hackability — Nanobot is designed to be modified by researchers, so SKILL.md files are human-readable and easy to add.

The cookbook's auto-schema approach is right for prototyping and single-developer projects. When third parties write tools or audit trails matter, explicit manifests provide the necessary boundary enforcement.

### Tool permissions: none vs. pipeline vs. config flags

Neither this example nor the base `Agent` class enforces permissions — any registered tool can be called at any time.

**OpenClaw** runs every tool call through a policy pipeline (`tool-policy-pipeline.ts`): allowlist/denylist, sandbox path restriction, optional interactive approval. Each tool can have its own policy override. This is a full decision tree, not a flag, driven by the need to safely expose shell access and file writes to end users on desktop and mobile.

**Nanobot** uses config-gated enable flags: `exec`, filesystem access, and web access are disabled by default. Simpler than OpenClaw's pipeline, appropriate for a single-server deployment where the operator controls who runs the agent.

### Compaction: summarise and preserve vs. drop vs. TTL

This example demonstrates three compaction strategies. Production systems converge on LLM summarisation, but with different triggering logic.

**OpenClaw** (`compaction.ts`) triggers on token limits (soft ~182k, hard ~195k) with up to 3 retry attempts before a circuit breaker fires. Its key differentiator is *identifier preservation* — file paths, function names, and variable names are kept verbatim through compaction. Without this, an agent working in a codebase loses the ability to reference its own prior observations in tool calls.

**Nanobot** uses two separate mechanisms: `AutoCompact` (TTL-based, fires on idle sessions at next request) and `Consolidator` (token-budget-based, fires before each turn, up to 5 rounds). No identifier preservation, but `history.jsonl` provides a cursor-indexed audit trail. The TTL approach is driven by Nanobot's multi-channel architecture — sessions may be inactive for hours between messages, making time-based compaction more natural than turn-based.

### Stop conditions: step cap vs. token budget

This cookbook uses `max_steps` as the primary safety net because it is directly observable and easy to reason about. Production systems prefer token budgets.

**OpenClaw** uses hard/soft token limits as the primary stop mechanism. Step count is secondary, capping tool-calls-per-turn and subagent depth. The constraint is cost predictability: token cost is proportional to actual resource use, whereas step count is not.

**Nanobot** uses `max_iterations` (similar to `max_steps`) as the outer limit, but the `Consolidator` keeps token usage bounded before each turn, so `max_iterations` fires only in pathological cases. Nanobot's approach is the pragmatic middle ground: step cap for simplicity, token awareness for safety.
