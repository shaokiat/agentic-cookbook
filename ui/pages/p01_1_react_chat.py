from common import about_from, chat_page

CORE_CONCEPT = """\
**What it is**

ReAct (Reasoning and Acting) lets the model "think" about a problem, "act" by calling a tool,
then "observe" the result before continuing to reason — looping until it has enough information
to give a final answer. This Think → Act → Observe cycle is the base loop every other pattern
in this cookbook builds on.

```mermaid
flowchart TD
    Q[User question] --> T["Think — model sees messages + tool schemas"]
    T --> D{Tool call issued?}
    D -->|Yes| A["Act — registry executes the tool"]
    A --> O["Observe — result added to memory"]
    O --> T
    D -->|No| F[Final answer]
```

**Sequence view of the same loop**

```mermaid
sequenceDiagram
    participant User
    participant Agent
    participant Model
    participant Tools

    User->>Agent: Run(question)
    loop until Max Steps or Final Answer
        Agent->>Model: Think (Messages + Tool Schemas)
        Model-->>Agent: LLM Response (Thought + Tool Calls)

        alt Tool Call Present
            Agent->>Tools: Execute Tool
            Tools-->>Agent: Observation (Result)
            Agent->>Agent: Add Observation to Memory
        else No Tool Call
            Agent-->>User: Final Answer
        end
    end
```

**The Think-Act-Observe cycle**

1. **Think** — the agent sends the conversation history and available tool schemas to the
   model. The model returns a response that may include reasoning text and a list of tool calls.
2. **Observe (partial)** — any text content in that response is added to memory immediately.
3. **Act** — if the model issued tool calls, the agent executes each one through the
   `ToolRegistry` and captures its output as an observation.
4. **Repeat** — the observation goes back into memory as a `tool`-role message, and the loop
   returns to Think. The model now sees its previous thought, the action it took, and the
   result — and reasons from there.

**How the agent decides and where the calling actually happens**

The agent never hardcodes which tool to call. The `ToolRegistry` converts every registered
Python function into a JSON schema and sends all of them to the model alongside the message
history. The model compares the user's intent against the tool descriptions and, if it finds a
match, returns a structured tool-call object (name + arguments) — a decision, not an action.
The actual Python function invocation happens back in the agent loop, not inside the model or
the `ModelProvider`: the agent takes that name and those arguments and hands them to the
registry, which runs the corresponding function and returns the result as the observation.
"""


chat_page(
    "ReAct Chat",
    "The foundational Thought → Tool Call → Observation loop, as a multi-turn chat with filesystem tools.",
    "examples/01_agent_patterns/01_react_basic.py",
    about_extra=about_from(CORE_CONCEPT),
)
