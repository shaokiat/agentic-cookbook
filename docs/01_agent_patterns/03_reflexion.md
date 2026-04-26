# Reflexion Agent Pattern

The **Reflexion** pattern is an iterative self-correction framework that improves model output through recursive loops of generation, evaluation, and revision. It is highly effective for tasks where the first attempt might be logically flawed, stylistically inconsistent, or factually incomplete.

## Overview

Unlike a single-shot prompt, Reflexion introduces a "feedback loop" where the model's own output is treated as a draft to be critiqued and refined.

1.  **Drafting**: An agent generates an initial response to the user's task.
2.  **Critique**: A separate agent (or the same model with a specialized prompt) reviews the draft for errors, style, or logical gaps.
3.  **Revision**: An agent uses the original draft and the critique to produce a final, optimized output.

---

## Architecture

This pattern is implemented in [examples/01_agent_patterns/03_reflexion.py](../../examples/01_agent_patterns/03_reflexion.py).

In this implementation, we utilize three distinct agent personas to simulate a collaborative editorial process:

### 1. The Writer (Drafting)
Responsible for the "creative" spark. It ignores technical constraints in favor of generating a complete initial narrative or response.

### 2. The Critic (Evaluation)
Acts as a rigorous peer reviewer. It specifically looks for inconsistencies, tone issues, and logical fallacies without suggesting the exact wording for the fix.

### 3. The Editor (Revision)
Synthesizes the original work and the feedback to produce the final version. It acts as the final arbiter of quality.

---

## Multi-Agent Workflow

The implementation demonstrates how multiple `Agent` instances can be chained together. Each agent maintains its own `Memory`, ensuring that the "critic" isn't biased by the initial drafting process, and the "editor" stays focused on the feedback.

### Code Snippet: The Reflexion Chain
```python
# Phase 1: Drafting (name identifies the agent in the logs)
writer_agent = Agent(
    system_prompt="You are a creative writer...", 
    log_path=log_path,
    name="Writer"
)
attempt = writer_agent.run(task)

# Phase 2: Critique (overwrite=False appends to existing log)
critic_agent = Agent(
    system_prompt="You are a critical reviewer...", 
    log_path=log_path,
    name="Critic",
    overwrite=False
)
critique = critic_agent.run(f"Please critique this text:\n\n{attempt}")

# Phase 3: Revision
revision_agent = Agent(
    system_prompt="You are an expert editor...", 
    log_path=log_path,
    name="Editor",
    overwrite=False
)
final_output = revision_agent.run(f"Original Text: {attempt}\n\nCritique: {critique}")
```

---

## Logging & Multi-Agent Observability

One of the challenges with multi-agent patterns is tracking which agent performed which action. The `Agent` class handles this via:

- **Agent Identity**: By passing a `name` to the constructor, every log entry (including reasoning loops and tool calls) is prefixed with that name in the Markdown logs.
- **Non-Destructive Logging**: By setting `overwrite=False`, agents will append their actions to a shared log file instead of overwriting it at the start of each `run()`.

This creates a unified "story" of the agentic interaction in a single file like [`03_reflexion_log.md`](../../examples/logs/03_reflexion_log.md).

---

## Deep Dive: Run Analysis

Following the run log [`03_reflexion_log.md`](../../examples/logs/03_reflexion_log.md), we can see the transition from a poetic draft to a refined final version.

### 1. The Feedback Signal
The Critic identified that while the imagery was "rich," it was potentially "too abstract" for technical clarity.
- **Key Critique Points**: High imagery ("gossamer," "labyrinth"), but potentially inaccessible metaphors for recursive loops.

### 2. The Revision Logic
During the final phase, the **Editor** (Revision Agent) processed the critique specifically to balance "poetic essence" with "clarity."

- **Original Line**: *"Where thought begets thought in endless mode"*
- **Revised Line**: *"Where thought ignites and swells to achieve"* (Focusing on the momentum of recursion).

### technical Note: Thought vs. Answer
In the logs, you will notice both `Assistant Thought` and `Final Answer`:
- **Assistant Thought**: This is the model's output at a specific **Step** in its reasoning loop. If the agent calls tools, there may be multiple "thoughts" as it works through the problem.
- **Final Answer**: This is the consolidated result returned at the **End** of the agent's run. In a simple Reflexion loop without tools, these are often identical as the agent completes its task in a single step.

> [!TIP]
> **Separation of Concerns**
> By using separate agent instances with different system prompts, we prevent "role confusion." A model tasked with *writing* often finds its own errors hard to see; a dedicated *critic* persona is more likely to be objective and thorough.

### Quantification: The Reflexion Impact

| Phase | Agent Role | Input Source | Primary Goal |
| :--- | :--- | :--- | :--- |
| **Drafting** | Creative Writer | User Prompt | Initial high-level generation. |
| **Critique** | Critical Reviewer | Draft | Identify weaknesses and gaps. |
| **Revision** | Expert Editor | Draft + Critique | Re-synthesize and optimize. |

---

## How to Reproduce

To see the Reflexion loop in action:

1.  Run the example script:
    ```bash
    python examples/01_agent_patterns/03_reflexion.py
    ```
2.  Examine the visual output in your terminal (using `rich` formatting).
3.  Review the granular log file generated at `examples/logs/03_reflexion_log.md` to see the internal "Thinking" of each agent phase.

This pattern can be extended to include multiple rounds of critique (Iterative Reflexion) or automated testing (e.g., critiquing code by running it).
