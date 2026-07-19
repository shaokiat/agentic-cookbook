# 05 Evaluation and Monitoring

Techniques for measuring the performance, reliability, and cost of agentic
workflows. These tools are essential before deploying any agent to production
or comparing prompt/model alternatives.

---

## Concept Ladder

| Level | Pattern | File |
| :---- | :------ | :--- |
| 1 | Parse trace logs to report step counts, tool usage, and error rates | `01_log_analyzer.py` |
| 2 | Intercept a live agent run to capture a structured execution trace | `02_agent_tracer.py` |
| 3 | Use a judge model to score agent outputs against a rubric | `03_llm_judge.py` |

---

## Examples

### `01_log_analyzer.py` — Log Analyzer

Reads the markdown trace files written by `AgentLogger` (from `examples/logs/`)
and produces aggregate statistics without re-running any agents.

```
examples/logs/*.md
    │
    ▼  parse_log_file()
    ├── RunTrace(steps=5, tool_calls=[...], error_count=0)
    └── RunTrace(steps=7, tool_calls=[...], error_count=1)
    │
    ▼  Rich tables
    ├── Per-run summary (steps, tool calls, errors)
    ├── Tool frequency table with error rates
    └── Aggregate stats (total steps, token est., overall error rate)
```

**Usage**:
```bash
python examples/05_evaluation_and_monitoring/01_log_analyzer.py
python examples/05_evaluation_and_monitoring/01_log_analyzer.py --log-dir path/to/logs
```

**When to use**: Post-hoc debugging. Run this after a batch of agent executions
to spot which tools fail most, which runs took the most steps, and where to
focus prompt improvements.

---

### `02_agent_tracer.py` — Agent Tracer

A context manager that monkey-patches `Agent.run`, `ModelProvider.generate`,
and `ToolRegistry.call_tool` to capture timing, token usage, and tool
inputs/outputs in a structured `Trace` object — without modifying any
core files.

```python
with AgentTracer(agent) as tracer:
    result = agent.run("Do something")

tracer.print_report()   # Rich tree visualization
data = tracer.to_dict() # Machine-readable dict for downstream use
```

**Output per run**:
- Per-step latency (ms) and thought content
- Per-tool-call latency, arguments, result, and error flag
- Total tokens, cost, and wall-clock time

**Key insight**: monkey-patching the three entry points (run, generate,
call_tool) captures the full execution path without subclassing. This is
the same technique used by distributed tracing libraries (OpenTelemetry,
LangSmith, Weights & Biases).

**When to use**: During development to understand where latency is coming from,
or to build a dataset of (input, trace, output) triples for fine-tuning.

---

### `03_llm_judge.py` — LLM-as-Judge

Three evaluation modes using a judge model to assess agent responses:

**Mode 1 — Single-criterion scoring**: rate on one axis (accuracy, clarity,
etc.) from 1–5 with a JSON-structured justification.

**Mode 2 — Multi-criterion rubric**: score across multiple dimensions
simultaneously. Results are machine-readable dicts suitable for dashboards.

**Mode 3 — Pairwise comparison**: compare two agent responses head-to-head.
The judge picks A, B, or tie. Use this to A/B test prompt or model changes.

```
Question + Response → Judge model → {"score": 4, "justification": "..."}
```

**Key insight**: the judge prompt is the eval spec. It should be versioned,
reviewed, and iterated like code. A bad judge prompt gives misleading scores
just as a bad test suite gives misleading pass rates.

**When to use**: When correctness is hard to express as a Python assertion.
The judge excels at nuanced qualities — tone, completeness, coherence — that
pattern matching cannot capture.

**Limitation**: LLM judges have known biases (verbosity bias, position bias).
Always calibrate against a small human-labelled gold set before trusting scores
at scale.

---

## Core Concepts

### The evaluation triangle

Every agent eval involves three components:

```
Input (question / task)
    │
    ▼
Agent response
    │
    ▼
Evaluator (log parser / tracer / judge / human)
    │
    ▼
Score or label
```

Different evaluators suit different failure modes:

| Evaluator | Catches | Misses |
|---|---|---|
| Log analyzer | Crashes, high step counts, error loops | Wrong-but-confident answers |
| Agent tracer | Latency hotspots, token cost, unexpected paths | Answer quality |
| LLM judge | Content quality, nuance, tone | Logic errors in structured output |
| Unit tests | Regressions in deterministic logic | Creative or open-ended tasks |

### Cost tracking

`ModelProvider` accumulates token counts across all calls via
`cumulative_usage`. The tracer captures this after each run. Use it to:
- Alert when a run exceeds a token budget
- Compare cost across prompt variants
- Set `max_steps` limits informed by real data

### Deterministic testing

For agents that must produce structured output (JSON, SQL, code), combine the
tracer with mock tool responses to make tests deterministic:

```python
# Replace with fixed responses for reproducibility
registry.tools["fetch_stock_price"] = lambda symbol: "AAPL: $189.45"
with AgentTracer(agent) as tracer:
    result = agent.run("What is the AAPL price?")
assert "189.45" in result
```

---

## How Production Systems Approach This

### pi-coding-agent: session logging and cost tracking

pi-coding-agent logs every model turn and tool call to a session file and
tracks cumulative cost via `pi-ai`'s built-in token accounting. The approach
mirrors `01_log_analyzer.py` — structured logs that can be post-processed —
but the format is designed for persistence across sessions, not just a single
run.

### OpenClaw: trajectory replay

OpenClaw stores the full message sequence for every agent session in a session
store. A failed or suboptimal run can be replayed with a modified prompt or
model, making it possible to compare trajectories rather than just final
outputs. `02_agent_tracer.py`'s `to_dict()` format is a minimal version of
this: a serialisable trace that records the full execution path.

### Evals at scale: LLM judges vs. rubric tests

Production teams at Anthropic and elsewhere use LLM judges for open-ended
tasks (coding agent outputs, multi-hop reasoning) and deterministic tests
(regex, JSON schema validation, unit tests) for structured outputs. The split
is roughly: if you can write a predicate, write a predicate; if you can't,
use a judge. Never use only one.
