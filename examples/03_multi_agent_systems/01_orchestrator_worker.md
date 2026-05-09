# Orchestrator-Worker Pattern: Walkthrough

This document walks through `examples/03_multi_agent_systems/01_orchestrator_worker.py` — its mechanics, what happened during a real execution, and the design decisions behind it.

---

## What it does

A single orchestrator agent receives a high-level goal. It has one tool: `delegate_to_agent`. When called, the tool spawns a fresh worker agent with a specific role and task, runs it to completion, and returns the result as a tool observation. The orchestrator can call this tool multiple times — once per subtask — and then synthesise the collected worker outputs into a final answer.

The goal given:

> *"Compare Python and Go as backend languages. Delegate research on each language to separate specialists, then synthesize a concise comparison covering performance, ecosystem, and ideal use cases."*

---

## Execution trace

### Step 1 — Orchestrator reasons about the goal

The orchestrator received the user message and decided to delegate before producing any output text. It immediately issued the first tool call:

```
Tool Call: delegate_to_agent({
  "role": "python_specialist",
  "task": "Research Python as a backend language focusing on its performance, ecosystem, and ideal use cases."
})
```

No intermediate "planning" text was printed. The model went straight to action. This is characteristic of a well-specified system prompt — the instruction *"delegate each subtask to a specialist worker"* was clear enough that no preamble was needed.

### Step 2 — Python specialist runs

A fresh `Agent` was created with:
- `system_prompt`: `"You are a python_specialist. Complete the assigned task thoroughly and concisely."`
- Empty `Memory` (no context from the orchestrator's session)
- Empty `ToolRegistry` (no tools — this worker only reasons, it does not act)

The worker produced a structured report covering three areas:

**Performance**: noted the GIL as a CPU-bound bottleneck; highlighted `asyncio`, PyPy, and Cython as mitigation paths.

**Ecosystem**: Django and Flask for web; Pandas/NumPy for data; PyPI's breadth; strong cross-language integration via SQLAlchemy, PyMongo.

**Ideal use cases**: web development, data science/ML (TensorFlow, PyTorch), automation/scripting, IoT, rapid prototyping.

The worker's full output was returned to the orchestrator as a tool observation — it landed in the orchestrator's context exactly like any other tool result.

### Step 3 — Orchestrator issues the second delegation

Without producing any assistant text, the orchestrator immediately called `delegate_to_agent` again:

```
Tool Call: delegate_to_agent({
  "role": "go_specialist",
  "task": "Research Go as a backend language focusing on its performance, ecosystem, and ideal use cases."
})
```

This is the key behavioral property of the pattern: **the orchestrator treats delegation like any other tool call**. It accumulates observations and defers synthesis until it has what it needs.

### Step 4 — Go specialist runs

A second fresh `Agent` was created with `"You are a go_specialist."` and a clean context.

The worker reported:

**Performance**: goroutines for native concurrency without the GIL; fast compilation to machine code; efficient garbage collector with low pause times; minimal syntax reducing runtime errors.

**Ecosystem**: strong standard library reducing third-party dependence; go toolchain (GoDoc, GoLint, GoTest); statically linked binaries ideal for containers; backing from Docker and Kubernetes.

**Ideal use cases**: web servers/REST APIs (Echo, Gin); microservices; networking tools; cloud/DevOps tooling (Terraform); CLI tools.

### Step 5 — Orchestrator synthesises

With both observations in its context, the orchestrator produced its final assistant message — a structured comparison across the three dimensions it was asked to cover:

| Dimension | Python | Go |
|:----------|:-------|:---|
| Performance | Interpreted; GIL limits CPU threads; asyncio for I/O concurrency | Compiled; goroutines for native concurrency; minimal GC pauses |
| Ecosystem | Largest third-party library count; dominant in data science/ML | Strong stdlib; excellent toolchain; preferred for cloud-native infra |
| Ideal use cases | Web apps, data science, AI, scripting, prototyping | Microservices, APIs, networking, cloud infra, CLI tools |

No additional tool calls were made. The orchestrator stopped after synthesising.

---

## How the code works

### The `delegate_to_agent` tool

```python
def delegate_to_agent(role: str, task: str, context) -> str:
    worker = Agent(
        model=context.model,      # reuse parent's ModelProvider
        memory=Memory(),          # fresh context — no cross-contamination
        registry=ToolRegistry(),  # no tools — workers only reason
        system_prompt=f"You are a {role}. ...",
        name=role.capitalize(),
        verbose=False,
    )
    return worker.run(task)
```

Three design decisions here:

**`context.model`** — The worker reuses the orchestrator's `ModelProvider` instead of creating a new one. This shares the same model configuration and usage tracking. The `context` argument is injected automatically by `ToolRegistry.call_tool()` when the function signature includes it.

**`Memory()`** — Each worker gets a completely empty memory. There is no way for a worker to read the orchestrator's conversation history or the other worker's output. This is intentional: workers are scoped to their subtask. The orchestrator synthesises across workers; the workers themselves do not need to know about each other.

**`ToolRegistry()`** — Workers have no tools. They can only reason and produce text. Giving workers tools would let them take actions the orchestrator didn't explicitly sanction. If a worker needs tools, they should be registered explicitly for that role.

### Why tool observations are the right delivery channel

Worker results return via `return worker.run(task)`. From the orchestrator's perspective, this is indistinguishable from any other tool result — it arrives as a `tool` role message in memory. The orchestrator's loop processes it the same way it would process the output of a file-read or a web search.

This means the orchestrator doesn't need special multi-agent awareness. It just uses tools.

### The orchestrator's tool call sequence

The orchestrator called `delegate_to_agent` twice sequentially, not in parallel. This is because the underlying `Agent.run()` loop dispatches tool calls one turn at a time — each call blocks until the worker finishes. If the orchestrator had issued both delegations in the same response (which LLMs can do if prompted), they would still execute sequentially here. For true parallel execution, see `02_parallel_subagents.py`.

---

## What the execution reveals about the pattern

### The orchestrator adds genuine value

The orchestrator did not simply concatenate the two worker reports. It restructured them into a side-by-side comparison organised by the three dimensions the user asked for. This is the synthesis step — the orchestrator's contribution beyond coordination.

A naive implementation that just concatenated results would produce a longer output but not a better one.

### Workers produce more focused output than a single agent

Each specialist worker had a narrow role and a focused task. The Python specialist's report was denser and more specific than what a general-purpose agent asked to "compare Python and Go" typically produces — because it wasn't also thinking about Go.

Narrow system prompts outperform general ones for specific domains. This is the core justification for specialisation over a single large context.

### Context isolation prevents cross-contamination

Because each worker has an empty memory, the Go specialist cannot be influenced by what the Python specialist said, and vice versa. For a comparison task this is desirable — you want independent assessments, not Go's section quietly echoing Python's framing.

Context isolation is a feature here, not a limitation. If workers needed to build on each other's outputs, you would chain them explicitly (see `03_sequential_pipeline.py`).

### Tool depth is bounded by the orchestrator's max_steps

The orchestrator was configured with `max_steps=10`. Each `delegate_to_agent` call consumes one step (the tool call) plus one step when the orchestrator produces its final text. With two workers, four steps were used. Had the orchestrator decided to delegate three or four subtasks, it would still complete within the limit.

For tasks requiring many delegations, increase `max_steps` proportionally or add a depth limit inside `delegate_to_agent` itself — the equivalent of OpenClaw's `subagent-depth.ts`.

---

## Tradeoffs

| Property | This pattern | Alternative |
|:---------|:-------------|:------------|
| Execution order | Sequential — one worker at a time | Parallel — see `02_parallel_subagents.py` |
| Worker awareness | Workers are isolated; cannot see each other | Chain workers explicitly for dependent tasks |
| Orchestrator control | LLM decides what to delegate and when | Pre-define the delegation plan (plan-and-execute) |
| Worker tools | None by default | Register tools per role for agentic workers |
| Result delivery | Synchronous tool return | Async queue — see `04_async_announce.py` |

---

## Extensions

**Give workers tools**: Change `registry=ToolRegistry()` in `delegate_to_agent` to a registry with specific tools (e.g., web search for a researcher). The orchestrator's tool call is identical; the worker gains the ability to take actions.

**Add depth limiting**: Track delegation depth via a counter in the context and raise an exception in `delegate_to_agent` when a threshold is exceeded. This prevents an orchestrator from spawning a worker that spawns further workers unboundedly.

**Dynamic role generation**: The orchestrator can invent role names on the fly (`"database_schema_expert"`, `"security_reviewer"`) based on the task. The worker's behaviour is shaped entirely by the role string in its system prompt — no code changes needed.

**Parallel delegation**: Wrap the sequential loop in `ThreadPoolExecutor` to run multiple `delegate_to_agent` calls concurrently. See `02_parallel_subagents.py` for the full implementation of this pattern.

---

_Example_: `01_orchestrator_worker.py`  
_Reference architectures_: `../../docs/reference_architectures.md` — OpenClaw `subagent-registry.ts`, Nanobot `SubagentManager`
