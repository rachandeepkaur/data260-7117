"""Apply the HW5 migration (code/hw05/migration.sql) and seed the inspectors.

    make migrate-hw05        (or: python code/hw05/migrate.py)

Run after the HW4 setup (make setup-db && make seed). Idempotent: each
ALTER block is skipped when information_schema shows it was already applied.
The 20 inspectors are generated from SEED = 7117, so ids/emails are the same
on every machine.
"""
from __future__ import annotations

import random
import re

from sqlalchemy import create_engine, text

from hw05_config import DB_NAME, HW05_CODE_DIR, MYSQL_ADMIN_URL, N_INSPECTORS, SEED

FIRST = ["Maria", "James", "Linh", "Priya", "Carlos", "Aisha", "Daniel", "Mei", "Omar", "Sofia",
         "Kevin", "Grace", "Ravi", "Elena", "Marcus", "Hana", "Diego", "Nora", "Arjun", "Tara"]
LAST = ["Nguyen", "Garcia", "Patel", "Kim", "Lopez", "Chen", "Singh", "Martinez", "Tran", "Rivera",
        "Kaur", "Wong", "Hernandez", "Shah", "Lee", "Ramos"]
DISTRICTS = ["Downtown San Jose", "East San Jose", "Evergreen", "Willow Glen", "North San Jose",
             "Almaden Valley", "Berryessa", "Cambrian", "West San Jose", "Alum Rock"]


def load_blocks() -> dict[str, str]:
    sql = (HW05_CODE_DIR / "migration.sql").read_text(encoding="utf-8")
    blocks: dict[str, str] = {}
    for chunk in re.split(r"^-- @block ", sql, flags=re.M)[1:]:
        name, _, body = chunk.partition("\n")
        body = "\n".join(l for l in body.splitlines() if not l.strip().startswith("--"))
        blocks[name.strip()] = body.strip().rstrip(";")
    return blocks


def generate_inspectors(rng: random.Random) -> list[dict]:
    rows, used = [], set()
    while len(rows) < N_INSPECTORS:
        first, last = rng.choice(FIRST), rng.choice(LAST)
        email = f"{first}.{last}@sccgov-eh.org".lower()
        if email in used:
            continue
        used.add(email)
        rows.append({"full_name": f"{first} {last}", "district": rng.choice(DISTRICTS), "email": email})
    return rows


def column_exists(conn, table: str, column: str) -> bool:
    return bool(conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = :db AND table_name = :t AND column_name = :c"
    ), {"db": DB_NAME, "t": table, "c": column}).scalar())


def constraint_exists(conn, name: str) -> bool:
    return bool(conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.table_constraints "
        "WHERE table_schema = :db AND constraint_name = :n"
    ), {"db": DB_NAME, "n": name}).scalar())


def main() -> None:
    say = print
    blocks = load_blocks()
    engine = create_engine(f"{MYSQL_ADMIN_URL}{DB_NAME}", isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text(blocks["create_inspectors"]))
        say("inspectors table: ok")

        if conn.execute(text("SELECT COUNT(*) FROM inspectors")).scalar() == 0:
            rows = generate_inspectors(random.Random(SEED))
            conn.execute(text(
                "INSERT INTO inspectors (full_name, district, email) VALUES (:full_name, :district, :email)"
            ), rows)
            say(f"seeded {len(rows)} inspectors (SEED={SEED})")
        else:
            say("inspectors already seeded - skipped")

        if not column_exists(conn, "inspections", "inspection_code"):
            conn.execute(text(blocks["add_inspection_columns"]))
            say("inspections: added inspection_code, score, inspector_id, created_at, updated_at")
        else:
            say("inspections columns already present - skipped")

        updated = conn.execute(text(blocks["backfill_inspections"])).rowcount
        say(f"backfilled {updated} inspections")

        if not constraint_exists(conn, "fk_inspections_inspector"):
            conn.execute(text(blocks["constrain_inspections"]))
            say("inspections: NOT NULL + UNIQUE(inspection_code) + CHECK(score) + FK -> inspectors (ON DELETE RESTRICT)")
        else:
            say("constraints already present - skipped")

        for table in ("inspectors", "inspections"):
            ddl = conn.execute(text(f"SHOW CREATE TABLE {table}")).one()[1]
            say(ddl)
        counts = conn.execute(text(
            "SELECT (SELECT COUNT(*) FROM inspectors), (SELECT COUNT(*) FROM inspections)"
        )).one()
        say(f"row counts: inspectors={counts[0]} inspections={counts[1]}")


if __name__ == "__main__":
    main()
