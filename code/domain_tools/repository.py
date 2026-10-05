"""Storage backends the domain tools read from (dependency injection).

- SqlRepository: the real s7117_rel MySQL database (inspections, inspectors,
  inspection_violations), with connect/read timeouts on the driver.
- InMemoryRepository: the same three queries over plain Python lists, used by
  the offline tests and `--offline` experiment runs.
- FaultyRepository: wraps either one and injects failures (Part 3).

All three return plain dicts/lists so results serialize straight into the
{ok, data, error} envelope.
"""
from __future__ import annotations

import os
import re
from typing import Any, Optional, Protocol

PASS_SCORE = 70  # a score below 70 is a failed inspection

DEFAULT_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://s7117_app:s7117_dev_pw@127.0.0.1:3306/s7117_rel?charset=utf8mb4",
)


class InspectionRepository(Protocol):
    def search(self, query: str, limit: int, min_score: Optional[int]) -> list[dict]: ...

    def get_by_code(self, inspection_code: str) -> Optional[dict]: ...

    def stats(self, inspector_id: Optional[int], zip_code: Optional[str],
              facility_query: Optional[str]) -> dict: ...


def _summarize(scores: list[int], violation_count: int) -> dict:
    n = len(scores)
    return {
        "inspection_count": n,
        "avg_score": round(sum(scores) / n, 2) if n else None,
        "min_score": min(scores) if n else None,
        "max_score": max(scores) if n else None,
        "pass_rate": round(sum(s >= PASS_SCORE for s in scores) / n, 4) if n else None,
        "violation_count": violation_count,
    }


class SqlRepository:
    """Reads s7117_rel with SQLAlchemy Core. The engine is created lazily so
    importing this module (e.g. in offline tests) never touches MySQL."""

    def __init__(self, url: str = DEFAULT_DATABASE_URL, connect_timeout: int = 3, read_timeout: int = 5):
        self._url = url
        self._connect_args = {"connect_timeout": connect_timeout, "read_timeout": read_timeout,
                              "write_timeout": read_timeout}
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            from sqlalchemy import create_engine

            self._engine = create_engine(self._url, pool_pre_ping=True, pool_size=5,
                                         connect_args=self._connect_args)
        return self._engine

    def _rows(self, sql: str, params: dict) -> list[dict]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(text(sql), params)]

    def search(self, query: str, limit: int, min_score: Optional[int]) -> list[dict]:
        return self._rows(
            "SELECT id, inspection_code, facility_name, site_address, score, inspector_id "
            "FROM inspections "
            "WHERE (facility_name LIKE :q OR site_address LIKE :q OR inspection_code = :exact) "
            "AND (:min_score IS NULL OR score >= :min_score) "
            "ORDER BY id LIMIT :limit",
            {"q": f"%{query}%", "exact": query.upper(), "min_score": min_score, "limit": limit},
        )

    def get_by_code(self, inspection_code: str) -> Optional[dict]:
        rows = self._rows(
            "SELECT i.id, i.inspection_code, i.facility_name, i.site_address, i.score, "
            "i.created_at, i.updated_at, n.id AS inspector_id, n.full_name AS inspector_name, "
            "n.district AS inspector_district "
            "FROM inspections i JOIN inspectors n ON n.id = i.inspector_id "
            "WHERE i.inspection_code = :code",
            {"code": inspection_code},
        )
        if not rows:
            return None
        record = rows[0]
        record["violations"] = self._rows(
            "SELECT violation_code, description, severity, points_deducted, observed_on "
            "FROM inspection_violations WHERE inspection_id = :id ORDER BY id",
            {"id": record["id"]},
        )
        return record

    def stats(self, inspector_id: Optional[int], zip_code: Optional[str],
              facility_query: Optional[str]) -> dict:
        where, params = ["1 = 1"], {}
        if inspector_id is not None:
            where.append("i.inspector_id = :inspector_id")
            params["inspector_id"] = inspector_id
        if zip_code is not None:
            where.append("i.site_address LIKE :zip")
            params["zip"] = f"%CA {zip_code}"
        if facility_query is not None:
            where.append("i.facility_name LIKE :fq")
            params["fq"] = f"%{facility_query}%"
        cond = " AND ".join(where)
        scores = [r["score"] for r in self._rows(f"SELECT i.score FROM inspections i WHERE {cond}", params)]
        violations = self._rows(
            f"SELECT COUNT(*) AS n FROM inspection_violations v "
            f"JOIN inspections i ON i.id = v.inspection_id WHERE {cond}", params,
        )[0]["n"]
        return _summarize(scores, int(violations))


class InMemoryRepository:
    """Same contract as SqlRepository over in-memory fixtures (no I/O)."""

    def __init__(self, inspections: list[dict], inspectors: list[dict], violations: list[dict]):
        self.inspections = inspections
        self.inspectors = {i["id"]: i for i in inspectors}
        self.violations = violations

    def search(self, query: str, limit: int, min_score: Optional[int]) -> list[dict]:
        q = query.lower()
        hits = [
            {k: r[k] for k in ("id", "inspection_code", "facility_name", "site_address", "score", "inspector_id")}
            for r in sorted(self.inspections, key=lambda r: r["id"])
            if (q in r["facility_name"].lower() or q in r["site_address"].lower()
                or r["inspection_code"] == query.upper())
            and (min_score is None or r["score"] >= min_score)
        ]
        return hits[:limit]

    def get_by_code(self, inspection_code: str) -> Optional[dict]:
        for r in self.inspections:
            if r["inspection_code"] == inspection_code:
                inspector = self.inspectors[r["inspector_id"]]
                return {
                    **{k: v for k, v in r.items()},
                    "inspector_name": inspector["full_name"],
                    "inspector_district": inspector["district"],
                    "violations": [
                        {k: v[k] for k in ("violation_code", "description", "severity", "points_deducted")}
                        for v in self.violations if v["inspection_id"] == r["id"]
                    ],
                }
        return None

    def stats(self, inspector_id: Optional[int], zip_code: Optional[str],
              facility_query: Optional[str]) -> dict:
        rows = [
            r for r in self.inspections
            if (inspector_id is None or r["inspector_id"] == inspector_id)
            and (zip_code is None or re.search(rf"CA {zip_code}$", r["site_address"]))
            and (facility_query is None or facility_query.lower() in r["facility_name"].lower())
        ]
        ids = {r["id"] for r in rows}
        return _summarize([r["score"] for r in rows], sum(v["inspection_id"] in ids for v in self.violations))


class FaultyRepository:
    """Delegates to `inner`, but every call first asks `injector` whether to
    fail (Part 3). The injector decides deterministically from its seed."""

    def __init__(self, inner: InspectionRepository, injector: Any):
        self.inner = inner
        self.injector = injector

    def search(self, *args, **kwargs):
        self.injector.maybe_fail()
        return self.inner.search(*args, **kwargs)

    def get_by_code(self, *args, **kwargs):
        self.injector.maybe_fail()
        return self.inner.get_by_code(*args, **kwargs)

    def stats(self, *args, **kwargs):
        self.injector.maybe_fail()
        return self.inner.stats(*args, **kwargs)
