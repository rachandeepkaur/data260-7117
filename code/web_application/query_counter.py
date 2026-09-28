"""Per-request SQL statement counter, used for the N+1 measurements.

A SQLAlchemy `before_cursor_execute` listener increments a thread-local
counter while a `count_queries()` block is active. FastAPI runs sync
endpoints in a worker thread, and every statement an endpoint issues runs on
that same thread, so a thread-local is enough to isolate concurrent requests.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager

from sqlalchemy import event
from sqlalchemy.engine import Engine

_local = threading.local()


class QueryCount:
    def __init__(self) -> None:
        self.count = 0
        self.statements: list[str] = []


def install(engine: Engine) -> None:
    @event.listens_for(engine, "before_cursor_execute")
    def _count(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        counter = getattr(_local, "counter", None)
        if counter is not None:
            counter.count += 1
            counter.statements.append(statement)


@contextmanager
def count_queries():
    counter = QueryCount()
    _local.counter = counter
    try:
        yield counter
    finally:
        _local.counter = None
