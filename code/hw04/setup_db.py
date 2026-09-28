"""Create the s7117_rel database, its tables (schema.sql), and the app user.

    python code/hw04/setup_db.py            # idempotent
    python code/hw04/setup_db.py --reset    # drop and recreate s7117_rel first
"""
from __future__ import annotations

import argparse

from sqlalchemy import create_engine, text

from hw04_config import APP_DB_PASSWORD, APP_DB_USER, DB_NAME, HW04_CODE_DIR, MYSQL_ADMIN_URL


def run_sql_file(conn, path) -> None:
    sql = path.read_text(encoding="utf-8")
    body = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    for statement in body.split(";"):
        if statement.strip():
            conn.execute(text(statement))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help=f"drop {DB_NAME} before creating it")
    args = parser.parse_args()

    engine = create_engine(MYSQL_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        version = conn.execute(text("SELECT VERSION()")).scalar()
        print(f"Connected to MySQL {version}")
        if args.reset:
            conn.execute(text(f"DROP DATABASE IF EXISTS {DB_NAME}"))
            print(f"Dropped {DB_NAME}")
        run_sql_file(conn, HW04_CODE_DIR / "schema.sql")
        # '%' as well as localhost: with MySQL in Docker, host connections arrive
        # from the container's gateway address, not 127.0.0.1.
        for host in ("localhost", "127.0.0.1", "%"):
            conn.execute(text(
                f"CREATE USER IF NOT EXISTS '{APP_DB_USER}'@'{host}' IDENTIFIED BY '{APP_DB_PASSWORD}'"
            ))
            conn.execute(text(f"GRANT ALL PRIVILEGES ON {DB_NAME}.* TO '{APP_DB_USER}'@'{host}'"))
        tables = [row[0] for row in conn.execute(text(f"SHOW TABLES FROM {DB_NAME}"))]
        print(f"{DB_NAME} tables: {tables}")


if __name__ == "__main__":
    main()
