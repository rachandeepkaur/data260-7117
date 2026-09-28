"""EXPLAIN before/after adding one index (HW4 Part 3.8).

    python code/hw04/explain_index.py

1. Drops ix_violations_inspection_id if present (so "before" is reproducible).
2. EXPLAINs the two violation lookups the N+1 endpoints issue:
     naive: SELECT ... FROM inspection_violations WHERE inspection_id = ? ORDER BY id
     fixed: SELECT ... FROM inspection_violations WHERE inspection_id IN (1..200)
   in both the tabular form and EXPLAIN ANALYZE (actual rows / time).
3. Applies code/hw04/add_index.sql and repeats the EXPLAINs.

Writes raw/explain_before_after.txt and raw/explain_before_after.json.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import text

from hw04_config import HW04_CODE_DIR, RAW_DIR, use_web_app_imports

use_web_app_imports()
from database import engine  # noqa: E402

INDEX_NAME = "ix_violations_inspection_id"

QUERIES = {
    "naive_per_record_lookup": (
        "SELECT id, inspection_id, violation_code, description, severity, points_deducted, observed_on "
        "FROM inspection_violations WHERE inspection_id = 42 ORDER BY id"
    ),
    "fixed_selectin_lookup_page200": (
        "SELECT id, inspection_id, violation_code, description, severity, points_deducted, observed_on "
        "FROM inspection_violations WHERE inspection_id IN ("
        + ", ".join(str(i) for i in range(1, 201)) + ") ORDER BY id"
    ),
}


def index_exists(conn) -> bool:
    return bool(conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.statistics "
        "WHERE table_schema = DATABASE() AND table_name = 'inspection_violations' AND index_name = :n"
    ), {"n": INDEX_NAME}).scalar())


def explain(conn, sql: str) -> dict:
    result = conn.execute(text(f"EXPLAIN {sql}"))
    columns = list(result.keys())
    rows = [dict(zip(columns, row)) for row in result]
    analyze = conn.execute(text(f"EXPLAIN ANALYZE {sql}")).scalar()
    return {"columns": columns, "rows": rows, "analyze": analyze}


def format_table(plan: dict) -> str:
    cols = ["id", "select_type", "table", "type", "possible_keys", "key", "key_len", "ref", "rows", "filtered", "Extra"]
    cols = [c for c in cols if c in plan["columns"]]
    cells = [[str(r.get(c)) for c in cols] for r in plan["rows"]]
    widths = [max(len(c), *(len(row[i]) for row in cells)) for i, c in enumerate(cols)]
    line = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    out = [line, "| " + " | ".join(c.ljust(w) for c, w in zip(cols, widths)) + " |", line]
    out += ["| " + " | ".join(v.ljust(w) for v, w in zip(row, widths)) + " |" for row in cells]
    out.append(line)
    return "\n".join(out)


def snapshot(conn, label: str) -> dict:
    conn.execute(text("ANALYZE TABLE inspection_violations"))
    idx_rows = conn.execute(text("SHOW INDEX FROM inspection_violations"))
    indexes = [{"Key_name": r.Key_name, "Column_name": r.Column_name} for r in idx_rows]
    return {
        "label": label,
        "indexes": indexes,
        "plans": {name: explain(conn, sql) for name, sql in QUERIES.items()},
    }


def main() -> None:
    lines: list[str] = [f"# EXPLAIN before/after - generated {datetime.now(timezone.utc).isoformat()}"]
    with engine.connect() as conn:
        version = conn.execute(text("SELECT VERSION()")).scalar()
        lines.append(f"# MySQL {version}, database {conn.execute(text('SELECT DATABASE()')).scalar()}")
        if index_exists(conn):
            conn.execute(text(f"DROP INDEX {INDEX_NAME} ON inspection_violations"))
            conn.commit()
            lines.append(f"# dropped existing {INDEX_NAME} to capture the 'before' state")

        before = snapshot(conn, "before")

        add_index_sql = (HW04_CODE_DIR / "add_index.sql").read_text(encoding="utf-8")
        statement = [s for s in add_index_sql.split(";") if "CREATE INDEX" in s][0]
        statement = "\n".join(l for l in statement.splitlines() if not l.strip().startswith("--")).strip()
        conn.execute(text(statement))
        conn.commit()
        lines.append(f"# applied: {statement}")

        after = snapshot(conn, "after")

    for snap in (before, after):
        lines.append("")
        lines.append("=" * 100)
        lines.append(f"{snap['label'].upper()} - indexes on inspection_violations: "
                     f"{[(i['Key_name'], i['Column_name']) for i in snap['indexes']]}")
        for name, plan in snap["plans"].items():
            lines.append("")
            lines.append(f"-- {name}: EXPLAIN {QUERIES[name][:110]}{'...' if len(QUERIES[name]) > 110 else ''}")
            lines.append(format_table(plan))
            lines.append("EXPLAIN ANALYZE:")
            lines.append(plan["analyze"].rstrip())

    report = "\n".join(lines) + "\n"
    print(report)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "explain_before_after.txt").write_text(report, encoding="utf-8")
    (RAW_DIR / "explain_before_after.json").write_text(
        json.dumps({"queries": QUERIES, "before": before, "after": after}, indent=2, default=str), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
