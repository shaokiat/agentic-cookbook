# Primitive 2: The Context Window as Working Memory

## What it is

Everything the agent "knows" at any moment is what fits in the context window. This is the agent's only working memory during a run. If something is not in the context, the agent cannot reason about it.

The context window is finite and expensive. Managing it is not optional — it is one of the central engineering problems in production agents.

## Structure of the context window

The context window is a flat list of messages in the standard chat format:

```python
[
    {"role": "system",    "content": "You are a helpful assistant."},
    {"role": "user",      "content": "What files are in this directory?"},
    {"role": "assistant", "content": "Let me check.",  "tool_calls": [...]},
    {"role": "tool",      "content": "README.md\ncore/\nexamples/", "tool_call_id": "call_1"},
    {"role": "assistant", "content": "The directory contains README.md, core/, and examples/."},
]
```

Every token in this list counts against your context budget. As the agent takes more steps, the list grows.

## Implementation in this project

[`core/memory.py`](../../core/memory.py) is a thin wrapper around this list:

```python
class Memory:
    def __init__(self):
        self.messages = []

    def add_message(self, role, content, **kwargs):
        message = {"role": role, "content": content, **kwargs}
        self.messages.append(message)

    def get_messages(self):
        return self.messages
```

The agent passes `memory.get_messages()` to the model on every step. The model sees the entire history each time — this is how it maintains coherence across turns.

## What fills the context window

| Message type | Role | Grows with |
| :----------- | :--- | :--------- |
| System prompt | `system` | Fixed (written once) |
| User input | `user` | Number of user turns |
| Model reasoning | `assistant` | Steps taken |
| Tool call requests | `assistant` + `tool_calls` | Tools called per step |
| Tool results | `tool` | Tools called, output size |

Tool results are often the biggest consumer. A tool that returns a large file or a long web page can consume thousands of tokens in a single step.

## The growth problem

After N steps, the context looks like this:

```text
[system] [user] [assistant+tool_call] [tool] [assistant+tool_call] [tool] ... [assistant]
  fixed   fixed   step 1               step 1   step 2              step 2
```

With a 200k token limit and tool outputs averaging 1k tokens, you can fit roughly 200 steps before hitting the limit — less if outputs are large or the model is verbose.

## Strategies to manage context growth

### 1. Auto-snip (sliding window)

Keep only the last N messages, always preserving the system prompt. Already implemented in [`examples/02_memory_management/01_windowed_memory.py`](../02_memory_management/01_windowed_memory.py).

```python
class WindowedMemory(Memory):
    def __init__(self, window_size=10):
        super().__init__()
        self.window_size = window_size

    def add_message(self, role, content, **kwargs):
        super().add_message(role, content, **kwargs)
        if len(self.messages) > self.window_size + 1:
            # Keep system prompt (index 0) + last N messages
            self.messages = [self.messages[0]] + self.messages[-self.window_size:]
```

**Trade-off**: The agent loses awareness of early steps. If a key observation from step 2 was evicted and step 15 depends on it, the agent will fail or hallucinate.

### 2. Auto-compact (summarization)

Replace old messages with a model-generated summary before they are evicted. The summary is injected back as a `system` or `assistant` message. Claude Code triggers this automatically at ~95% context usage or via the `/compact` command.

The summary prompt is engineered to preserve what matters: tool call results, decisions made, and open tasks — not just prose.

```python
# Pseudocode
if token_count(memory) > THRESHOLD:
    old_messages = memory.messages[1:-RECENT_N]
    summary = model.generate([
        {"role": "user", "content": (
            "Summarize these steps. Preserve: tool results, decisions made, open tasks.\n"
            f"{old_messages}"
        )}
    ])
    memory.messages = [memory.messages[0], summary] + memory.messages[-RECENT_N:]
```

**Trade-off**: Adds latency and costs tokens. The summary may lose details that later matter.

### 3. Output truncation

Truncate or post-process tool results before adding them to memory:

```python
result = registry.call_tool(name, args)
if len(result) > MAX_OUTPUT_TOKENS:
    result = result[:MAX_OUTPUT_TOKENS] + "\n[output truncated]"
memory.add_message("tool", result, ...)
```

### 4. Token budget signaling (proactive)

The only *proactive* strategy — instead of reacting to overflow, you signal the model how much budget remains so it self-regulates verbosity before hitting the limit.

Inject a running token count into the system prompt each turn:

```python
remaining = MAX_TOKENS - token_count(memory.get_messages())
system_msg = (
    f"{BASE_SYSTEM_PROMPT}\n\n"
    f"Remaining context budget: {remaining} tokens. "
    "Be concise in reasoning and tool calls."
)
```

Claude Code implements this in `token_budget.py`, which updates the budget message every turn and tightens the instruction as the budget shrinks.

**Trade-off**: The model may become overly terse too early if the budget message is too aggressive. Calibrate the threshold at which you start warning.

## Failure modes

- **Context overflow**: The message list exceeds the model's token limit. The API returns an error. Claude Code handles this with *reactive compaction*: on a `prompt_too_long` error it auto-compacts the history and retries transparently. Without this, the agent crashes.
- **Lost observations**: With auto-snip, evicted tool results cause the model to re-derive or hallucinate information it already obtained.
- **Repetitive loops**: When the agent can't see its earlier attempts, it may re-call the same tool with the same arguments repeatedly.

## Running the example

```bash
python examples/00_primitives/02_context_window.py
```

The example runs two agents back-to-back — unbounded memory vs. windowed memory — and prints message count and character size after every `add_message` call via `InstrumentedMemory`:

```python
class InstrumentedMemory(Memory):
    def add_message(self, role, content, **kwargs):
        super().add_message(role, content, **kwargs)
        total_chars = sum(len(str(m.get("content", ""))) for m in self.messages)
        print(f"  [Memory] {len(self.messages)} messages | ~{total_chars} chars in context")
```

To also print each message's role and a content snippet, set `SHOW_FULL_CONTEXT=1`:

```bash
SHOW_FULL_CONTEXT=1 python examples/00_primitives/02_context_window.py
```
