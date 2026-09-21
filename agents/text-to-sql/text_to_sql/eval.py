"""Eval harness: runs a question set through the real agent path and scores by result equality.

  python -m text_to_sql.eval                          # default variant/model, writes answers.json
  python -m text_to_sql.eval --variants baseline,full  # prompt ablation
  python -m text_to_sql.eval --models a,b              # model A/B
  python -m text_to_sql.eval --repeats 5               # variance across repeat runs
"""

import argparse
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List

from text_to_sql.agent import DEFAULT_MODEL, DEFAULT_VARIANT, PRICING, SQLAgent

QUESTIONS = Path("data/questions.json")
ANSWERS_OUT = Path("answers.json")


def normalize(rows: List[List[Any]]) -> List[tuple]:
    """Result-set equality: ignore column aliases and ordering, round floats."""

    def cell(v: Any) -> Any:
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return round(float(v), 2)
        return str(v).strip()

    return sorted((tuple(sorted((cell(v) for v in row), key=str)) for row in rows), key=str)


def score(actual_rows: List[List[Any]], expected: List[Dict[str, Any]]) -> bool:
    return normalize(actual_rows) == normalize([list(r.values()) for r in expected])


def summarize(rows: List[List[Any]], columns: List[str], error: str | None) -> str:
    if error:
        return f"ERROR: {error}"
    if not rows:
        return "no rows"
    if len(rows) == 1 and len(rows[0]) == 1:
        return f"{columns[0] if columns else 'result'} = {rows[0][0]}"
    head = "; ".join(", ".join(f"{c}={v}" for c, v in zip(columns, r)) for r in rows[:5])
    return head + (f" (+{len(rows) - 5} more rows)" if len(rows) > 5 else "")


def run(variant: str, model: str, questions: List[Dict[str, Any]], verbose: bool = True) -> Dict[str, Any]:
    """One (prompt variant, model) cell of the matrix. Fresh agent = no cross-question history."""
    results = []
    for q in questions:
        agent = SQLAgent(model=model, variant=variant)
        r = agent.ask(q["question"])
        r["id"], r["tier"] = q["id"], q["tier"]
        r["correct"] = r["error"] is None and score(r["rows"], q["expected_result"])
        r["answer"] = summarize(r["rows"], r["columns"], r["error"])
        results.append(r)
        if verbose:
            mark = "PASS" if r["correct"] else "FAIL"
            print(f"  [{mark}] {q['id']} (tier {q['tier']}) {r['latency_s']}s"
                  f"{' repaired' if r['repaired'] else ''}")

    lat = sorted(r["latency_s"] for r in results)
    n = len(results)
    tiers = sorted({r["tier"] for r in results})
    return {
        "variant": variant,
        "model": model,
        "results": results,
        "accuracy": sum(r["correct"] for r in results) / n,
        "by_tier": {
            t: sum(r["correct"] for r in results if r["tier"] == t)
            / sum(1 for r in results if r["tier"] == t)
            for t in tiers
        },
        "error_rate": sum(r["error"] is not None for r in results) / n,
        "repair_rate": sum(r["repaired"] for r in results) / n,
        "p50_latency": statistics.median(lat),
        "p95_latency": lat[min(n - 1, int(0.95 * n))],
        "cost_per_query": sum(r["cost_usd"] for r in results) / n,
        "avg_tokens": sum(r["prompt_tokens"] + r["completion_tokens"] for r in results) / n,
    }


def print_scoreboard(runs: List[Dict[str, Any]]) -> None:
    hdr = f"{'variant':<18}{'model':<26}{'acc':>6}{'err':>6}{'repair':>8}{'P50':>7}{'P95':>7}{'tok':>7}{'$/q':>10}"
    print("\n" + hdr)
    print("-" * len(hdr))
    for r in runs:
        print(f"{r['variant']:<18}{r['model'].split('/')[-1]:<26}"
              f"{r['accuracy']:>5.0%}{r['error_rate']:>6.0%}{r['repair_rate']:>8.0%}"
              f"{r['p50_latency']:>6.2f}s{r['p95_latency']:>6.2f}s{r['avg_tokens']:>7.0f}"
              f"{r['cost_per_query']:>10.5f}")
    for r in runs:
        print(f"\n{r['variant']} / {r['model'].split('/')[-1]} by tier: "
              + ", ".join(f"tier {t}: {a:.0%}" for t, a in r["by_tier"].items()))


def print_variance(runs: List[Dict[str, Any]], repeats: int) -> None:
    """Spread across repeat runs of the same cell. Temperature 0 is not determinism."""
    cells: Dict[tuple, List[Dict[str, Any]]] = {}
    for r in runs:
        cells.setdefault((r["variant"], r["model"]), []).append(r)
    hdr = f"{'variant':<18}{'model':<16}{'acc mean':>10}{'acc range':>12}{'P50 mean':>10}{'P50 range':>14}"
    print(f"\n{repeats} runs per cell:\n{hdr}\n" + "-" * len(hdr))
    for (variant, model), rs in cells.items():
        acc = [r["accuracy"] for r in rs]
        p50 = [r["p50_latency"] for r in rs]
        print(f"{variant:<18}{model.split('/')[-1]:<16}"
              f"{statistics.mean(acc):>9.0%}{f'{min(acc):.0%}-{max(acc):.0%}':>12}"
              f"{statistics.mean(p50):>9.2f}s{f'{min(p50):.2f}-{max(p50):.2f}s':>14}")


def print_failures(run_result: Dict[str, Any], gold: Dict[str, Dict[str, Any]]) -> None:
    misses = [r for r in run_result["results"] if not r["correct"]]
    if not misses:
        print("\nNo failures.")
        return
    print(f"\nFailure analysis ({run_result['variant']} / {run_result['model'].split('/')[-1]}):")
    for r in misses:
        print(f"\n  {r['id']} (tier {r['tier']}): {r['question']}")
        print(f"    generated: {r['sql']}")
        print(f"    gold     : {gold[r['id']]['gold_sql']}")
        print(f"    got      : {r['answer']}   expected: {gold[r['id']]['expected_result']}")
        print(f"    model's reasoning: {r['reasoning'][:300]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default=DEFAULT_VARIANT, help="comma-separated: baseline,schema_only,schema_plus_docs,full")
    ap.add_argument("--models", default=DEFAULT_MODEL, help="comma-separated model ids")
    ap.add_argument("--out", default=str(ANSWERS_OUT), help="answers.json path (first cell only)")
    ap.add_argument("--repeats", type=int, default=1, help="runs per cell; >1 also prints variance")
    ap.add_argument("--questions", default=str(QUESTIONS), help="question set path (default: data/questions.json)")
    args = ap.parse_args()

    unpriced = [m for m in args.models.split(",") if m not in PRICING]
    if unpriced:
        print("WARNING: no list price for " + ", ".join(unpriced) + " — $/query will read 0.00000.\n"
              "Add it to PRICING in text_to_sql/agent.py.")

    questions = json.loads(Path(args.questions).read_text())
    gold = {q["id"]: q for q in questions}

    runs = []
    for model in args.models.split(","):
        for variant in args.variants.split(","):
            for rep in range(args.repeats):
                suffix = f" [run {rep + 1}/{args.repeats}]" if args.repeats > 1 else ""
                print(f"\n=== {variant} / {model.split('/')[-1]}{suffix} ===")
                runs.append(run(variant, model, questions))

    print_scoreboard(runs)
    if args.repeats > 1:
        print_variance(runs, args.repeats)
    print_failures(runs[0], gold)

    Path(args.out).write_text(json.dumps(
        {r["id"]: {"sql": r["sql"], "answer": r["answer"]} for r in runs[0]["results"]}, indent=2
    ))
    Path("eval_runs.json").write_text(json.dumps(runs, indent=2))
    print(f"\nWrote {args.out} and eval_runs.json")


if __name__ == "__main__":
    main()
