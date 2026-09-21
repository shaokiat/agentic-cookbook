"""Self-check: python tests/test_agent.py (run from the agents/text-to-sql/ directory)"""
import json
import sqlite3
import sys

from text_to_sql.agent import guard, execute, build_system_prompt, format_column_docs, _parse_sql_response, SQLAgent
from text_to_sql.eval import score
from text_to_sql.db import Database

# guard: only single read-only SELECTs get through
guard("SELECT 1")
guard("WITH x AS (SELECT 1) SELECT * FROM x")
for bad in ["DROP TABLE loan", "SELECT 1; DROP TABLE loan", "DELETE FROM loan", "", "PRAGMA table_info(loan)"]:
    try:
        guard(bad)
        raise AssertionError(f"guard let through: {bad!r}")
    except ValueError:
        pass

# read-only connection is the real boundary
db = Database("data/financial.sqlite")
try:
    db._conn.execute("CREATE TABLE t (x)")
    raise AssertionError("read-only connection allowed a write")
except sqlite3.OperationalError:
    pass

# execute: row cap + working query
r = execute(db, "SELECT COUNT(*) AS n FROM account")
assert r == {"columns": ["n"], "rows": [[4500]]}, r
assert len(execute(db, "SELECT account_id FROM trans")["rows"]) == 100

# scoring: result equality ignores aliases, row order and int/float
assert score([[554]], [{"account_count": 554}])
assert score([[554.0]], [{"x": 554}])
assert not score([[553]], [{"x": 554}])
assert score([["Brno", 10], ["Praha", 2]], [{"d": "Praha", "c": 2}, {"d": "Brno", "c": 10}])

# prompt variants differ in the ways the ablation claims
prompts = {v: build_system_prompt(v, db) for v in ["baseline", "schema_only", "schema_plus_docs", "full"]}
assert prompts["baseline"] == ""
assert "CREATE TABLE" in prompts["schema_only"] and "values:" not in prompts["schema_only"]
assert "values:" in prompts["schema_plus_docs"] and "Examples:" not in prompts["schema_plus_docs"]
assert prompts["full"].startswith(prompts["schema_plus_docs"]) and "Examples:" in prompts["full"]

# response parsing survives a model that ignores the JSON schema
assert _parse_sql_response('{"sql": "SELECT 1", "reasoning": "r"}')["sql"] == "SELECT 1"
assert _parse_sql_response("here you go:\n```sql\nSELECT 1\n```")["sql"] == "SELECT 1"

# "any database" support: no docs dir -> empty docs, not a crash; dataset-specific rules
# stay out of the default prompt and only show up in the opt-in "full" variant
assert format_column_docs("data/does_not_exist") == ""
assert "carry their own" not in prompts["schema_plus_docs"]
assert "carry their own" in prompts["full"]

# connection strings for other engines resolve without a live server (lazy engine creation)
assert Database("postgresql://user:pass@localhost/db").dialect == "postgresql"
assert Database("mysql+pymysql://user:pass@localhost/db").dialect == "mysql"

# Live checks (cost real API calls): python tests/test_agent.py --live
if "--live" in sys.argv:
    assert SQLAgent().ask("How many loans are in status 'A'?")["rows"]

    # The repair path never fires on the shipped config, so force it — and across several
    # distinct error *classes*, not just one, since a single forced failure only proves the
    # retry plumbing works, not that the model can actually recover from the kinds of errors
    # it's likely to produce.
    import text_to_sql.agent as agent_mod

    questions = {q["id"]: q for q in json.loads(open("data/questions.json").read())}
    FAULT_CASES = [
        ("unknown column", "q_03", "no such column: regionn"),
        ("unknown table", "q_01", "no such table: accounts"),
        ("syntax error", "q_02", 'near "FORM": syntax error'),
        ("ambiguous column", "q_04", "ambiguous column name: district_id"),
    ]
    real_execute = agent_mod.execute
    for label, qid, fault_msg in FAULT_CASES:
        q = questions[qid]
        calls = []

        def failing_once(d, sql, _calls=calls, _msg=fault_msg):
            _calls.append(sql)
            if len(_calls) == 1:
                raise sqlite3.OperationalError(_msg)
            return real_execute(d, sql)

        agent_mod.execute = failing_once
        try:
            out = SQLAgent().ask(q["question"])
        finally:
            agent_mod.execute = real_execute
        assert out["repaired"], f"[{label}] repair never fired"
        assert len(calls) == 2, f"[{label}] repair must be capped at one retry"
        assert out["error"] is None and score(out["rows"], q["expected_result"]), \
            f"[{label}] repair did not recover the correct answer: {out}"
        print(f"repair verified ({label}): forced failure -> one repair turn -> correct result")

    # conversation memory: a follow-up should refine the prior query, not start over
    convo = SQLAgent()
    first = convo.ask("How many loans are there?")
    followup = convo.ask("now only for status A")
    assert "loan" in followup["sql"].lower() and "status" in followup["sql"].lower(), followup["sql"]
    assert followup["rows"][0][0] < first["rows"][0][0], (first["rows"], followup["rows"])
    print("follow-up memory verified: refined the prior query using conversation history")

print("all checks passed")
