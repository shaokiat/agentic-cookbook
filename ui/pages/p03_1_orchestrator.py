from common import about_from, single_run_page

CORE_CONCEPT = """\
**What it is**

A single orchestrator agent owns one tool: `delegate_to_agent`. Calling it spawns a fresh
worker agent with a narrow role and task, runs it to completion, and returns its output as a
tool observation. The orchestrator can call this tool repeatedly — once per subtask — and only
synthesizes a final answer once it has what it needs. From the orchestrator's point of view,
delegation is indistinguishable from calling any other tool.

```mermaid
flowchart TD
    G[Goal] --> O["Orchestrator agent — one tool: delegate_to_agent"]
    O -->|delegate_to_agent role=A| W1["Worker A — empty memory, no tools"]
    W1 -->|return string| O
    O -->|delegate_to_agent role=B| W2["Worker B — empty memory, no tools"]
    W2 -->|return string| O
    O --> S[Synthesize both observations into final answer]
```

**Three deliberate design choices in `delegate_to_agent`**

- **Reuses `context.model`** — the worker shares the orchestrator's `ModelProvider`, so usage
  and cost tracking stay unified instead of fragmenting per worker.
- **Fresh, empty `Memory()`** — a worker cannot see the orchestrator's conversation or any other
  worker's output. This is intentional isolation: workers answer their own subtask only, and the
  orchestrator is the one place synthesis happens.
- **Empty `ToolRegistry()`** — workers can only reason and produce text, not take further
  actions. If a role needs tools, they're registered explicitly for that role, not inherited.

**Why this beats one generalist agent**

A narrowly-scoped worker (system prompt: *"You are a python_specialist..."*) produces denser,
more specific output than one agent asked to reason about several things at once — it isn't
splitting attention across domains. And because delegation runs through the normal tool-call
loop, execution is sequential: one worker finishes before the next is spawned, bounded by the
orchestrator's own `max_steps`. For true concurrent workers, see Parallel Subagents.
"""


single_run_page(
    "Orchestrator / Worker",
    "The orchestrator decomposes the goal and spawns specialist workers via a delegate_to_agent tool; "
    "worker results come back as ordinary observations.",
    "examples/03_multi_agent_systems/01_orchestrator_worker.py",
    builder="build_orchestrator",
    default_prompt_attr="DEFAULT_GOAL",
    about_extra=about_from(CORE_CONCEPT),
)
