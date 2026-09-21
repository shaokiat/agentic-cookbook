"""Interactive text-to-SQL CLI. Run with: uv run text-to-sql (or python -m text_to_sql.cli)"""

import argparse
import json
import os
import sys
import time

from text_to_sql.agent import SQLAgent
from text_to_sql.db import DEFAULT_DB_PATH

# Every query, appended as JSONL — a fine-tuning corpus candidate, especially the
# repaired rows, which are labeled failures. See README.md's post-training section.
QUERY_LOG = "query_log.jsonl"


def log_query(record: dict) -> None:
    with open(QUERY_LOG, "a") as f:
        f.write(json.dumps({"ts": time.time(), **record}) + "\n")


def print_table(columns, rows) -> None:
    if not columns:
        print("(no results)")
        return
    cells = [[("" if v is None else str(v)) for v in row] for row in rows]
    widths = [max(len(c), *(len(r[i]) for r in cells)) if cells else len(c)
              for i, c in enumerate(columns)]
    line = "  ".join(c.ljust(w) for c, w in zip(columns, widths))
    print(line)
    print("-" * len(line))
    for r in cells:
        print("  ".join(v.ljust(w) for v, w in zip(r, widths)))
    print(f"({len(rows)} row{'s' if len(rows) != 1 else ''})")


def main() -> None:
    ap = argparse.ArgumentParser(description="Ask a database questions in plain English.")
    ap.add_argument(
        "--db",
        default=DEFAULT_DB_PATH,
        help="SQLite file path, or any SQLAlchemy connection string "
        "(e.g. postgresql://user:pass@host/db, mysql+pymysql://user:pass@host/db)",
    )
    ap.add_argument("--model", default=None, help="model id (overrides LLM_MODEL)")
    args = ap.parse_args()

    if not os.environ.get("LLM_API_KEY"):
        sys.exit("LLM_API_KEY is not set (put it in .env)")
    if "://" not in args.db and not os.path.exists(args.db):
        sys.exit(f"database not found: {args.db}")
    agent = SQLAgent(model=args.model, db_path=args.db)
    print(f"Text-to-SQL CLI — {agent.model.split('/')[-1]} on {args.db}")
    print("Ask a question in plain English. 'schema' to see the tables, 'exit' or 'quit' to leave.\n")

    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not question:
            continue
        if question.lower() in ("exit", "quit"):
            return
        if question.lower() == "schema":
            print(agent.db.ddl())
            continue

        try:
            r = agent.ask(question)
        except Exception as e:  # noqa: BLE001 - keep the REPL alive on API/network errors
            print(f"error: {e}\n")
            continue

        log_query({k: r[k] for k in
                   ("question", "sql", "reasoning", "error", "repaired", "latency_s",
                    "prompt_tokens", "completion_tokens")})
        print(f"\nSQL{' (repaired)' if r['repaired'] else ''}:\n  {r['sql']}\n")
        if r["error"]:
            print(f"query failed: {r['error']}")
        else:
            print_table(r["columns"], r["rows"])
        print(f"[{r['latency_s']}s · {r['prompt_tokens'] + r['completion_tokens']} tokens · ${r['cost_usd']:.5f}]\n")


if __name__ == "__main__":
    main()
