"""HW6 Part 3.3/3.4: replay the same 30-message conversation + 5 probes under
each memory setting and log the per-turn cost.

    make memory-experiment-hw06                     (all 4 settings, ~3 h on CPU)
    python code/hw06/run_memory_experiment.py --only "SHORT_TERM_N=4"

For every setting the FastAPI backend is (re)started on PORT_BASE with that
setting's env (SHORT_TERM_N, MEMORY_POLICY), then a fresh user_id + session_id
sends the 30 messages and the 5 probe questions through POST /api/chat - the
same endpoint and code path as Part 2. Output:
    raw/turns_<slug>.jsonl   one row per request (reply, memory used, usage)
    raw/memory_turns.csv     all settings, flat per-turn token/latency table
    raw/probe_scores.json    rubric score per probe per setting
A setting whose jsonl already has all 35 rows is skipped unless --force, so
an interrupted run can be resumed.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import socket
import subprocess
import sys
import time
from datetime import datetime

import requests
import yaml

from hw06_config import (
    BASE_URL,
    CONVERSATION_FILE,
    EXPERIMENT_SETTINGS,
    PORT_BASE,
    PREFIX,
    RAW_DIR,
    WEB_APP_DIR,
)
from probe_scoring import load_probes, score_reply

CSV_FIELDS = ["setting", "turn", "kind", "probe_id", "prompt_tokens", "completion_tokens",
              "tok_system_primer", "tok_long_term_summary", "tok_short_term_window", "tok_episodic_facts",
              "tok_current_message", "tok_counted_total", "aux_prompt_tokens", "aux_completion_tokens", "aux_calls",
              "short_term_count", "episodic_count", "has_session_summary", "has_lifetime_summary",
              "latency_ms", "model_latency_ms", "aux_latency_ms", "client_latency_ms", "probe_score"]


def slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def start_server(env_overrides: dict) -> subprocess.Popen:
    if port_open(PORT_BASE):
        sys.exit(f"Port {PORT_BASE} is already in use - stop the running API first (the runner starts its own).")
    env = {**os.environ, **env_overrides}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
                             "--port", str(PORT_BASE)], cwd=WEB_APP_DIR, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        if port_open(PORT_BASE):
            return proc
        time.sleep(0.5)
    proc.terminate()
    sys.exit("API did not start")


def stop_server(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
    while port_open(PORT_BASE):
        time.sleep(0.5)


def run_setting(label: str, env: dict, messages: list[str], probes: list[dict]) -> list[dict]:
    run_tag = datetime.now().strftime("%m%d%H%M")
    user_id = f"{PREFIX}-exp-{slug(label)}-{run_tag}"
    session_id = f"{user_id}-s1"
    out_path = RAW_DIR / f"turns_{slug(label)}.jsonl"
    rows: list[dict] = []
    proc = start_server(env)
    try:
        turns = [("conversation", None, m) for m in messages] + [("probe", p, p["question"]) for p in probes]
        with out_path.open("w") as fh:
            for i, (kind, probe, text) in enumerate(turns, start=1):
                t0 = time.perf_counter()
                r = requests.post(f"{BASE_URL}/api/chat", timeout=1800,
                                  json={"user_id": user_id, "session_id": session_id, "message": text})
                client_ms = (time.perf_counter() - t0) * 1000
                r.raise_for_status()
                body = r.json()
                row = {"setting": label, "env": env, "turn": i, "kind": kind,
                       "probe_id": probe["id"] if probe else None, "message": text,
                       "client_latency_ms": round(client_ms, 1), **body}
                if probe:
                    row["probe_result"] = score_reply(probe, body["reply"])
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                rows.append(row)
                u = body["usage"]
                extra = f" probe={probe['id']} score={row['probe_result']['score']}" if probe else ""
                print(f"[{datetime.now():%H:%M:%S}] {label} turn {i:2d}/{len(turns)} prompt={u['prompt_tokens']:5d} "
                      f"completion={u['completion_tokens']:4d} window={body['memory_used']['short_term_count']:2d} "
                      f"facts={len(body['memory_used']['episodic_facts'])} latency={u['latency_ms']:.0f}ms{extra}",
                      flush=True)
                if probe:
                    print(f"      Q: {text}\n      A: {body['reply'][:300]}", flush=True)
    finally:
        stop_server(proc)
    return rows


def flatten(row: dict) -> dict:
    u, c, m = row["usage"], row["usage"]["components"], row["memory_used"]
    return {
        "setting": row["setting"], "turn": row["turn"], "kind": row["kind"], "probe_id": row["probe_id"],
        "prompt_tokens": u["prompt_tokens"], "completion_tokens": u["completion_tokens"],
        "tok_system_primer": c["system_primer"], "tok_long_term_summary": c["long_term_summary"],
        "tok_short_term_window": c["short_term_window"], "tok_episodic_facts": c["episodic_facts"],
        "tok_current_message": c["current_message"], "tok_counted_total": c["counted_total"],
        "aux_prompt_tokens": u["aux_prompt_tokens"], "aux_completion_tokens": u["aux_completion_tokens"],
        "aux_calls": u["aux_calls"], "short_term_count": m["short_term_count"],
        "episodic_count": len(m["episodic_facts"]), "has_session_summary": bool(m["session_summary"]),
        "has_lifetime_summary": bool(m["lifetime_summary"]), "latency_ms": u["latency_ms"],
        "model_latency_ms": u["model_latency_ms"], "aux_latency_ms": u["aux_latency_ms"],
        "client_latency_ms": row["client_latency_ms"],
        "probe_score": row["probe_result"]["score"] if row.get("probe_result") else "",
    }


def load_rows(label: str) -> list[dict]:
    path = RAW_DIR / f"turns_{slug(label)}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", help="run only this setting label (repeatable)")
    ap.add_argument("--force", action="store_true", help="re-run settings that are already complete")
    args = ap.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    messages = [m["text"] for m in yaml.safe_load(CONVERSATION_FILE.read_text())["messages"]]
    probes = load_probes()["probes"]
    assert len(messages) == 30 and len(probes) == 5
    expected_rows = len(messages) + len(probes)

    for label, env in EXPERIMENT_SETTINGS:
        if args.only and label not in args.only:
            continue
        if not args.force and len(load_rows(label)) == expected_rows:
            print(f"{label}: already complete ({expected_rows} rows) - skipped (use --force to re-run)")
            continue
        print(f"\n=== {label}  env={env}  started {datetime.now():%Y-%m-%d %H:%M:%S} ===", flush=True)
        run_setting(label, env, messages, probes)

    all_rows = [r for label, _ in EXPERIMENT_SETTINGS for r in load_rows(label)]
    with (RAW_DIR / "memory_turns.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(flatten(r) for r in all_rows)
    scores = [{"setting": r["setting"], "probe_id": r["probe_id"], "question": r["message"], "reply": r["reply"],
               **r["probe_result"]} for r in all_rows if r["kind"] == "probe"]
    (RAW_DIR / "probe_scores.json").write_text(json.dumps(scores, indent=2))
    print(f"\nwrote {len(all_rows)} rows -> {RAW_DIR / 'memory_turns.csv'}, {len(scores)} probe scores -> probe_scores.json")


if __name__ == "__main__":
    main()
