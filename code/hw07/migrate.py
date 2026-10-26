"""Apply the HW7 migration (code/hw07/migration.sql) and create one user per role.

    make migrate-hw07        (or: python code/hw07/migrate.py)

Run after the HW4/HW5 setup (make setup-db seed migrate-hw05). Idempotent:
each ALTER block is skipped when information_schema shows it was already
applied, and existing role users only get their role/password refreshed.
Passwords are stored as PBKDF2-SHA256 hashes (security.hash_password).
"""
from __future__ import annotations

import re

from sqlalchemy import create_engine, text

from hw07_config import DB_NAME, HW07_CODE_DIR, MYSQL_ADMIN_URL, PREFIX, ROLE_PASSWORD, ROLE_USERS, use_web_app_imports

use_web_app_imports()
from security import hash_password  # noqa: E402


def load_blocks() -> dict[str, str]:
    """Split migration.sql into its named `-- @block` statements."""
    sql = (HW07_CODE_DIR / "migration.sql").read_text(encoding="utf-8")
    blocks: dict[str, str] = {}
    for chunk in re.split(r"^-- @block ", sql, flags=re.M)[1:]:
        name, _, body = chunk.partition("\n")
        body = "\n".join(line for line in body.splitlines() if not line.strip().startswith("--"))
        blocks[name.strip()] = body.strip().rstrip(";")
    return blocks


def column_exists(conn, table: str, column: str) -> bool:
    """True if `table.column` exists in s7117_rel."""
    return bool(conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = :db AND table_name = :t AND column_name = :c"
    ), {"db": DB_NAME, "t": table, "c": column}).scalar())


def constraint_exists(conn, name: str) -> bool:
    """True if a constraint (unique key, check, FK) called `name` exists in s7117_rel."""
    return bool(conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.table_constraints "
        "WHERE table_schema = :db AND constraint_name = :n"
    ), {"db": DB_NAME, "n": name}).scalar())


def upsert_role_users(conn) -> None:
    """Create (or refresh) the reader / writer / moderator demo users."""
    for role, username in ROLE_USERS.items():
        row = conn.execute(text("SELECT id FROM users WHERE username = :u"), {"u": username}).first()
        params = {"u": username, "r": role, "h": hash_password(ROLE_PASSWORD),
                  "n": f"{role.title()} (HW7)", "e": f"{role}@{PREFIX}.dev"}
        if row is None:
            conn.execute(text(
                "INSERT INTO users (username, name, email, password_hash, role) VALUES (:u, :n, :e, :h, :r)"
            ), params)
            print(f"created user {username} (role={role})")
        else:
            conn.execute(text("UPDATE users SET role = :r, password_hash = :h WHERE username = :u"), params)
            print(f"user {username} exists - role/password refreshed (role={role})")


def main() -> None:
    """Run the migration blocks that have not been applied yet, then seed the role users."""
    blocks = load_blocks()
    engine = create_engine(f"{MYSQL_ADMIN_URL}{DB_NAME}", isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        if not column_exists(conn, "users", "username"):
            conn.execute(text(blocks["add_user_columns"]))
            print("users: added username + role columns")
        else:
            print("users.username/role already present - skipped")

        updated = conn.execute(text(blocks["backfill_usernames"])).rowcount
        print(f"backfilled username for {updated} existing user(s)")

        if not constraint_exists(conn, "uq_users_username"):
            conn.execute(text(blocks["constrain_users"]))
            print("users: username NOT NULL + UNIQUE, role CHECK (reader|writer|moderator)")
        else:
            print("users constraints already present - skipped")

        upsert_role_users(conn)
        rows = conn.execute(text(
            "SELECT id, username, role, LEFT(password_hash, 22) AS hash_prefix FROM users ORDER BY id"
        )).mappings().all()
        print("\nusers table (password_hash truncated - only hashes are stored):")
        for r in rows:
            print(f"  id={r['id']:<3} username={r['username']:<20} role={r['role']:<10} {r['hash_prefix']}...")


if __name__ == "__main__":
    main()
