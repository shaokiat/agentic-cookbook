"""Text-to-SQL agent: prompt assembly, LLM call, guard, execute, one repair."""

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

from text_to_sql.db import DEFAULT_DB_PATH, DEFAULT_DESCRIPTION_DIR, DIALECT_NOTES, Database

load_dotenv()

# Any OpenAI-compatible endpoint: Fireworks by default, or point LLM_API_BASE at a local
# vLLM/Ollama server (see the cookbook root README's self-hosted-inference section).
DEFAULT_API_BASE = "https://api.fireworks.ai/inference/v1"
DEFAULT_MODEL = "accounts/fireworks/models/gpt-oss-120b"
# "full" = schema_plus_docs + optional dataset hints (hints.md), which no-ops to
# schema_plus_docs on any database that doesn't ship one — a strict, gracefully degrading
# superset. See the ablation in README.md.
DEFAULT_VARIANT = "full"
MAX_ROWS = 100
QUERY_TIMEOUT_S = 10.0
HISTORY_TURNS = 6  # user+assistant messages kept for follow-ups
MAX_COMPLETION_TOKENS = 800
MAX_REPAIRS = 1  # hard cap: one regenerate-and-retry on execution failure, no loop

# $ per 1M tokens. Used for the $/query estimate only; unpriced models still run, just at $0.
PRICING = {
    "accounts/fireworks/models/gpt-oss-120b": (0.15, 0.60),
    "accounts/fireworks/models/deepseek-v4p1-flash": (0.22, 0.66),
    "accounts/fireworks/models/glm-5p3-flash": (0.15, 0.50),
}

DIALECT_RULES = """You translate natural-language questions into SQL for a {dialect} database.

Rules:
- Emit exactly one SELECT statement. No INSERT/UPDATE/DELETE/DDL, no semicolon-separated batches.
{dialect_notes}
- Use the documented code values literally (e.g. status = 'A'), never invent new ones.
- Return only columns the question asks for, and alias aggregates readably.
- Keep `reasoning` to one short sentence."""

SCHEMA_ONLY_SUFFIX = "\n\nDatabase schema (DDL):\n{ddl}"
DOCS_SUFFIX = "\n\nColumn documentation (name | meaning | value decoding):\n{docs}"
HINTS_SUFFIX = "\n\n{hints}"

BASELINE_PROMPT = "Convert this question to SQL: {question}"
STRUCTURED_JSON_HINT = '\n\nReturn JSON: {"sql": ..., "reasoning": ...}'
REPAIR_PROMPT = (
    "That SQL failed.\nQuestion: {question}\nSQL: {sql}\n"
    "Database error: {error}\nReturn corrected JSON with the same shape."
)

SQL_SCHEMA = {
    "type": "object",
    "properties": {"sql": {"type": "string"}, "reasoning": {"type": "string"}},
    "required": ["sql", "reasoning"],
}


def format_column_docs(description_dir: str = DEFAULT_DESCRIPTION_DIR) -> str:
    """One line per column: table.column | description | value decoding.

    Optional: most databases won't ship this kind of CSV documentation, so a missing
    directory just means no docs section rather than a crash.
    """
    from pathlib import Path
    import csv

    root = Path(description_dir)
    if not root.is_dir():
        return ""
    lines = []
    for csv_path in sorted(root.glob("*.csv")):
        table = csv_path.stem
        with csv_path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                col = (row.get("original_column_name") or "").strip()
                desc = (row.get("column_name") or "").strip()
                meaning = (row.get("column_description") or "").strip()
                values = re.sub(r"\s+", " ", (row.get("value_description") or "").strip())
                parts = [p for p in (desc, meaning) if p and p.lower() != col.lower()]
                line = f"{table}.{col}: {' / '.join(dict.fromkeys(parts))}"
                if values:
                    line += f" | values: {values}"
                lines.append(line)
    return "\n".join(lines)


def load_hints(description_dir: str = DEFAULT_DESCRIPTION_DIR) -> str:
    """Optional freeform notes about this specific dataset (business rules, quirks) that
    don't belong in the dialect-level prompt. Returns "" when there's no hints.md — most
    databases won't have one, and that's fine.
    """
    from pathlib import Path

    path = Path(description_dir) / "hints.md"
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def _dialect_and_schema_section(prompt: str, db: Database, description_dir: str) -> str:
    notes = DIALECT_NOTES.get(db.dialect, "")
    prompt += DIALECT_RULES.format(dialect=db.dialect, dialect_notes=notes)
    return prompt + SCHEMA_ONLY_SUFFIX.format(ddl=db.ddl())


def _docs_section(prompt: str, db: Database, description_dir: str) -> str:
    docs = format_column_docs(description_dir)
    return prompt + DOCS_SUFFIX.format(docs=docs) if docs else prompt


def _hints_section(prompt: str, db: Database, description_dir: str) -> str:
    hints = load_hints(description_dir)
    return prompt + HINTS_SUFFIX.format(hints=hints) if hints else prompt


# Each variant is the cumulative list of sections it includes, in order. The name is the
# single source of truth for "what variants exist".
PROMPT_VARIANTS = {
    "baseline": [],  # zero-schema prompt: what most naive text-to-SQL prototypes ship with
    "schema_only": [_dialect_and_schema_section],
    "schema_plus_docs": [_dialect_and_schema_section, _docs_section],
    "full": [_dialect_and_schema_section, _docs_section, _hints_section],
}


def build_system_prompt(
    variant: str = DEFAULT_VARIANT,
    db: Optional[Database] = None,
    description_dir: str = DEFAULT_DESCRIPTION_DIR,
) -> str:
    """Prompt variants for the ablation, each one a superset of the last."""
    if variant not in PROMPT_VARIANTS:
        raise ValueError(f"unknown prompt variant: {variant}")
    prompt = ""
    for section in PROMPT_VARIANTS[variant]:
        prompt = section(prompt, db, description_dir)
    return prompt


# --- guard + execute ---------------------------------------------------------

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum)\b", re.I
)


def guard(sql: str) -> None:
    """Reject anything that is not a single read-only SELECT. Raises ValueError."""
    stripped = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql, flags=re.S).strip().rstrip(";").strip()
    if not stripped:
        raise ValueError("empty SQL")
    if ";" in stripped:
        raise ValueError("multiple statements are not allowed")
    if not re.match(r"^(select|with)\b", stripped, re.I):
        raise ValueError("only SELECT statements are allowed")
    if FORBIDDEN.search(stripped):
        raise ValueError("only SELECT statements are allowed")


def execute(db: Database, sql: str) -> Dict[str, Any]:
    guard(sql)
    return db.run(sql.strip().rstrip(";"), MAX_ROWS, QUERY_TIMEOUT_S)


# --- agent -------------------------------------------------------------------


class SQLAgent:
    """Single LLM call per question, plus at most one repair attempt on execution error."""

    def __init__(
        self,
        db: Optional[Database] = None,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        variant: str = DEFAULT_VARIANT,
        db_path: str = DEFAULT_DB_PATH,
        description_dir: str = DEFAULT_DESCRIPTION_DIR,
    ):
        # Read-only: the real guard against writes, regardless of what the model emits.
        # db_path may be a plain SQLite file path or any SQLAlchemy connection string
        # (postgresql://, mysql+pymysql://, ...) — "any database" via a connection string.
        self.db = db or Database(db_path)
        self.model = model or os.environ.get("LLM_MODEL", DEFAULT_MODEL)
        self.variant = variant
        self.system_prompt = (
            system_prompt
            if system_prompt is not None
            else build_system_prompt(variant, self.db, description_dir)
        )
        self.client = OpenAI(
            base_url=os.environ.get("LLM_API_BASE", DEFAULT_API_BASE),
            api_key=os.environ["LLM_API_KEY"],
            timeout=60,
        )
        self.messages: List[Dict[str, str]] = []

    # -- LLM ---------------------------------------------------------------

    def _complete(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        full = ([{"role": "system", "content": self.system_prompt}] if self.system_prompt else []) + messages
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=full,
            temperature=0,
            max_tokens=MAX_COMPLETION_TOKENS,
            response_format={"type": "json_object", "schema": SQL_SCHEMA},
        )
        content = resp.choices[0].message.content or ""
        return {
            "parsed": _parse_sql_response(content),
            "usage": (resp.usage.prompt_tokens, resp.usage.completion_tokens),
        }

    def _generate(self, messages: List[Dict[str, str]]) -> tuple:
        """One LLM call -> (sql, reasoning, prompt_tokens, completion_tokens)."""
        out = self._complete(messages)
        prompt_tokens, completion_tokens = out["usage"]
        return out["parsed"]["sql"], out["parsed"]["reasoning"], prompt_tokens, completion_tokens

    def ask(self, question: str) -> Dict[str, Any]:
        """Question -> {sql, reasoning, columns, rows, error, repaired, latency_s, tokens, cost_usd}."""
        started = time.monotonic()
        user_msg = (
            BASELINE_PROMPT.format(question=question)
            if self.variant == "baseline"
            else question + STRUCTURED_JSON_HINT
        )
        history = self.messages[-HISTORY_TURNS:] + [{"role": "user", "content": user_msg}]

        sql, reasoning, prompt_tokens, completion_tokens = self._generate(history)
        repaired, error = False, None

        try:
            result = execute(self.db, sql)
        except Exception as first_error:  # noqa: BLE001 - any failure feeds the repair turn
            repaired = True
            repair_msg = REPAIR_PROMPT.format(question=question, sql=sql, error=first_error)
            try:
                sql, reasoning, pt, ct = self._generate(history + [{"role": "user", "content": repair_msg}])
                prompt_tokens += pt
                completion_tokens += ct
                result = execute(self.db, sql)  # MAX_REPAIRS = 1: no further retry
            except Exception as second_error:  # noqa: BLE001
                result = {"columns": [], "rows": []}
                error = str(second_error)

        self.messages = (history + [{"role": "assistant", "content": sql}])[-HISTORY_TURNS:]
        price_in, price_out = PRICING.get(self.model, (0.0, 0.0))
        return {
            "question": question,
            "sql": sql,
            "reasoning": reasoning,
            "columns": result["columns"],
            "rows": result["rows"],
            "error": error,
            "repaired": repaired,
            "latency_s": round(time.monotonic() - started, 3),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": (prompt_tokens * price_in + completion_tokens * price_out) / 1e6,
        }


def _parse_sql_response(content: str) -> Dict[str, str]:
    """Structured output is JSON; fall back to a fenced/bare SQL scrape if the model ignores it."""
    try:
        data = json.loads(content)
        if isinstance(data, dict) and data.get("sql"):
            return {"sql": str(data["sql"]).strip(), "reasoning": str(data.get("reasoning", ""))}
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:sql)?\s*(.+?)```", content, re.S)
    sql = fenced.group(1) if fenced else content
    match = re.search(r"\b(with|select)\b.*", sql, re.S | re.I)
    return {"sql": (match.group(0) if match else sql).strip(), "reasoning": ""}
