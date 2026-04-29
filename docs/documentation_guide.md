# Documentation Guide

This guide defines the structure and voice for all documentation in this cookbook. Follow it when writing READMEs and walkthroughs for any concept ladder level.

---

## Principles

1. **Explain the why, not just the what.** Code shows what happens. Docs explain why a design choice was made and what it costs.
2. **Ground every concept in the reference implementations.** OpenClaw and Nanobot are real production systems. Use them to show that the pattern being taught is not academic — it is how deployed agents actually work.
3. **Compare, don't just list.** When both systems solve the same problem differently, show the tradeoff. A table of "OpenClaw does X, Nanobot does Y" is less useful than a paragraph explaining *why* they diverged and what each approach gains.
4. **Connect the example to the pattern.** Each walkthrough should make explicit which design decision in the code corresponds to which architectural pattern, and why that decision was made this way rather than another.

---

## README Structure

Each subfolder README covers one level of the concept ladder.

```
# NN Topic Name

One-paragraph framing: what problem this level solves, and why it matters before moving to the next level.

---

## Concept Ladder

Table: Level | Pattern description | File

---

## Examples

### `filename.py` — Short Title

2–3 sentences: what it does, the key mechanism, when to use it.

[Walkthrough →](filename_walkthrough.md)

(repeat for each example)

---

## Core Concepts

### Concept Name
Explanation of the underlying idea, grounded in the example code.

(repeat for 2–4 key concepts)

---

## How Production Systems Approach This

### Sub-question 1 (the interesting design divergence)

Paragraph comparing OpenClaw and Nanobot:
- What each system does
- Why they made that choice (what constraint drove it)
- What the tradeoff is
- Which choice the example in this folder follows and why

### Sub-question 2 ...

(2–4 sub-questions covering the most instructive divergences)

---

See `docs/reference_architectures.md` for full architectural analysis.
```

### Rules for the "How Production Systems Approach This" section

- Each sub-question should be a genuine architectural decision, not a surface difference. "OpenClaw is TypeScript, Nanobot is Python" is not a sub-question. "OpenClaw tracks subagent lineage in a registry; Nanobot fires and forgets" is.
- Lead with the constraint that drove the decision, not the decision itself. "OpenClaw's mobile/multi-platform architecture requires temporal decoupling between parent and child agents" explains *why* the announce pattern exists.
- Name the specific source files (`subagent-registry.ts`, `AgentRunner.run()`) so readers can cross-reference with `docs/reference_architectures.md`.
- End each sub-question by connecting back to the example in this folder: "The example uses the simpler X approach because Y."

---

## Walkthrough Structure

Each example gets one walkthrough file co-located in its subfolder.

```
# Topic: Walkthrough

One sentence: what this file covers.

---

## What it does

The task or scenario the example demonstrates. Quote the exact input given to the agent.

---

## How the code works

### Section per key mechanism

Code snippet (the relevant 5–15 lines, no more).
Explanation of each design decision in the snippet.
Why this way and not another way.

(repeat for 2–5 mechanisms)

---

## Execution trace (if the example was run)

What actually happened, step by step. Use a table for tool call sequences.
Quote any non-obvious model behaviour (e.g., "the model skipped preamble and went straight to the first tool call").

---

## What the execution reveals about the pattern

2–4 observations grounded in what actually ran. Not what the code is supposed to do — what it did, and what that tells us about the pattern.

---

## How production systems handle this

### The key design question

- **OpenClaw**: what it does, source file reference, why (what constraint drove it)
- **Nanobot**: what it does, source file reference, why
- **Tradeoff**: what each approach gains and loses
- **This example**: which approach it follows and why that is the right default for a cookbook example

(repeat for 1–3 key questions)

---

## Tradeoffs

Table: Property | This example's approach | Alternative

---

## Extensions

Bullet list: concrete code changes that add the next level of capability.
Each extension should be 1–2 sentences. No code samples — just enough to point the reader in the right direction.

---

_Example_: `filename.py`
_See also_: cross-references to related examples or docs
```

### Rules for the "How production systems handle this" section in walkthroughs

- Pick the 1–3 design decisions in the example code where a different choice would produce meaningfully different behaviour in production.
- The point is not to show that production systems are complex — it is to explain why the example made the choice it did, using the production system as evidence that the choice is sound (or that the simpler version is deliberately pedagogical).
- If the example deliberately simplifies a production pattern (e.g., synchronous where production is async), say so explicitly. "This example uses synchronous return for clarity. See `04_async_announce.py` for the production-equivalent async pattern."

---

## Voice and Style

- **No preamble.** Don't open with "In this document we will explore...". State what the file covers in the first sentence and move on.
- **No trailing summaries.** Don't end sections with "In summary, we have seen that...". The reader just read it.
- **Active voice.** "The registry generates a schema" not "A schema is generated by the registry."
- **Concrete over abstract.** "The model called `count_words` before `multiply` because it needs the word count as input to the multiplication" is better than "The model determines the correct tool call order."
- **Name the file.** When referencing a specific behaviour in OpenClaw or Nanobot, cite the source file: `subagent-registry.ts`, `AgentRunner.run()`. This lets readers verify.
- **Short paragraphs.** Two to four sentences per paragraph. If you need more, split the concept.
- **No emojis unless the user explicitly requested them.**
- **No comments in code snippets** unless the comment explains something non-obvious that the surrounding prose does not cover.

---

## What NOT to include

- **Step-by-step setup instructions.** Those belong in the root README.
- **API reference.** Parameter descriptions belong in docstrings, not walkthroughs.
- **Exhaustive feature lists.** Cover the 2–3 most instructive decisions, not every line.
- **Hypothetical future extensions** beyond what the codebase supports today. Extensions should be achievable with small, concrete changes.
- **Generic best-practice advice** not grounded in this codebase. "Always validate your inputs" adds no value here.

---

## Example: applying the template to a README section

**Do not write:**

> OpenClaw uses `subagent-registry.ts` for subagent management. Nanobot uses `SubagentManager`.

**Write instead:**

> **Subagent scoping: registry-tracked vs. fire-and-forget**
>
> OpenClaw maintains a full `SubagentRegistry` that tracks every child agent's lineage (parent → child → grandchild), enforces depth limits, and manages lifecycle states. This overhead is justified because OpenClaw supports long-running background agents that outlive a single session and need to be recoverable after a crash.
>
> Nanobot's `SubagentManager` spawns a child `AgentLoop` as a background `asyncio.Task` and tracks it only until it posts its result. No lineage graph, no depth enforcement by default. The tradeoff is simplicity for single-server deployments, at the cost of being harder to audit in recursive scenarios.
>
> The `01_orchestrator_worker.py` example sits closer to Nanobot's model — spawn, run, return — which is the right default when you control the prompt and depth is not a concern.

The second version answers: what does each system do, why, what does each gain, and which approach does the example use and why.
