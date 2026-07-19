"""
LLM-as-Judge Evaluation

Use a judge model (Claude) to score an agent's response against a rubric.
This is the canonical "evals-as-a-service" pattern: instead of hand-writing
assertion logic, you describe what good looks like in natural language and let
the judge decide.

Three evaluation modes are demonstrated:

  Mode 1 — Single-criterion scoring: judge rates the response on one axis
    (e.g. accuracy, conciseness) from 1–5 with a short justification.

  Mode 2 — Multi-criterion rubric: judge scores across multiple dimensions
    and returns structured JSON so results are machine-readable.

  Mode 3 — Pairwise comparison: judge compares two agent responses and picks
    the better one, useful for A/B testing prompts or models.

Key insight: the judge prompt is the eval. Version-control it like code.

Docs: examples/05_evaluation_and_monitoring/03_llm_judge.md
"""
import json
import os
from dataclasses import dataclass
from dotenv import load_dotenv
import litellm
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from core.agent import Agent
from core.memory import Memory
from core.model import ModelProvider
from core.registry import ToolRegistry

load_dotenv()

console = Console()

JUDGE_MODEL = os.getenv("JUDGE_MODEL", os.getenv("DEFAULT_MODEL", "openai/gpt-4o"))


# --- Judge primitives --------------------------------------------------------

def _judge_call(prompt: str) -> str:
    """Call the judge model with a plain text prompt, return the response string."""
    response = litellm.completion(
        model=JUDGE_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()


# --- Mode 1: Single-criterion scoring ----------------------------------------

@dataclass
class SingleScore:
    criterion: str
    score: int        # 1–5
    justification: str


def score_single(question: str, response: str, criterion: str) -> SingleScore:
    """
    Ask the judge to rate response on a single criterion from 1 (worst) to 5 (best).
    """
    prompt = f"""You are an impartial evaluator. Rate the following response on a scale of 1–5.

**Criterion**: {criterion}
**Scale**: 1 = very poor, 3 = acceptable, 5 = excellent

**Question asked to the agent**:
{question}

**Agent's response**:
{response}

Reply with ONLY a JSON object in this exact format:
{{"score": <integer 1-5>, "justification": "<one sentence>"}}"""

    raw = _judge_call(prompt)
    try:
        data = json.loads(raw)
        return SingleScore(
            criterion=criterion,
            score=int(data["score"]),
            justification=data["justification"],
        )
    except (json.JSONDecodeError, KeyError):
        return SingleScore(criterion=criterion, score=0, justification=f"Parse error: {raw}")


# --- Mode 2: Multi-criterion rubric ------------------------------------------

@dataclass
class RubricScore:
    scores: dict[str, int]     # criterion → score
    justifications: dict[str, str]
    overall: int


def score_rubric(question: str, response: str, rubric: dict[str, str]) -> RubricScore:
    """
    Score a response against a multi-criterion rubric.
    rubric = {criterion_name: criterion_description}
    """
    rubric_text = "\n".join(f"- **{k}**: {v}" for k, v in rubric.items())
    criteria_json = {k: {"score": "1-5", "justification": "one sentence"} for k in rubric}

    prompt = f"""You are an impartial evaluator. Score the following agent response on each criterion from 1–5.

**Question asked to the agent**:
{question}

**Agent's response**:
{response}

**Rubric** (score each 1=very poor, 5=excellent):
{rubric_text}

Reply with ONLY a JSON object matching this schema:
{json.dumps(criteria_json, indent=2)}

Also include an "overall" key with a single integer 1–5 representing the overall quality."""

    raw = _judge_call(prompt)
    try:
        data = json.loads(raw)
        overall = int(data.pop("overall", 0))
        scores = {k: int(v["score"]) for k, v in data.items() if isinstance(v, dict)}
        justifications = {k: v.get("justification", "") for k, v in data.items() if isinstance(v, dict)}
        return RubricScore(scores=scores, justifications=justifications, overall=overall)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        return RubricScore(scores={}, justifications={}, overall=0)


# --- Mode 3: Pairwise comparison ---------------------------------------------

@dataclass
class PairwiseResult:
    winner: str    # "A", "B", or "tie"
    justification: str


def compare_responses(question: str, response_a: str, response_b: str) -> PairwiseResult:
    """
    Ask the judge to pick the better of two responses (A/B test).
    """
    prompt = f"""You are an impartial evaluator comparing two responses to the same question.

**Question**:
{question}

**Response A**:
{response_a}

**Response B**:
{response_b}

Which response is better overall? Consider accuracy, completeness, and clarity.

Reply with ONLY a JSON object:
{{"winner": "A" | "B" | "tie", "justification": "<one sentence>"}}"""

    raw = _judge_call(prompt)
    try:
        data = json.loads(raw)
        return PairwiseResult(winner=data["winner"], justification=data["justification"])
    except (json.JSONDecodeError, KeyError):
        return PairwiseResult(winner="tie", justification=f"Parse error: {raw}")


# --- Demo agent helpers ------------------------------------------------------

def _run_agent(system_prompt: str, question: str, model: str | None = None) -> str:
    agent = Agent(
        model=ModelProvider(model),
        memory=Memory(),
        registry=ToolRegistry(),
        system_prompt=system_prompt,
        max_steps=3,
        verbose=False,
    )
    return agent.run(question)


# --- Demo --------------------------------------------------------------------

DEFAULT_QUESTION = (
    "Explain the difference between supervised and unsupervised learning "
    "in machine learning. Give a concrete example of each."
)


def llm_judge_demo():
    console.print(Rule("[bold blue]LLM-as-Judge Evaluation[/bold blue]"))

    question = DEFAULT_QUESTION

    console.print(f"[dim]Question: {question}[/dim]\n")

    # Generate two responses with different system prompts for comparison
    console.print("[bold yellow]Running agents...[/bold yellow]")
    response_a = _run_agent(
        "You are a concise ML tutor. Answer in 3-4 sentences maximum.", question
    )
    response_b = _run_agent(
        "You are a thorough ML educator. Provide detailed explanations with examples.", question
    )

    console.print(Panel(response_a, title="[bold]Response A (concise)[/bold]", border_style="cyan"))
    console.print(Panel(response_b, title="[bold]Response B (thorough)[/bold]", border_style="blue"))

    # Mode 1: Single criterion
    console.print(Rule("[bold]Mode 1 — Single Criterion[/bold]"))
    for criterion in ["accuracy", "clarity"]:
        score = score_single(question, response_a, criterion)
        console.print(f"Response A — {criterion}: [bold]{score.score}/5[/bold] — {score.justification}")

    # Mode 2: Multi-criterion rubric
    console.print(Rule("[bold]Mode 2 — Multi-Criterion Rubric[/bold]"))
    rubric = {
        "accuracy": "Is the information factually correct?",
        "completeness": "Does the answer cover all aspects of the question?",
        "clarity": "Is the answer easy to understand for a beginner?",
        "conciseness": "Is the answer appropriately concise without padding?",
    }
    rubric_result = score_rubric(question, response_b, rubric)

    table = Table(title="Response B — Rubric Scores")
    table.add_column("Criterion", style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Justification")
    for criterion, score_val in rubric_result.scores.items():
        color = "green" if score_val >= 4 else ("yellow" if score_val == 3 else "red")
        table.add_row(
            criterion,
            f"[{color}]{score_val}/5[/{color}]",
            rubric_result.justifications.get(criterion, ""),
        )
    console.print(table)
    console.print(f"Overall: [bold]{rubric_result.overall}/5[/bold]")

    # Mode 3: Pairwise
    console.print(Rule("[bold]Mode 3 — Pairwise Comparison[/bold]"))
    comparison = compare_responses(question, response_a, response_b)
    color = "cyan" if comparison.winner == "A" else ("blue" if comparison.winner == "B" else "yellow")
    console.print(
        Panel(
            f"Winner: [{color}]{comparison.winner}[/{color}]\n{comparison.justification}",
            title="[bold]Pairwise Result[/bold]",
            border_style=color,
        )
    )


if __name__ == "__main__":
    llm_judge_demo()
