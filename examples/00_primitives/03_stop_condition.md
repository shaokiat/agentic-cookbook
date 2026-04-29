# Primitive 3: The Stop Condition Problem

## What it is

How does an agent know it is done? Without a clear termination signal, agents loop indefinitely or stop prematurely. Every agent loop needs an explicit stop condition.

This is not a minor implementation detail — it is a correctness requirement. An agent with no stop condition will run until it exhausts the context window, the token budget, or the patience of whoever is paying the bill.

## Three kinds of stop conditions

### 1. Step cap (`max_steps`)

The simplest guard. The loop exits after a fixed number of iterations regardless of what the agent has done.

```python
steps = 0
while steps < self.max_steps:
    steps += 1
    response = model.generate(...)
    if not response.tool_calls:
        break  # natural stop — model is done
# loop exits here even if the agent never broke naturally
```

In [`core/agent.py`](../../core/agent.py), `max_steps=10` is the default. It is a last-resort safety net, not the primary stop mechanism.

**Trade-off**: Too low and the agent gives up on hard tasks. Too high and a stuck agent burns tokens. There is no universal right value — set it per task.

### 2. Terminal tool call

The agent signals completion by calling a designated "done" tool instead of stopping mid-sentence. The loop exits when it sees this call.

```python
def finish(answer: str) -> str:
    """Signal that the task is complete and return the final answer."""
    return answer

registry.register(finish)

# In the agent loop:
for tool_call in response.tool_calls:
    if tool_call["function"]["name"] == "finish":
        return registry.call_tool("finish", tool_call["function"]["arguments"])
```

This is more reliable than detecting "no tool call" because it forces the model to make an explicit, structured decision to stop.

### 3. Model-emitted stop signal

The model stops calling tools and emits a plain text response. The loop interprets the absence of tool calls as a completion signal:

```python
if response.tool_calls:
    # ... execute tools, continue loop ...
    continue
else:
    break  # no tool calls → agent is done reasoning
```

This is the default stop mechanism in this project. It works well for conversational tasks but can be fragile: the model may stop early if it is not sure what to do next, even if the task is incomplete.

## How these compose

In [`core/agent.py`](../../core/agent.py) all three mechanisms are active simultaneously:

```python
steps = 0
while steps < self.max_steps:          # guard 1: step cap
    steps += 1
    response = model.generate(...)

    if response.tool_calls:
        for tool_call in response.tool_calls:
            if tool_call["function"]["name"] == "finish":  # guard 2: terminal tool
                return handle_finish(tool_call)
            result = registry.call_tool(...)
            memory.add_message("tool", result, ...)
        continue
    else:
        break                          # guard 3: no tool call → natural stop

return memory.get_messages()[-1]["content"]
```

The natural stop (guard 3) handles the happy path. The step cap (guard 1) handles infinite loops. The terminal tool (guard 2) handles tasks where explicit confirmation is required.

## Failure modes

- **Premature stop**: The model emits a text response mid-task when it should have called another tool. Often caused by an ambiguous or too-permissive system prompt.
- **Infinite tool loop**: The model keeps calling the same failing tool. The step cap prevents a crash but the agent's final output will be incomplete.
- **Silent truncation**: The agent hits `max_steps` but the caller receives whatever the last message was, with no indication that the task was cut short. Always check whether the loop exited via `break` (natural stop) or ran to `max_steps`.

```python
if steps >= self.max_steps:
    # log or raise a warning — the agent may not have finished
    logger.warning(f"Agent hit max_steps={self.max_steps} without a natural stop.")
```

## Choosing `max_steps`

| Task type | Suggested `max_steps` |
| :-------- | :-------------------- |
| Simple Q&A with 1-2 tool calls | 5 |
| Multi-step research | 15–20 |
| Code generation + verification loop | 20–30 |
| Open-ended planning | 30–50 (with cost monitoring) |

## Running the example

```bash
python examples/00_primitives/03_stop_condition.py
```

Each scenario runs a separate agent in sequence.

### Scenario 1: Natural stop

```
=== Scenario 1: Natural Stop ===
The model calls one tool then returns a text answer.

User: What is the capital of Japan?
Tool Call: lookup_capital({"country":"Japan"})
Observation: Tokyo
Assistant: The capital of Japan is Tokyo.

Stopped after 5 messages in context.
Stop reason: natural (no tool calls on final step)
```

The model calls one tool, receives the result, and emits a plain text answer. The loop hits the `else: break` path — no `finish()` needed.

### Scenario 2: Terminal tool call

```
=== Scenario 2: Terminal Tool Call ===
The model must explicitly call finish() to signal completion.

  Tool: search  →  No results found.
  ...
Final answer: No results found.
```

This run also demonstrates a **failure mode**: the model's search queries don't match the tool's hardcoded keys, so every call returns "No results found." The agent exhausts `max_steps=8` and falls through without ever calling `finish()` — the fallback returns the last message instead. In production, this would surface as a degraded answer with no explicit stop signal. Fix: either broaden the search tool's data or tune the system prompt to guide query format.

### Scenario 3: Step cap

```
=== Scenario 3: Step Cap (Safety Net) ===
A broken tool causes the agent to loop. max_steps prevents infinite execution.

Tool Call: broken_tool({"input":"hello"})
Observation: Error: Service unavailable. Please try again later.
Assistant: It seems there was an error with the broken_tool. I'll try again.
Tool Call: broken_tool({"input":"hello"})
Observation: Error: Service unavailable. Please try again later.
...
Reached max steps safety limit.

Agent stopped after hitting max_steps=3.
Total messages in context: 10
Last message: Error: Service unavailable. Please try again later.
```

The broken tool always raises. The model retries every step until `max_steps=3` is hit. The final message is the last tool error, not a real answer — illustrating the **silent truncation** failure mode: the caller gets *something* back but it is not a valid result.
