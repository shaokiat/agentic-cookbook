import sqlite3
import time
from typing import Any, Dict

DEFAULT_DB_PATH = "data/financial.sqlite"
DEFAULT_DESCRIPTION_DIR = "data/database_description"

# Dialect-level SQL quirks worth telling the model about. Anything specific to *this*
# dataset's schema (table/column names, business rules) belongs in hints.md, not here.
DIALECT_NOTES = {
    "sqlite": (
        "- SQLite dialect: no FULL OUTER JOIN, no RIGHT JOIN, no window functions unless needed.\n"
        "- SQLite text comparison is case-sensitive by default. When filtering on a text value whose\n"
        "  exact stored casing you are not certain of, add COLLATE NOCASE rather than assuming\n"
        "  standard capitalization.\n"
        "- SQLite has no native DATE type: a DATE column holds plain text (commonly 'YYYY-MM-DD').\n"
        "  Filter by year/month with strftime, never string prefix or substring matching — the\n"
        "  stored format is not guaranteed and that silently matches the wrong rows or none.\n"
        "- Quote reserved words used as identifiers with double quotes."
    ),
    "postgresql": (
        "- PostgreSQL dialect: prefer ILIKE for case-insensitive text matching instead of wrapping\n"
        "  both sides in LOWER().\n"
        "- Quote reserved words used as identifiers with double quotes."
    ),
    "mysql": (
        "- MySQL dialect: identifiers are back-tick quoted, not double-quoted.\n"
        "- Text comparison is case-insensitive by default under the common *_ci collations; don't\n"
        "  add redundant LOWER()/UPPER() calls."
    ),
}

# Best-effort server-side statement timeout, set per connection before running the query.
# ponytail: only sqlite/postgres/mysql are wired up; a dialect not in this table (mssql,
# oracle, ...) still runs, just without an enforced timeout — add its SET/PRAGMA here.
_TIMEOUT_SQL = {
    "postgresql": "SET statement_timeout = {ms}",
    "mysql": "SET SESSION MAX_EXECUTION_TIME={ms}",
}
_READONLY_SQL = {
    "postgresql": "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY",
    "mysql": "SET SESSION TRANSACTION READ ONLY",
}


class Database:
    """One read-only interface over a SQLite file or any SQLAlchemy-supported database
    (Postgres, MySQL, ...), so the agent can point at 'any database' via a connection
    string the same way it points at a local .sqlite file.

    A bare path with no '://' is treated as a SQLite file path; anything else is passed
    straight to SQLAlchemy as a connection URL.
    """

    def __init__(self, db: str):
        if "://" not in db:
            self.dialect = "sqlite"
            self._conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, check_same_thread=False)
            self._engine = None
        else:
            from sqlalchemy import create_engine

            self._engine = create_engine(db)
            self.dialect = self._engine.dialect.name
            self._conn = None

    def ddl(self) -> str:
        """Schema description for the prompt: exact DDL for sqlite, introspected for others."""
        if self.dialect == "sqlite":
            rows = self._conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL ORDER BY name"
            ).fetchall()
            return "\n".join(r[0] for r in rows)

        from sqlalchemy import inspect

        insp = inspect(self._engine)
        lines = []
        for table in insp.get_table_names():
            pk_cols = set(insp.get_pk_constraint(table).get("constrained_columns") or [])
            cols = ", ".join(
                f"{c['name']} {c['type']}" + (" PRIMARY KEY" if c["name"] in pk_cols else "")
                for c in insp.get_columns(table)
            )
            lines.append(f"CREATE TABLE {table} ({cols});")
            for fk in insp.get_foreign_keys(table):
                if fk.get("constrained_columns"):
                    lines.append(
                        f"-- FOREIGN KEY {table}.{fk['constrained_columns'][0]} "
                        f"REFERENCES {fk['referred_table']}.{fk['referred_columns'][0]}"
                    )
        return "\n".join(lines)

    def run(self, sql: str, max_rows: int, timeout_s: float) -> Dict[str, Any]:
        """EXPLAIN (parse check, no I/O) then run with a row cap and a best-effort timeout."""
        if self.dialect == "sqlite":
            self._conn.execute("EXPLAIN " + sql)
            deadline = time.monotonic() + timeout_s
            self._conn.set_progress_handler(lambda: time.monotonic() > deadline, 10000)
            try:
                cur = self._conn.execute(sql)
                rows = cur.fetchmany(max_rows)
                cols = [d[0] for d in cur.description] if cur.description else []
            finally:
                self._conn.set_progress_handler(None, 0)
            return {"columns": cols, "rows": [list(r) for r in rows]}

        from sqlalchemy import text

        with self._engine.connect() as conn:
            if self.dialect in _READONLY_SQL:
                conn.execute(text(_READONLY_SQL[self.dialect]))
            if self.dialect in _TIMEOUT_SQL:
                conn.execute(text(_TIMEOUT_SQL[self.dialect].format(ms=int(timeout_s * 1000))))
            conn.execute(text("EXPLAIN " + sql))
            result = conn.execute(text(sql))
            cols = list(result.keys())
            rows = [list(r) for r in result.fetchmany(max_rows)]
            return {"columns": cols, "rows": rows}

    def close(self) -> None:
        if self._conn:
            self._conn.close()
        if self._engine:
            self._engine.dispose()
