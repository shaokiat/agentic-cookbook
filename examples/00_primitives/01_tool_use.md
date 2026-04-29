# Primitive 1: Tool Use / Function Calling

## What it is

Tool use is the mechanism by which a language model emits a structured request to call an external function, then receives the result back as an observation. It is the foundation of all agentic behavior — without it, the model can only generate text.

The critical insight: **the model does not execute tools. It requests them.** Your loop executes them.

## How it works

### 1. Define a tool as a plain Python function

```python
def get_weather(city: str, unit: str = "celsius") -> str:
    """
    Get the current weather for a city.
    :param city: The city to get weather for.
    :param unit: Temperature unit, either 'celsius' or 'fahrenheit'.
    """
    # ... call a weather API ...
    return f"The weather in {city} is 22°{unit[0].upper()}"
```

### 2. The ToolRegistry generates a JSON schema automatically

[`core/registry.py`](../../core/registry.py) uses Python's `inspect` and `get_type_hints` to convert the function into an OpenAI-compatible schema:

```json
{
  "type": "function",
  "function": {
    "name": "get_weather",
    "description": "Get the current weather for a city.",
    "parameters": {
      "type": "object",
      "properties": {
        "city": { "type": "string", "description": "The city to get weather for." },
        "unit": { "type": "string", "description": "Temperature unit, either 'celsius' or 'fahrenheit'." }
      },
      "required": ["city"]
    }
  }
}
```

The `required` list is populated automatically: parameters with no default value are required; parameters with defaults (like `unit = "celsius"`) are optional.

### 3. The schema is sent to the model alongside the messages

```python
response = model.generate(
    messages=memory.get_messages(),
    tools=registry.get_schemas()   # <-- model sees the schema, not the function
)
```

The model reads the schema and decides whether to call a tool. If it does, it returns a **tool call object** — structured JSON describing which function to call and with what arguments:

```json
{
  "id": "call_abc123",
  "type": "function",
  "function": {
    "name": "get_weather",
    "arguments": "{\"city\": \"Singapore\", \"unit\": \"celsius\"}"
  }
}
```

### 4. Your loop executes the tool and feeds the result back

```python
if response.tool_calls:
    for tool_call in response.tool_calls:
        result = registry.call_tool(
            tool_call["function"]["name"],
            tool_call["function"]["arguments"]
        )
        memory.add_message("tool", str(result), tool_call_id=tool_call["id"])
```

The result is added to the conversation as a `tool` role message. On the next iteration the model sees it as an observation and can reason about it.

### Full request/response cycle

```text
User message
    │
    ▼
Model (sees messages + tool schemas)
    │
    ├─► Text response only  ──────────────────► Final answer
    │
    └─► Tool call response
            │
            ▼
        Your loop executes the Python function
            │
            ▼
        Result added to memory as "tool" message
            │
            ▼
        Model (sees original messages + tool result)
            │
            └─► ... repeat ...
```

## Context injection

If a tool function includes a `context` parameter, the registry injects the agent instance automatically — stripped from the JSON schema, so the model never sees or supplies it.

### The key line: `agent.py:97`

```python
result = self.registry.call_tool(tool_name, tool_args, context=self)
```

`self` is the `Agent` instance. Every tool call passes the whole agent in. Whether the tool *uses* it depends on whether it has a `context` parameter.

### Case 1: Normal tool — no `context` parameter

```python
def add(a: int, b: int) -> int:
    """Add two integers together."""
    return a + b
```

**Schema generation** (`registry.py:44-60`): iterates `a`, `b` — neither is `"context"`, so both appear in the JSON schema sent to the model.

**Execution** (`registry.py:102-104`): `"context" not in sig.parameters` → nothing injected. Called as `add(a=3, b=4)`.

Model sees:
```json
{ "name": "add", "parameters": { "a": ..., "b": ... } }
```

### Case 2: Context-injected tool

```python
def summarize_history(context) -> str:
    """Summarize the current conversation history."""
    messages = context.memory.get_messages()
    return f"Conversation has {len(messages)} messages."
```

**Schema generation** (`registry.py:45-47`): hits `if param_name == "context": continue` — skipped entirely.

Model sees:
```json
{ "name": "summarize_history", "parameters": {} }
```

The model calls it with empty arguments: `arguments = "{}"`.

**Execution** (`registry.py:102-104`):
```python
sig = inspect.signature(func)
if "context" in sig.parameters:
    args["context"] = context   # context = the Agent instance
```

So it becomes `func(context=agent)`, giving the function access to `agent.memory`, `agent.model`, `agent.registry`, etc.

### What `context` unlocks

Because `context` is the `Agent` instance, a tool can reach anything on it:

```python
def get_step_count(context) -> str:
    """Tell the user how many steps have been used so far."""
    tool_messages = [m for m in context.memory.get_messages() if m["role"] == "tool"]
    return f"{len(tool_messages)} tool calls made so far."

def reset_memory(context) -> str:
    """Clear conversation history and start fresh."""
    context.memory.messages = []   # mutates agent state directly
    return "Memory cleared."

def call_subagent(query: str, context) -> str:
    """Spin up a sub-agent using the same model and registry."""
    sub = Agent(model=context.model, memory=Memory(), registry=context.registry)
    return sub.run(query)   # agent spawning another agent
```

Notice `call_subagent` mixes both: `query` appears in the schema (model-supplied), `context` does not (runtime-injected).

### The flow side by side

```
Normal tool                          Context-injected tool
─────────────────────────────────    ──────────────────────────────────────
Model supplies all args              Model supplies non-context args only
  arguments = {"a": 3, "b": 4}        arguments = "{}"  (or {"query": "..."})

registry.call_tool(name, args,       registry.call_tool(name, args,
    context=self)                         context=self)
  → "context" not in sig               → "context" in sig
  → func(a=3, b=4)                     → args["context"] = agent
                                        → func(context=agent)
                                          or func(query="...", context=agent)
```

The pattern cleanly separates **what the model decides** (tool arguments) from **what only the runtime knows** (live agent state).

## Failure modes

- **Hallucinated arguments**: The model may supply argument values that don't exist (e.g., an invalid file path). Always validate or handle errors in the tool implementation and return the error string as the observation — let the model reason about it and retry.
- **Wrong tool selected**: If tool descriptions are ambiguous or overlap, the model may call the wrong one. Write precise, distinct docstrings.
- **Infinite tool loop**: If a tool call always fails and the model keeps retrying, the agent loops until `max_steps`. The stop condition (Primitive 3) is your safety net.

## Areas to explore further

Context injection via `context=self` is convenient but passes a wide-open handle to the agent. The following security concerns are worth revisiting in a dedicated exploration:

- **Unrestricted registry access** — any context-injected tool can call `context.registry.call_tool()` directly, bypassing the model loop with no logging or step counting. Worth exploring: an allowlist of which tools are permitted to receive context.
- **Memory tampering** — tools can silently read or mutate `context.memory.messages`, poisoning the model's context window for subsequent reasoning. Worth exploring: passing a read-only memory snapshot to tools that only need to inspect history.
- **Prompt injection via tool results** — external content fetched by a tool (webpages, files) lands in memory as an observation. A malicious payload could instruct the model to invoke destructive context-injected tools. Worth exploring: sanitizing external content before it enters memory.
- **Subagent resource amplification** — `call_subagent` reuses `context.model` (same API credentials) with no recursion limit. Worth exploring: tracking recursion depth on the agent and refusing to spawn beyond a threshold.

## Running the example

```bash
python examples/00_primitives/01_tool_use.py
```
