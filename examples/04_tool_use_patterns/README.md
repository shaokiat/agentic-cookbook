# 04 Tool Use Patterns

Advanced patterns for how agents interact with the world. These examples assume
you have completed `00_primitives/01_tool_use.py` and understand the basic
tool execution lifecycle.

---

## Concept Ladder

| Level | Pattern | File |
| :---- | :------ | :--- |
| 1 | Block on user confirmation before running a destructive action | `01_human_approval.py` |
| 2 | Dispatch multiple tool calls in one turn concurrently | `02_parallel_tool_calls.py` |
| 3 | Retry flaky tools; agent reasons around persistent failures | `03_error_recovery.py` |
| 4 | Load tools at runtime by capability or auto-discovery | `04_dynamic_tools.py` |

---

## Examples

### `01_human_approval.py` — Human-in-the-Loop (HIL)

Destructive tools (`delete_file`, `write_file`) are marked `@dangerous`. Before
executing a marked tool, `ApprovalAgent._act` yields an `approval_request` event
and the loop pauses until the surrounding UI answers via `generator.send(bool)`.
If denied, the tool never runs and a refusal string becomes the observation.

```
Agent proposes action
    │
    ▼
_act() sees requires_approval ──► yield approval_request ──► UI asks (terminal Confirm / web buttons)
    │
    ├─ send(True)  ──► tool executes ──► result as observation
    └─ send(False) ──► "Action denied" ──► agent finds alternative
```

**Key insight**: approval is loop policy, not tool internals. The tools stay
pure; the gate lives in the tool-execution step, and any frontend — terminal
or web — decides how to ask. Denial still arrives as an ordinary observation,
so the model's view is unchanged.

**When to use**: Irreversible operations (file deletion, API mutations, payments,
shell commands).

**Reference**: pi-coding-agent tiered permission system (`--allow-write`,
`--allow-shell`). OpenClaw `permissions.py` four-tier safe-by-default model.

---

### `02_parallel_tool_calls.py` — Concurrent Tool Dispatch

When the model returns multiple tool calls in one response, the default `Agent`
executes them sequentially. `ParallelAgent` overrides the execution step to
dispatch the full batch via `ThreadPoolExecutor`, then assembles results before
the next model turn — preserving the protocol while cutting wall-clock time.

```
Model response: [tool_a, tool_b, tool_c]   (one response, three calls)
    │
    ▼  ParallelAgent dispatches concurrently
    ├── tool_a ──┐
    ├── tool_b ──┼── (concurrent) ──► assemble results ──► next model turn
    └── tool_c ──┘
```

**Key insight**: the speedup requires no prompt changes. The model already
groups independent tool calls. You only change the executor, not the protocol.

**When to use**: Tools with independent I/O (network calls, database reads).
Do NOT use for tools with data dependencies between them.

**Reference**: OpenClaw `pi-embedded-subscribe.ts` dispatches all tool calls
in a response concurrently. Nanobot `concurrent_tools=True` in `AgentRunner`.

---

### `03_error_recovery.py` — Two-Layer Error Handling

```
fetch_stock_price()  ← fails ~60% of the time
    │
    Layer 1: @with_retry(max_attempts=3)
    │   ├── attempt 1 fails → wait 0.3s
    │   ├── attempt 2 fails → wait 0.6s
    │   └── attempt 3 fails → return "Error after 3 attempts: ..."
    │
    Layer 2: Agent reasoning
        ├── sees error string as tool observation
        └── calls fetch_cached_price() or get_market_summary() as fallback
```

**Key insight**: return error strings, don't raise exceptions out of tools.
The agent can reason about a string; an uncaught exception terminates the turn.

**When to use**: External APIs, network calls, or any tool that can fail for
reasons outside your control.

---

### `04_dynamic_tools.py` — Runtime Tool Loading

Two patterns for choosing which tools the model sees:

**Pattern A — Capability-scoped**: build a `ToolRegistry` per task by selecting
only the relevant tool subsets. Shorter schema lists = fewer prompt tokens +
less model confusion.

```python
registry = build_registry_for(["research", "code"])  # not "data" or "communication"
```

**Pattern B — Plugin discovery**: mark functions with `@agent_tool`. A scanner
walks the namespace and auto-registers everything marked, so adding a new tool
requires no manual registry calls.

```python
@agent_tool
def my_new_tool(x: str) -> str: ...
# discovered and registered automatically on next scan
```

**When to use**: A — large tool libraries where exposing everything degrades
quality. B — extensible systems where tools are added by third parties or at
deploy time.

**Reference**: pi-coding-agent `Skills`, `Extensions`, and `Pi Packages` all
use manifest-driven discovery. OpenClaw `plugin.json` registers tools via hooks.

---

## Core Concepts

### Why return errors as strings?

The agent loop in `core/agent.py` already wraps tool execution in a try/except
and converts exceptions to `"Error: ..."` strings. But if your tool raises an
exception after doing partial work, the agent may not know what succeeded. An
explicit error string lets you encode partial results:

```python
return f"Fetched 3 of 5 records before timeout. Partial data: {partial}"
```

### Tool schemas and model confusion

The model chooses tools by name and description in the schema. Registering
too many irrelevant tools increases the chance of the wrong tool being called.
Pattern A (capability-scoped loading) addresses this directly.

### Thread safety

`ModelProvider` wraps `litellm.completion()` which is thread-safe.
`Memory` is **not** thread-safe — each agent needs its own instance.
`ToolRegistry` is read-only after registration and safe to share across threads.

---

## How Production Systems Approach This

### HIL and permission tiers

pi-coding-agent implements HIL as a global permission tier system. Tools are
tagged with a risk level (`always`, `write`, `shell`, `unsafe`). The runner
checks the tier before dispatch — no HIL code inside each tool. The
`@dangerous` marker + loop gate in `01_human_approval.py` is the same idea at
its smallest: a boolean tier and a single check in the dispatch step.

### Parallel dispatch at the framework level

Both OpenClaw and Nanobot move parallel dispatch into the core loop rather than
into a subclass. OpenClaw's `pi-embedded-subscribe.ts` wraps every tool call
batch in `Promise.all()`. `ParallelAgent` in `02_parallel_tool_calls.py`
achieves the same effect by overriding `_execute_tool_calls` — the minimal
change needed without modifying the shared `Agent` base.

### Dynamic tool loading and MCP

pi-coding-agent supports MCP (Model Context Protocol) servers as an external
tool source: the agent connects to an MCP server over stdio transport, fetches
its tool schema list at startup, and registers them dynamically. This is
Pattern B taken to its logical conclusion — tools live in separate processes
and are discovered at runtime via a standard protocol.
