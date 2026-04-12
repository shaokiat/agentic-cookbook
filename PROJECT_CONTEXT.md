# 🦀 agentic-cookbook Project Context

This document serves as the primary source of truth for the motivation, architecture, and rationale behind the `agentic-cookbook` project. It is intended to provide context for both human contributors and AI assistants.

---

## 🎯 Motivation

The core motivation of `agentic-cookbook` is to **demystify agentic architectures**. 

In an era of increasingly complex frameworks like LangChain, AutoGPT, and CrewAI, `agentic-cookbook` takes a step back. Inspired by the lean approaches of **Claude Code** and **Open Claw**, this project aims to provide a "barebones" implementation of a recursive agent loop.

### Why build this?
1.  **Educational**: To understand exactly how tool-calling, memory management, and feedback loops interact without layers of abstraction.
2.  **Prototyping**: To create a minimal but functional playground for testing new agentic concepts (e.g., terminal access, local file manipulation).
3.  **Transparency**: To keep the "thinking" process of the agent fully visible and controllable.

---

## 🏗️ Architectural Rationale

The project is built around four primary components, each chosen for specific reasons:

### 1. Agent Loop (`core/agent.py`)
-   **Concept**: A standard **Think-Act-Observe** (ReAct) cycle.
-   **Rationale**: We use a sequential loop rather than complex state machines. This makes the execution flow predictable and easy to debug. The loop continues until the model either achieves the goal or hits a `max_steps` safety limit.

### 2. Tool Registry (`core/registry.py`)
-   **Concept**: Dynamic schema generation from Python functions.
-   **Rationale**: **Configuration over Boilerplate**. By using Python type hints and docstrings, we automatically generate JSON schemas for the Model Provider. This reduces friction when adding new capabilities—if you can write a Python function, you can write a tool.

### 3. Model Abstraction (`core/model.py`)
-   **Concept**: Multi-provider support via **LiteLLM**.
-   **Rationale**: **Provider Agnosticism**. We avoid vendor lock-in by using a unified interface. This allows us to swap between OpenAI, Anthropic, or even local models (via Ollama) with a single configuration change.

### 4. Memory (`core/memory.py`)
-   **Concept**: Simple list-based message history.
-   **Rationale**: **Standardization**. By maintaining state in the standard `[{"role": "...", "content": "..."}]` format, we ensure compatibility with virtually all modern LLM APIs and simplify the logic for rendering context.

---

## 🧱 Design Principles

-   **Minimize Abstractions**: If a plain dictionary or list works, use it. Do not wrap data in classes unless they provide functional utility.
-   **Inversion of Control**: Tools are registered *to* the agent, rather than the agent being built *into* a specific toolset.
-   **Rich Feedback**: Use visual tools (like the `rich` library) to make the internal state (steps, tool calls, results) clear to the user.

---

## 🤖 Context for Future Contributions

When contributing to this project, keep the following in mind:

> [!TIP]
> **Minimalist first.** Before adding a dependency or a complex design pattern, ask: "Can this be done with a standard Python list or function?"

### Documentation Standards
- **Relative Paths Only**: Never use absolute local file paths (e.g., `/Users/...`) in documentation or links. Always use relative paths from the current file's location to maintain privacy, security, and portability.
- **Link Integrity**: Ensure all relative links to source code or other documentation are tested and valid.

### Adding New Features
-   **Tools**: Define them in `tools/` as standard functions and register them in `main.py`.
-   **Model Features**: If adding support for vision or long-context features, update `ModelProvider` without breaking the core generation interface.
-   **Agent Logic**: Any changes to the loop in `Agent.run` should prioritize keeping the "Step" output clean and informative.

### Future Roadmap
-   [ ] **Terminal Access**: A tool that can execute safe shell commands.
-   [ ] **File System Agent**: Tools for reading/writing files in the workspace.
-   [ ] **Self-Correction**: Improving how the agent handles tool execution errors.

---
*Created: 2026-04-12*
