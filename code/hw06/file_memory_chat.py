"""HW6 Part 4: chat client whose memory is AGENT.md + MEMORY.md.

    make file-memory-chat                                   (interactive)
    python code/hw06/file_memory_chat.py --script reports/hw06/file_memory_demo_script.txt

On start-up (and after /dream) the consolidation rules are checked; when
MEMORY.md has more than 40 lines or its last consolidation is over 24 h old
it is consolidated automatically. `--script` replays one line per input
(the evidence run in RUN_LOG.txt); `--no-auto-consolidate` skips the start-up check.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from file_memory import FileMemorySession, needs_consolidation  # noqa: E402
from file_memory.memory_files import MEMORY_MD  # noqa: E402
from model_client import ModelClientError  # noqa: E402  (path added by file_memory.commands)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", type=Path, help="replay inputs from this file instead of stdin")
    ap.add_argument("--memory", type=Path, default=MEMORY_MD)
    ap.add_argument("--no-auto-consolidate", action="store_true")
    args = ap.parse_args()

    user = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.strip()
    print(f"file_memory_chat.py - user: {user} - {datetime.now():%Y-%m-%d %H:%M:%S} - memory: {args.memory}")
    print("type a message, or /help for commands")
    session = FileMemorySession(memory_path=args.memory)
    print(session.consolidation_status())
    due, reasons = needs_consolidation(args.memory.read_text()) if args.memory.exists() else (False, [])
    if due and not args.no_auto_consolidate:
        print(f"[memory] consolidation required ({'; '.join(reasons)}) - running /compact")
        print(session.cmd_compact())

    inputs = args.script.read_text().splitlines() if args.script else None
    while True:
        if inputs is not None:
            if not inputs:
                break
            line = inputs.pop(0)
            print(f"\n{user}> {line}")
        else:
            try:
                line = input(f"\n{user}> ")
            except EOFError:
                break
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line == "/exit":
            break
        try:
            out = session.handle(line)
            print(out if out is not None else session.chat(line))
        except ModelClientError as exc:
            print(f"model call failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
