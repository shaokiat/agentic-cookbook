from common import about_from, single_run_page

CORE_CONCEPT = """\
**What it is**

Tool use is the mechanism by which a language model emits a structured *request* to call an
external function, then receives the result back as an observation. It's the foundation of all
agentic behavior — without it, the model can only generate text.

The critical insight: **the model never executes tools, it only requests them.** Your agent
loop is what actually runs the Python function.

**Characteristics of defining a tool**

A tool is just a plain Python function — no special base class or decorator required. The
registry reads its signature to build a schema for the model:

- The function's **docstring** becomes the tool's description.
- `:param name: ...` lines in the docstring become each parameter's description.
- **Type hints** (`str`, `int`, ...) become the JSON schema parameter types.
- Parameters with **no default value** are marked `required`; parameters **with a default**
  are optional.
- A parameter literally named `context` is handled specially — see below — and is stripped out
  of what the model ever sees.

**How the agent reads and uses it**

Every turn, the registry converts each registered function into an OpenAI-compatible JSON
schema and sends all of them to the model alongside the conversation. The model decides, purely
from those schemas and docstrings, whether to answer in plain text or emit a tool call (a
function name plus JSON arguments). Your loop looks up that function, calls it with the
model-supplied arguments, and appends the return value back into memory as a `tool`-role
message. On the next turn the model sees that result as an observation and keeps reasoning —
this request → execute → observe cycle repeats until the agent stops.

```mermaid
flowchart TD
    A[User message] --> B{Model sees messages + tool schemas}
    B -->|Text response only| C[Final answer]
    B -->|Tool call| D[Loop executes the Python function]
    D --> E[Result added to memory as a tool message]
    E --> B
```

**Context injection — giving a tool access to live agent state**

If a tool's signature includes a parameter named `context`, the registry silently strips it
from the schema the model sees, and injects the live `Agent` instance when the function is
called. That lets a tool reach `agent.memory`, `agent.model`, `agent.registry` — summarizing
history, clearing memory, even spawning a sub-agent — without the model ever knowing that
capability exists. Every other parameter on the same function still comes from the model as
normal; only `context` is carved out.

```mermaid
flowchart LR
    subgraph Normal tool
    N1[Model supplies all arguments] --> N2[registry.call_tool] --> N3["func(a, b, ...)"]
    end
    subgraph Context-injected tool
    C1[Model supplies non-context arguments only] --> C2["registry.call_tool(context=agent)"] --> C3["func(..., context=agent)"]
    end
```

This cleanly separates **what the model decides** (tool arguments) from **what only the
runtime knows** (live agent state).

**Failure modes to keep in mind**

Hallucinated arguments (the model supplies a value that doesn't exist, e.g. a bad file path),
ambiguous tool descriptions causing the wrong tool to be picked, and infinite retry loops if a
tool keeps failing — the stop condition is the safety net for that last one.
"""


single_run_page(
    "Tool Use",
    "The full tool-use lifecycle: plain functions → auto-generated schemas → model-driven calls.",
    "examples/00_primitives/01_tool_use.py",
    about_extra=about_from(CORE_CONCEPT),
)
