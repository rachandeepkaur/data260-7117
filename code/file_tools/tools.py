"""The six file tools (HW7 Part 6), confined to one sandbox directory.

    read_file(root, path, max_lines=None)
    write_file(root, path, content, overwrite=True)
    edit_file(root, path, old_text, new_text)             -> includes a short unified diff
    glob_files(root, pattern="**/*")
    search_in_files(root, pattern, file_pattern="**/*", regex=False, max_matches=50)
    bash(root, command, auto_approve=False, timeout_s=10)  -> gated by safety.confirm_bash

Every tool returns the HW5 envelope {"ok", "data", "error"}; paths are
resolved against `root` and anything that escapes it (../, absolute paths,
symlinks out) is rejected. make_file_toolset(root) exposes them to the
hand-written agent loop; the model can never pass auto_approve.
"""
from __future__ import annotations

import difflib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from .safety import confirm_bash

MAX_READ_CHARS = 20_000
MAX_DIFF_LINES = 20
MAX_GLOB_RESULTS = 200


def _ok(data: Any) -> dict:
    return {"ok": True, "data": data, "error": None}


def _fail(error: str) -> dict:
    return {"ok": False, "data": None, "error": error}


def _resolve(root: Path, path: str) -> Path:
    """Resolve `path` inside the sandbox; raise ValueError if it escapes."""
    base = Path(root).resolve()
    target = (base / path).resolve()
    if target != base and base not in target.parents:
        raise ValueError(f"path '{path}' is outside the sandbox")
    return target


def read_file(root: Path, path: str, max_lines: Optional[int] = None) -> dict:
    """Return a text file's content, optionally only its first `max_lines` lines."""
    try:
        target = _resolve(root, path)
        if not target.is_file():
            return _fail(f"file not found: {path}")
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        shown = lines if max_lines is None else lines[:max_lines]
        content = "\n".join(shown)[:MAX_READ_CHARS]
        return _ok({"path": path, "content": content, "total_lines": len(lines), "lines_returned": len(shown),
                    "truncated": len(shown) < len(lines)})
    except (ValueError, OSError) as exc:
        return _fail(str(exc))


def write_file(root: Path, path: str, content: str, overwrite: bool = True) -> dict:
    """Create or replace a text file (parent folders are created)."""
    try:
        target = _resolve(root, path)
        if target.exists() and not overwrite:
            return _fail(f"{path} exists and overwrite=False")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return _ok({"path": path, "bytes": len(content.encode()), "lines": content.count("\n") + 1})
    except (ValueError, OSError) as exc:
        return _fail(str(exc))


def edit_file(root: Path, path: str, old_text: str, new_text: str) -> dict:
    """Replace the single occurrence of `old_text`; returns a short unified diff."""
    try:
        target = _resolve(root, path)
        if not target.is_file():
            return _fail(f"file not found: {path}")
        before = target.read_text(encoding="utf-8")
        count = before.count(old_text) if old_text else 0
        if count != 1:
            return _fail(f"old_text must occur exactly once in {path} (found {count})")
        after = before.replace(old_text, new_text, 1)
        target.write_text(after, encoding="utf-8")
        diff = list(difflib.unified_diff(before.splitlines(), after.splitlines(), f"a/{path}", f"b/{path}",
                                         n=1, lineterm=""))
        short = diff[:MAX_DIFF_LINES] + ([f"... ({len(diff) - MAX_DIFF_LINES} more diff lines)"]
                                         if len(diff) > MAX_DIFF_LINES else [])
        return _ok({"path": path, "diff": "\n".join(short)})
    except (ValueError, OSError) as exc:
        return _fail(str(exc))


def glob_files(root: Path, pattern: str = "**/*") -> dict:
    """Files under the sandbox matching a glob pattern (sorted, relative paths)."""
    try:
        base = Path(root).resolve()
        if pattern.startswith("/") or ".." in Path(pattern).parts:
            return _fail("pattern must be relative to the sandbox")
        files = sorted(p.relative_to(base).as_posix() for p in base.glob(pattern) if p.is_file())
        return _ok({"pattern": pattern, "count": len(files), "files": files[:MAX_GLOB_RESULTS],
                    "truncated": len(files) > MAX_GLOB_RESULTS})
    except (ValueError, OSError) as exc:
        return _fail(str(exc))


def search_in_files(root: Path, pattern: str, file_pattern: str = "**/*", regex: bool = False,
                    max_matches: int = 50) -> dict:
    """Lines containing `pattern` (literal, or a regex) in files matching `file_pattern`."""
    listing = glob_files(root, file_pattern if any(c in file_pattern for c in "*?[") or "/" in file_pattern
                         else f"**/{file_pattern}")
    if not listing["ok"]:
        return listing
    try:
        matcher = re.compile(pattern if regex else re.escape(pattern))
    except re.error as exc:
        return _fail(f"invalid regex: {exc}")
    base = Path(root).resolve()
    matches = []
    for rel in listing["data"]["files"]:
        try:
            lines = (base / rel).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, 1):
            if matcher.search(line):
                matches.append({"file": rel, "line": number, "text": line.strip()[:200]})
                if len(matches) >= max_matches:
                    break
        if len(matches) >= max_matches:
            break
    files = sorted({m["file"] for m in matches})
    return _ok({"pattern": pattern, "file_pattern": file_pattern, "match_count": len(matches),
                "files": files, "matches": matches})


def bash(root: Path, command: str, auto_approve: bool = False, timeout_s: float = 10.0) -> dict:
    """Run a shell command in the sandbox only if the safety gate allows it."""
    gate = confirm_bash(command, auto_approve=auto_approve)
    if not gate.allowed:
        return {**_fail(f"blocked by safety gate: {gate.reason}"), "gate": gate.to_dict()}
    try:
        proc = subprocess.run(command, shell=True, cwd=Path(root).resolve(), capture_output=True, text=True,
                              timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return {**_fail(f"timed out after {timeout_s:g}s"), "gate": gate.to_dict()}
    return {**_ok({"command": command, "exit_code": proc.returncode, "stdout": proc.stdout[-4000:],
                   "stderr": proc.stderr[-2000:]}), "gate": gate.to_dict()}


# --- agent toolset ------------------------------------------------------------------
class ReadFileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, description="File path relative to the sandbox")
    max_lines: Optional[int] = Field(default=None, ge=1, le=5000, description="Only return the first N lines")


class WriteFileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1)
    content: str
    overwrite: bool = True


class EditFileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1)
    old_text: str = Field(min_length=1, description="Exact text to replace (must occur once)")
    new_text: str


class GlobIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pattern: str = Field(default="**/*", description="Glob relative to the sandbox, e.g. **/*.py")


class SearchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pattern: str = Field(min_length=1, description="Text to search for")
    file_pattern: str = Field(default="**/*", description="Only search files matching this glob, e.g. *.py")
    regex: bool = False


class BashIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str = Field(min_length=1, description="Shell command; destructive commands are blocked")


def make_file_toolset(root: Path):
    """The six file tools bound to one sandbox, as an agent_loop Toolset."""
    from agent_loop.toolsets import ToolDef, Toolset

    root = Path(root)

    def wrap(fn):
        return lambda args: json.dumps(fn(args), default=str)

    return Toolset("files", [
        ToolDef("glob_files", "List files in the sandbox matching a glob pattern.", GlobIn,
                wrap(lambda a: glob_files(root, a.pattern))),
        ToolDef("search_in_files", "Find lines containing a pattern; file_pattern limits which files are searched.",
                SearchIn, wrap(lambda a: search_in_files(root, a.pattern, a.file_pattern, a.regex))),
        ToolDef("read_file", "Read a text file (optionally only the first max_lines lines).", ReadFileIn,
                wrap(lambda a: read_file(root, a.path, a.max_lines))),
        ToolDef("write_file", "Create or overwrite a text file.", WriteFileIn,
                wrap(lambda a: write_file(root, a.path, a.content, a.overwrite))),
        ToolDef("edit_file", "Replace one exact occurrence of old_text with new_text; returns a short diff.",
                EditFileIn, wrap(lambda a: edit_file(root, a.path, a.old_text, a.new_text))),
        ToolDef("bash", "Run a read-only shell command in the sandbox (safety-gated).", BashIn,
                wrap(lambda a: bash(root, a.command))),
    ])
