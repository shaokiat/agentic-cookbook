# 03 Multi-Agent Systems

Learn how to coordinate multiple agents to solve problems that are too large or complex for a single agent.

## Core Concepts to Explore
1. **Hierarchical Coordination**: A "Manager" agent that decomposes tasks and delegates to "Worker" agents.
2. **Sequential Orchestration**: Passing a baton between specialized agents (e.g., Researcher -> Coder -> Reviewer).
3. **Peer-to-Peer**: Agents communicating directly with each other to reach a consensus.
4. **Sub-Agents**: Spawning temporary agents to handle specific sub-tasks using the `context` injection pattern.

## Suggested Next Example
- `01_manager_worker.py`: A high-level manager that uses sub-agents to research and then summarize a topic.
