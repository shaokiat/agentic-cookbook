# LLM-as-Judge Evaluation: Walkthrough

> Placeholder — full execution trace to be written.

## What it does

Uses a judge model to score agent responses three ways: single-criterion rating (1–5 + justification), multi-criterion rubric (structured JSON per criterion), and pairwise A/B comparison of two responses to the same question.

## Key insight

The judge prompt **is** the eval — version-control it like code. Structured JSON output makes results machine-readable so evals can run in CI, not just eyeballs.

## Run it

```bash
.venv/bin/python examples/05_evaluation_and_monitoring/03_llm_judge.py
```

UI page: `ui/pages/p05_3_llm_judge.py`

## References

- Code: [`03_llm_judge.py`](03_llm_judge.py)
- Concept: [PROJECT_CONTEXT.md](../../PROJECT_CONTEXT.md) — #23 Evaluation
- Chapter overview: [README.md](README.md)
- Related: [`02_agent_tracer.py`](02_agent_tracer.py) — quantitative metrics to pair with the judge's qualitative scores
