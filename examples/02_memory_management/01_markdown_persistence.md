# Intermediate Memory: Markdown Persistence

Short-term memory (the context window) is wiped when a session ends. An agent that helped you yesterday remembers nothing today. Intermediate memory solves this by writing facts to disk during a session and injecting them back at the next session start.

## The Pattern

```
Session 1:  User tells agent facts → agent calls save_fact() → memory_store.md
                                                                      │
Session 2:  memory_store.md → load_facts() → injected into system prompt → agent recalls facts
```

Three moving parts:

1. **`memory_store.md`** — a plain markdown file, one bullet per fact. Human-readable and git-diffable.
2. **`save_fact` tool** — appends a bullet to the file. The agent decides what's worth saving.
3. **System prompt injection** — at session start, `load_facts()` reads the file and embeds its contents into the system prompt before the agent runs.

## Key Mechanic: Prime the System Prompt

```python
def make_agent(session_name: str) -> Agent:
    existing_facts = load_facts()           # read from disk
    system_prompt = f"""You are a helpful assistant with persistent memory.

--- Recalled from previous sessions ---
{existing_facts}
----------------------------------------
Use save_fact to remember new information for future sessions."""

    return Agent(..., system_prompt=system_prompt)
```

The new `Agent` starts with a completely empty `Memory()` — it has no access to Session 1's conversation. Yet it can answer correctly because the facts were written to disk and re-injected.

## What the example produces

Session 1 — the agent breaks the user's message into three discrete facts and saves each one:

```
Tool Call: save_fact({"fact": "The user's name is Alice."})
Tool Call: save_fact({"fact": "Alice is a researcher at Anthropic."})
Tool Call: save_fact({"fact": "Alice's favourite model is Claude."})
```

Session 2 — a brand-new agent, zero conversation history, answers from injected facts:

```
Assistant: You are Alice, a researcher at Anthropic,
           and your favourite model is Claude.
```

## Trade-offs

| | Short-term (context window) | **Intermediate (this example)** | Long-term (hybrid retrieval) |
|---|---|---|---|
| Survives restart | No | **Yes** | Yes |
| Context cost | O(history) | O(n facts) — all injected | O(k) — top-k retrieved |
| Human-readable | No | **Yes** | No |
| Scales to | ~200K tokens | Dozens of facts | Thousands of facts |

The scaling limit is the key weakness: every fact is injected on every session regardless of relevance. At hundreds of facts the system prompt becomes unwieldy and the model's attention dilutes. That's where long-term hybrid retrieval takes over — see [`02_hybrid_search.py`](./02_hybrid_search.py).

## Running the example

```bash
python examples/02_memory_management/01_markdown_persistence.py
```

## In Open Claw

| This example | Open Claw |
|:-------------|:----------|
| `memory_store.md` | `MEMORY.md` — global project memory index |
| `save_fact` tool | agent writes to `MEMORY.md` during a run |
| System prompt injection | `MEMORY.md` contents injected at every session start |
| — | `CLAUDE.md` — workspace instructions, same injection pattern |
| — | `journal/` files — per-session discoveries |
