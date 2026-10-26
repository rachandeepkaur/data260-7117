"""MRKL tools for the bike-share membership agent (HW7 Part 4), as pure functions
with JSON schemas, plus the two Part 5 defenses as switches.

    csv_sql(sql)                         read-only SELECT over the uploaded trips
    policy_retriever(url, query, k=4)    quotable snippets from the pricing page
    calculator(expression, units=None)   safe arithmetic (AST walk, no eval)

Every tool returns the common shape
    {"success": bool, "data"?: any, "error"?: str, "source"?: str, "ts"?: str}

State the functions need (the trips table, the fetched page snapshots) lives
in explicit objects - TripStore and SnapshotRegistry - passed in by the agent,
so the functions themselves stay pure apart from that injected state.

Part 5 switches:
    TripStore(enforce_select=True)    tool-boundary defense: exactly ONE read-only
                                      SELECT/WITH statement, on a connection with
                                      PRAGMA query_only=ON. False = the
                                      undefended version (any SQL, writes allowed).
    label_untrusted (agent.py)        prompt defense: retrieved text is wrapped and
                                      labelled as untrusted data.
"""
from __future__ import annotations

import ast
import csv
import hashlib
import html
import io
import math
import operator
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from pydantic import BaseModel, ConfigDict, Field

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = REPO_ROOT / "reports" / "hw07" / "fixtures"
MAX_SQL_ROWS = 200
MAX_PASSAGE_CHARS = 320
CALC_WHITELIST = re.compile(r"^[0-9+\-*/().\s]+$")
CSV_SOURCE = "uploaded.csv"
TRIP_COLUMNS = ["ride_id", "rideable_type", "started_at", "ended_at", "start_station_name", "start_station_id",
                "end_station_name", "end_station_id", "start_lat", "start_lng", "end_lat", "end_lng", "member_casual"]


def now_iso() -> str:
    """UTC timestamp used in every tool envelope."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def envelope(success: bool, data: Any = None, error: Optional[str] = None, source: Optional[str] = None) -> dict:
    """The common tool result shape."""
    out: dict[str, Any] = {"success": success, "ts": now_iso()}
    if data is not None:
        out["data"] = data
    if error is not None:
        out["error"] = error
    if source is not None:
        out["source"] = source
    return out


# --- JSON schemas (inputs and outputs) -------------------------------------------------
class CsvSqlIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sql: str = Field(min_length=1, max_length=4000, description="One read-only SQLite SELECT over table `trips`")


class CsvSqlOut(BaseModel):
    rows: list[dict]
    row_count: int
    source: str = CSV_SOURCE


class PolicyRetrieverIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=8, description="Official pricing page URL")
    query: str = Field(min_length=2, max_length=200, description="What to look for, e.g. 'month pass price'")
    k: int = Field(default=4, ge=1, le=8, description="Number of snippets to return")


class Passage(BaseModel):
    text: str
    source: str
    score: float


class PolicyRetrieverOut(BaseModel):
    passages: list[Passage]


class CalculatorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expression: str = Field(min_length=1, max_length=300, pattern=CALC_WHITELIST.pattern,
                            description="Arithmetic using digits + - * / ( ) . only")
    units: Optional[str] = Field(default=None, max_length=20, description="Optional label, e.g. USD")


class CalculatorOut(BaseModel):
    value: float
    units: Optional[str] = None


class ToolEnvelope(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    source: Optional[str] = None
    ts: Optional[str] = None


TOOL_SCHEMAS = {
    "csv_sql": {"input": CsvSqlIn.model_json_schema(), "output": CsvSqlOut.model_json_schema()},
    "policy_retriever": {"input": PolicyRetrieverIn.model_json_schema(),
                         "output": PolicyRetrieverOut.model_json_schema()},
    "calculator": {"input": CalculatorIn.model_json_schema(), "output": CalculatorOut.model_json_schema()},
    "common_envelope": ToolEnvelope.model_json_schema(),
}


# --- csv_sql ------------------------------------------------------------------------------
class TripStore:
    """The uploaded CSV loaded into an in-memory SQLite table `trips`.

    Derived columns (documented to the agent): duration_min (REAL),
    billable_min (INTEGER, minutes rounded up), month ('YYYY-MM'),
    week_start (Monday, 'YYYY-MM-DD'). Rows with a missing/unparseable
    timestamp or a non-positive duration are dropped and counted."""

    def __init__(self, csv_text: str, *, enforce_select: bool = True):
        self.enforce_select = enforce_select
        self.audit: list[dict] = []  # every statement csv_sql was asked to run
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.load_report = self._load(csv_text)
        self.conn.execute("PRAGMA query_only = ON" if enforce_select else "PRAGMA query_only = OFF")

    def _load(self, csv_text: str) -> dict:
        reader = csv.DictReader(io.StringIO(csv_text))
        missing_cols = [c for c in ("started_at", "ended_at", "rideable_type") if c not in (reader.fieldnames or [])]
        if missing_cols:
            raise ValueError(f"CSV is missing required column(s): {missing_cols}")
        cols = [c for c in TRIP_COLUMNS if c in reader.fieldnames]
        self.conn.execute(f"CREATE TABLE trips ({', '.join(f'{c} TEXT' for c in cols)}, duration_min REAL, "
                          "billable_min INTEGER, month TEXT, week_start TEXT)")
        kept, dropped, blank = [], {"bad_timestamp": 0, "non_positive_duration": 0}, {c: 0 for c in cols}
        for row in reader:
            for c in cols:
                if not (row.get(c) or "").strip():
                    blank[c] += 1
            try:
                start = datetime.fromisoformat(row["started_at"].strip())
                end = datetime.fromisoformat(row["ended_at"].strip())
            except (ValueError, AttributeError):
                dropped["bad_timestamp"] += 1
                continue
            seconds = (end - start).total_seconds()
            if seconds <= 0:
                dropped["non_positive_duration"] += 1
                continue
            week = (start.date() - timedelta(days=start.weekday())).isoformat()
            kept.append([row.get(c) for c in cols] + [round(seconds / 60, 2), math.ceil(seconds / 60),
                                                       start.strftime("%Y-%m"), week])
        self.conn.executemany(f"INSERT INTO trips VALUES ({', '.join('?' * (len(cols) + 4))})", kept)
        return {"rows_loaded": len(kept), "rows_dropped": dropped, "columns": cols,
                "blank_values": {c: n for c, n in blank.items() if n}}

    def row_count(self) -> int:
        """Current number of rows in trips (Part 5 checks it did not change)."""
        try:
            return int(self.conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0])
        except sqlite3.Error:
            return -1  # table dropped


_COMMENT_RE = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)
_STRING_RE = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"")
# REPLACE is not listed: REPLACE() is a normal string function, and REPLACE INTO
# is already stopped by the SELECT/WITH prefix rule and PRAGMA query_only.
_FORBIDDEN_RE = re.compile(r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma|vacuum|"
                           r"reindex|truncate|grant|load_extension)\b", re.I)


def check_read_only_select(sql: str) -> Optional[str]:
    """None if `sql` is exactly one read-only SELECT (or WITH ... SELECT); else why not."""
    code = _STRING_RE.sub("''", _COMMENT_RE.sub(" ", sql)).strip()
    if code.endswith(";"):
        code = code[:-1].rstrip()
    if ";" in code:
        return "only a single SQL statement is allowed"
    if not re.match(r"^(select|with)\b", code, re.I):
        return "only SELECT queries are allowed"
    bad = _FORBIDDEN_RE.search(code)
    if bad:
        return f"keyword '{bad.group(1).upper()}' is not allowed in a read-only query"
    return None


def csv_sql(sql: str, *, store: TripStore) -> dict:
    """Run a query over the uploaded trips. With store.enforce_select (default)
    only one read-only SELECT runs; otherwise every statement is executed."""
    entry = {"sql": sql, "ts": now_iso(), "enforced": store.enforce_select}
    store.audit.append(entry)
    try:
        if store.enforce_select:
            problem = check_read_only_select(sql)
            if problem:
                entry.update(outcome="rejected", reason=problem)
                return envelope(False, error=f"csv_sql rejected the query: {problem}", source=CSV_SOURCE)
            cursor = store.conn.execute(sql)
        else:  # undefended (Part 5 "before"): run every statement, return the last result
            cursor = None
            for statement in [s for s in sql.split(";") if s.strip()]:
                cursor = store.conn.execute(statement)
            store.conn.commit()
        rows = [dict(r) for r in cursor.fetchmany(MAX_SQL_ROWS + 1)] if cursor and cursor.description else []
        truncated = len(rows) > MAX_SQL_ROWS
        rows = rows[:MAX_SQL_ROWS]
        entry.update(outcome="executed", rows=len(rows))
        data = {"rows": rows, "row_count": len(rows), "source": CSV_SOURCE}
        if truncated:
            data["truncated_at"] = MAX_SQL_ROWS
        return envelope(True, data=data, source=CSV_SOURCE)
    except sqlite3.Error as exc:
        entry.update(outcome="error", reason=str(exc))
        return envelope(False, error=f"SQL error: {exc}", source=CSV_SOURCE)


# --- policy_retriever ----------------------------------------------------------------------
class SnapshotRegistry:
    """Fetches each URL once per run and keeps the exact text used, its
    SHA-256 and the access time, so the evidence can be saved (Part 4.IV)."""

    def __init__(self, fetch: Optional[Callable[[str], str]] = None):
        self._fetch = fetch or fetch_url
        self.snapshots: dict[str, dict] = {}

    def get(self, url: str) -> dict:
        """The snapshot for `url` (fetched on first use)."""
        if url not in self.snapshots:
            raw = self._fetch(url)
            text = extract_text(raw)
            self.snapshots[url] = {
                "url": url, "accessed_at": now_iso(), "text": text,
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "raw_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(), "raw": raw,
                "passages": split_passages(text),
            }
        return self.snapshots[url]


def fetch_url(url: str) -> str:
    """http(s) pages via requests; file:// only inside reports/hw07/fixtures (local attack fixtures)."""
    if url.startswith("file://"):
        path = Path(url[len("file://"):]).resolve()
        if FIXTURES_DIR.resolve() not in path.parents:
            raise ValueError("file:// URLs are limited to reports/hw07/fixtures")
        return path.read_text(encoding="utf-8")
    if not url.startswith(("https://", "http://")):
        raise ValueError("only http(s) URLs are supported")
    import requests

    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (data260-hw7 s7117 pricing agent)"}, timeout=20)
    resp.raise_for_status()
    return resp.text


_GRID_CELL_RE = re.compile(r'<div[^>]*\bidx="(\d+)"[^>]*>')
_PLAN_HEADER_RE = re.compile(r"\n([^\n$]+)\n(\$[\d.]+(?:/\w+)?)\n(?:Get [^\n]+|Join)\nClassic bike prices")


def _cell_text(fragment: str) -> str:
    fragment = re.sub(r"(?is)<(script|style|svg)[^>]*>.*?</\1>", " ", fragment)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _plan_summaries(raw_html: str, text: str) -> list[str]:
    """The page's comparison grid as one line per plan.

    The pricing page lays its comparison table out as <div idx="0..n"> cells
    (idx 0 = row label, idx k = plan column k), which flattens into an
    ambiguous list of rates. This rebuilds "Plan (price): row: value; ..." so
    each rate stays attached to its plan. Column names come from the page's
    own per-plan headings ("Month pass / $29/month / Get a month pass")."""
    starts = list(_GRID_CELL_RE.finditer(raw_html))
    rows: dict[str, dict[int, str]] = {}
    label = None
    for i, m in enumerate(starts):
        boundary = starts[i + 1].start() if i + 1 < len(starts) else m.end() + 2000
        end = raw_html.find("</p>", m.end())  # a cell's text is its first <p>; icon-only cells have none
        idx = int(m.group(1))
        value = _cell_text(raw_html[m.end():end]) if 0 <= end < boundary else ""
        if idx == 0:
            label = value
            rows.setdefault(label, {})
        elif label and value:
            rows[label].setdefault(idx, value)
    rows = {k: v for k, v in rows.items() if v}
    if not rows:
        return []
    headers = _PLAN_HEADER_RE.findall("\n" + text)
    n_cols = max(max(v) for v in rows.values())
    lines = []
    for col in range(1, n_cols + 1):
        name = f"{headers[col - 1][0]} ({headers[col - 1][1]})" if col <= len(headers) else f"Column {col}"
        cells = "; ".join(f"{row}: {vals[col]}" for row, vals in rows.items() if col in vals)
        lines.append(f"Plan comparison - {name}: {cells}")
    return lines


def extract_text(raw_html: str) -> str:
    """Visible text of a page, one block per line (scripts/styles removed),
    followed by the comparison grid rebuilt as one line per plan."""
    text = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", raw_html)
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h\d|tr|td|th|section|span|a|button)>", "\n", text)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = "\n".join(line for line in (" ".join(raw.split()) for raw in text.splitlines()) if line)
    summaries = _plan_summaries(raw_html, text)
    return text + ("\n" + "\n".join(summaries) if summaries else "")


def split_passages(text: str) -> list[str]:
    """Short, quotable snippets: each line merged with its neighbours up to
    MAX_PASSAGE_CHARS, de-duplicated (pricing pages repeat their tables)."""
    lines = text.splitlines()
    passages, seen = [], set()
    for i in range(len(lines)):
        chunk = lines[i]
        j = i + 1
        while j < len(lines) and len(chunk) + len(lines[j]) + 3 <= MAX_PASSAGE_CHARS and j - i < 4:
            chunk += " | " + lines[j]
            j += 1
        if chunk not in seen and len(chunk) >= 12:
            seen.add(chunk)
            passages.append(chunk)
    return passages


_STOP = {"the", "a", "an", "of", "for", "and", "or", "to", "in", "on", "is", "what", "how", "much", "per", "with"}


def _terms(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9$.]+", text.lower()) if t not in _STOP]


def policy_retriever(url: str, query: str, k: int = 4, *, registry: SnapshotRegistry) -> dict:
    """Top-k snippets of the pricing page for `query` (keyword overlap + a bonus for prices)."""
    try:
        snap = registry.get(url)
    except Exception as exc:  # noqa: BLE001 - network/HTTP/file errors become a tool error
        return envelope(False, error=f"could not fetch {url}: {type(exc).__name__}: {exc}", source=url)
    q = set(_terms(query))
    scored = []
    for passage in snap["passages"]:
        words = _terms(passage)
        overlap = sum(1 for w in set(words) if w in q or any(w.startswith(t) for t in q if len(t) > 3))
        prices = len(re.findall(r"\$\s?\d", passage))
        score = overlap + 0.5 * min(prices, 3) - 0.002 * len(passage)
        if overlap:
            scored.append((round(score, 3), passage))
    scored.sort(key=lambda x: -x[0])
    passages = [{"text": p, "source": url, "score": s} for s, p in scored[:k]]
    return envelope(True, data={"passages": passages, "captured_at": snap["accessed_at"],
                                "page_sha256": snap["sha256"]}, source=url)


# --- calculator ----------------------------------------------------------------------------
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval_node(node.operand))
    raise ValueError(f"unsupported expression element: {type(node).__name__}")


def calculator(expression: str, units: Optional[str] = None) -> dict:
    """Safe arithmetic: whitelist ^[0-9+\\-*/().\\s]+$, then an AST walk allowing only + - * / and unary +/-."""
    if not CALC_WHITELIST.match(expression or ""):
        return envelope(False, error="expression may only contain digits, + - * / ( ) . and spaces")
    try:
        value = _eval_node(ast.parse(expression, mode="eval"))
    except ZeroDivisionError:
        return envelope(False, error="division by zero")
    except (SyntaxError, ValueError) as exc:
        return envelope(False, error=f"invalid expression: {exc}")
    if not math.isfinite(value):
        return envelope(False, error="result is not a finite number")
    data = {"value": round(value, 6)}
    if units:
        data["units"] = units
    return envelope(True, data=data)
