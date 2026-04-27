# 02 Memory Management

This category explores how agents retain information over time, handle large contexts, and utilize external knowledge.

## Examples

| File | Concept |
| :--- | :--- |
| [`01_windowed_memory.py`](./01_windowed_memory.py) | Short-term memory — sliding window that prunes old messages to stay within context limits |
| [`02_markdown_persistence.py`](./02_markdown_persistence.py) | Intermediate memory — persist facts to a markdown file across session restarts ([guide](./02_markdown_persistence.md)) |

## Core Concepts to Explore
1. **Short-term Memory**: Managing the immediate conversation window (sliding windows, summarization).
2. **Intermediate Memory**: Durable facts written to markdown files — survives restarts, human-readable, git-diffable.
3. **Long-term Memory (RAG)**: Using vector databases to retrieve relevant history or external documents.
