# 📚 Agentic Architectures Guide

This document explores the common agentic architectures used in modern AI systems. The goal of `agentic-cookbook` is to provide minimal implementations of these patterns to illustrate their core mechanics.

## 1. ReAct (Reason + Act)
The foundational pattern for most modern agents. It structures the agent's behavior into a loop where it alternates between reasoning and acting.

- **Workflow**: Thought → Action (Tool Call) → Observation (Tool Result) → Thought ...
- **Strengths**: Handles dynamic tasks well; easy to implement.
- **Implementation in Cookbook**: See `core/agent.py` and [examples/01_react_basic.py](../examples/01_react_basic.py).
- **Detailed Guide**: [ReAct Basic Agent Documentation](./01_react_basic.md)

## 2. Plan-and-Execute
Separates the strategy (planning) from the execution. This avoids the "forgetfulness" of pure ReAct agents in long-horizon tasks.

- **Workflow**: Goal → Planner Agent (Global Plan) → Executor Agent (Execute Plan Step-by-Step) → Re-plan if necessary.
- **Strengths**: More stable for complex tasks; reduced token usage for repetitive execution steps.
- **Implementation in Cookbook**: See `examples/02_plan_and_execute.py`.

## 3. Reflexion (Self-Correction)
Enhances performance by adding a self-critique phase. The agent reviews its own work before finalizing it.

- **Workflow**: Agent Generation → Critiquer Agent (Identify Errors) → Agent Revision → Final Output.
- **Strengths**: High accuracy; mimics human "drafting" and "editing" process.
- **Implementation in Cookbook**: See `examples/03_reflexion.py`.

## 4. Multi-Agent Systems (MAS)
Distributes work across multiple specialized agents. Each agent has its own tools, persona, and specific domain expertise.

- **Workflow**: Orchestrator delegates tasks to specialized Worker Agents (e.g., Coder, Reviewer, Researcher).
- **Strengths**: Scalable for huge projects; better domain specialisation.
- **Cookbook Vision**: While not yet implemented as a core module, this can be achieved by having agents call other agents as tools (Inversion of Control).

---

### Comparison Matrix

| Architecture | Best For | Complexity | Implementation Tip |
| :--- | :--- | :--- | :--- |
| **ReAct** | Simple, dynamic tools | Low | Keep the "Thinking" output clean. |
| **Plan-and-Execute** | Long, multi-step tasks | Medium | Use a separate model/prompt for the planner. |
| **Reflexion** | High-precision code/text | Medium | Don't reflect too many times (diminishing returns). |
| **Multi-Agent** | Enterprise-scale workflows | High | Focus on clear communication protocols. |
