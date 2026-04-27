# Intermediate Memory: Markdown Persistence

This example demonstrates **Concept #8: Intermediate Memory** from the Concept Ladder — storing facts in a markdown file so they survive session restarts.

## The Problem

Short-term memory (the context window) is wiped when a session ends. An agent that helped you yesterday remembers nothing today. For long-horizon tasks, agents need a way to persist discoveries across runs without flooding the next session's context with the full previous transcript.

## The Pattern

```
Session 1:  Agent learns facts → save_fact() → memory_store.md
                                                      │
Session 2:  memory_store.md → injected into system prompt → Agent recalls facts
```

Three moving parts:

1. **`memory_store.md`** — a plain markdown file, one bullet per fact. Human-readable and git-diffable.
2. **`save_fact` tool** — appends a new bullet to the file. The agent calls this explicitly when it decides something is worth remembering.
3. **System prompt injection** — at session start, `load_facts()` reads the file and embeds its contents into the system prompt before the agent runs. The agent receives prior context without re-reading a long transcript.

## Key Mechanic: Prime the System Prompt

```python
def make_agent(session_name: str) -> Agent:
    existing_facts = load_facts()           # read from disk
    system_prompt = f"""...
--- Recalled from previous sessions ---
{existing_facts}                            # injected here
----------------------------------------
Use save_fact to remember new information."""

    return Agent(..., system_prompt=system_prompt)
```

This is exactly what Open Claw does with `MEMORY.md` — the index is always injected into the system prompt, individual fact files are loaded on demand.

## Trade-offs vs Other Memory Types

| | Short-term (Context Window) | **Intermediate (This Example)** | Long-term (RAG) |
|---|---|---|---|
| Survives restart | No | **Yes** | Yes |
| Token cost | Always in context | Index only | Retrieval cost |
| Human-readable | No | **Yes** | No |
| Scales to... | ~200K tokens | Dozens of facts | Millions of documents |

## Running the Example

```bash
python examples/02_memory_management/02_markdown_persistence.py
```

Session 1 saves two facts. Session 2 starts a brand-new `Agent` with an empty `Memory()` — yet it can answer questions about Alice because the facts were injected from `memory_store.md`.

## In Open Claw

This pattern maps directly to:
- `MEMORY.md` — the global project memory index, injected every session
- `journal/` files — per-session discoveries written during a run
- `CLAUDE.md` — workspace instructions loaded into every system prompt
