# text-to-sql

Natural-language questions → SQL → results, in a terminal REPL, against any SQLite,
Postgres, or MySQL database.

## The problem

`Convert this question to SQL: {question}` — no schema, no column docs — is the prompt
every text-to-SQL prototype starts with, and it fails predictably: the model hallucinates
table and column names it has never seen, picks the wrong join key, or invents string
values that don't exist in the data. None of that shows up as an exception; it shows up as
a wrong answer that looks plausible. This agent exists to measure how much of that a
schema-grounded prompt fixes, and how much is left over for a guard + repair loop to catch.

## Architecture

- **Prompt is a stack of optional sections**, each one a superset of the last
  (`text_to_sql/agent.py::PROMPT_VARIANTS`): `baseline` (the naive prompt above) →
  `schema_only` (+ DDL) → `schema_plus_docs` (+ per-column documentation, when the database
  ships any) → `full` (+ freeform dataset hints/examples, when the database ships those too).
  A database with no docs or hints degrades gracefully to `schema_only` — nothing crashes,
  the agent just runs with less context.
- **A read-only guard is the actual safety boundary**, not the prompt (`agent.py::guard`):
  single `SELECT`/`WITH` statement only, no semicolon batches, no DDL/DML keywords. The
  SQLite connection is also opened `mode=ro` as a second, independent boundary.
- **One bounded repair**: if execution fails, the error message goes back to the model once
  for a corrected query. No retry loop — a model that can't fix it in one try usually can't
  fix it at all, and an unbounded loop just burns tokens.
- **`Database`** (`text_to_sql/db.py`) is one interface over SQLite or any SQLAlchemy
  connection string, so "any database" is a connection string, not a rewrite.

## Run it

```bash
uv sync
cp .env.example .env   # then fill in LLM_API_KEY
uv run text-to-sql
```

```
> How many accounts are located in the Prague region?

SQL:
  SELECT COUNT(*) AS account_count FROM account JOIN district
  ON account.district_id = district.district_id WHERE district.A3 = 'Prague' COLLATE NOCASE

account_count
-------------
554
(1 row)
[1.16s · 2132 tokens · $0.00036]
```

`schema` prints the tables and columns; `exit`/`quit` leaves. `--db` points at another
SQLite file or SQLAlchemy connection string; `--model` swaps the LLM. Any OpenAI-compatible
endpoint works for `LLM_API_BASE` — Fireworks by default, or a local server started with
`make serve-vllm` from the cookbook root.

## Validate it

```bash
python tests/test_agent.py                        # guard, scorer, prompt-variant self-checks
python tests/test_agent.py --live                  # + forced-failure repair + follow-up memory (real API calls)
python -m text_to_sql.eval --variants baseline,schema_only,schema_plus_docs,full
```

The eval harness (`text_to_sql/eval.py`) scores by **result-set equality** — rows sorted,
floats rounded, column aliases ignored — against `data/questions.json`, and prints a
scoreboard across whatever prompt variants / models you pass. `--repeats N` also reports
variance: temperature 0 is not determinism, and accuracy on a small question set can move
run to run.

## The demo database

`data/financial.sqlite` is the `financial` database from the [BIRD
benchmark](https://bird-bench.github.io/) (CC BY-SA 4.0 — see `BIRD_LICENSE.md`): a Czech
retail banking schema with 8 tables (accounts, clients, loans, transactions, cards,
standing orders, regional demographics). It's a good stress test for schema grounding
because it has the failure modes that make naive text-to-SQL fall over: status codes that
need decoding (`data/database_description/*.csv`), a reserved word as a table name
(`order`), dates stored as text, and two tables that both carry a `district_id` FK pointing
at different real-world things. `data/database_description/hints.md` is where those
dataset-specific rules live — swap the whole `data/` directory for your own database and
its docs/hints, and everything else keeps working.

## Known limits / where to take this next

- Repair is capped at one attempt and only exercised via fault injection
  (`tests/test_agent.py --live`) — it's never actually fired on the shipped question set.
- No retrieval: the docs/hints sections are loaded whole, which works at this schema's size
  (8 tables) but won't scale to a schema with hundreds of tables. That's the natural next
  step — embed column docs and retrieve only the relevant slice per question (the cookbook's
  `mini-researcher` agent already has a compress/retrieve pipeline to crib from).
- No tool-calling: the agent gets the schema up front rather than asking for it turn by
  turn. A tool-calling variant (`list_tables`, `describe_table`, `run_query` as tools) is
  the natural extension for databases too large to put in a system prompt at all.
- Results are capped at 100 rows; no pagination.
- Ambiguous questions fail rather than asking a clarifying question back.
