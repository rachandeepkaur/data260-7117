"""SQLAlchemy engine/session setup for the MySQL database (HW4).

Database name follows the assignment convention <PREFIX>_rel -> s7117_rel.
Override the connection with the DATABASE_URL env var; the default points at
a local MySQL with the dev-only app user created by code/hw04/setup_db.py.
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

import query_counter

PREFIX = "s7117"
DB_NAME = f"{PREFIX}_rel"

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"mysql+pymysql://s7117_app:s7117_dev_pw@127.0.0.1:3306/{DB_NAME}?charset=utf8mb4",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=10)

# Counts every SQL statement sent to MySQL, so the N+1 endpoints can report
# exactly how many queries a request triggered.
query_counter.install(engine)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: one SQLAlchemy session per request.

    Endpoints receive it as `db_session_basede26` (the required variable name
    for the database connection)."""
    db_session_basede26: Session = SessionLocal()
    try:
        yield db_session_basede26
    finally:
        db_session_basede26.close()
