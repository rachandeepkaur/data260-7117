"""Non-determinism study: runs the Planner -> Reviewer -> Publish pipeline on
one fixed input 20 times at temperature=0.7 and 20 times at temperature=0.0
(40 runs total), and reports how much the output (tags) and latency vary.

Fixed input: reports/hw01/cases/nondeterminism_input.json (title + content,
saved once and read unchanged here).

Produces:
  - reports/hw01/RUN_LOG.txt        (via `tee` on this script's stdout)
  - reports/hw01/raw/nondeterminism_runs.json
  - reports/hw01/raw/nondeterminism_runs.csv
  - reports/hw01/METRICS.md         (overwritten with this study's tables)

Run with (from repo root, ollama serve running with qwen3:8b pulled):

    source .venv/bin/activate
    python code/experiments/run_nondeterminism_experiment.py 2>&1 | tee reports/hw01/RUN_LOG.txt
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "code"))

from agents_demo import ModelClient, ModelClientError, finalize, run_planner, run_reviewer  # noqa: E402

REPORT_DIR = REPO_ROOT / "reports" / "hw01"
RAW_DIR = REPORT_DIR / "raw"
INPUT_PATH = REPORT_DIR / "cases" / "nondeterminism_input.json"

TEMPERATURES = [0.7, 0.0]
RUNS_PER_TEMPERATURE = 20

CSV_FIELDS = [
    "temperature", "run", "tags", "summary", "approved",
    "latency_ms", "planner_ms", "reviewer_ms",
    "planner_total_tokens", "reviewer_total_tokens",
    "started_at", "finished_at", "status", "error",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def load_fixed_input() -> Dict[str, str]:
    return json.loads(INPUT_PATH.read_text())


def run_one(client: ModelClient, title: str, content: str) -> Dict[str, Any]:
    t_start = time.time()

    t0 = time.time()
    draft = run_planner(client, title, content)
    planner_ms = int((time.time() - t0) * 1000)
    planner_tokens = client.last_usage["total_tokens"]

    t0 = time.time()
    review = run_reviewer(client, title, content, draft)
    reviewer_ms = int((time.time() - t0) * 1000)
    reviewer_tokens = client.last_usage["total_tokens"]

    publish = finalize(title, review)
    latency_ms = int((time.time() - t_start) * 1000)

    return {
        "tags": publish.tags,
        "summary": publish.summary,
        "approved": review.approved,
        "latency_ms": latency_ms,
        "planner_ms": planner_ms,
        "reviewer_ms": reviewer_ms,
        "planner_total_tokens": planner_tokens,
        "reviewer_total_tokens": reviewer_tokens,
    }


def run_all(title: str, content: str) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []

    for temperature in TEMPERATURES:
        client = ModelClient(temperature=temperature)
        print(f"[{now_iso()}] === Temperature {temperature}: {RUNS_PER_TEMPERATURE} runs ===")

        for run in range(1, RUNS_PER_TEMPERATURE + 1):
            record: Dict[str, Any] = {
                "temperature": temperature,
                "run": run,
                "started_at": now_iso(),
                "error": "",
            }
            try:
                outcome = run_one(client, title, content)
                record.update(outcome)
                record["status"] = "ok"
                print(f"[{now_iso()}] T={temperature} run {run}/{RUNS_PER_TEMPERATURE} "
                      f"({outcome['latency_ms']} ms): tags={outcome['tags']}")
            except ModelClientError as exc:
                record.update({"status": "error", "error": str(exc)})
                print(f"[{now_iso()}] T={temperature} run {run}/{RUNS_PER_TEMPERATURE} FAILED: {exc}",
                      file=sys.stderr)

            record["finished_at"] = now_iso()
            results.append(record)

    return results


def write_raw(results: List[Dict[str, Any]]) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    (RAW_DIR / "nondeterminism_runs.json").write_text(json.dumps(results, indent=2))

    with (RAW_DIR / "nondeterminism_runs.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for record in results:
            row = dict(record)
            if isinstance(row.get("tags"), list):
                row["tags"] = "; ".join(row["tags"])
            writer.writerow(row)


def percentiles(values: List[int]) -> Dict[str, float]:
    if not values:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
    q = statistics.quantiles(values, n=100, method="inclusive")
    return {"p50": q[49], "p95": q[94], "p99": q[98]}


# A run's wall-clock latency includes any time the host machine spent asleep
# mid-call (time.time() counts elapsed wall time, not just CPU/active time).
# A run whose latency is many times the group's median is almost certainly a
# sleep artifact rather than real model latency, so it's excluded from the
# percentile stats (and called out explicitly) instead of silently skewing them.
OUTLIER_MULTIPLE = 5


def split_latency_outliers(runs: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    latencies = [r["latency_ms"] for r in runs]
    if not latencies:
        return [], []
    med = statistics.median(latencies)
    clean = [r for r in runs if r["latency_ms"] <= med * OUTLIER_MULTIPLE]
    outliers = [r for r in runs if r["latency_ms"] > med * OUTLIER_MULTIPLE]
    return clean, outliers


def summarize_temperature(results: List[Dict[str, Any]], temperature: float) -> Dict[str, Any]:
    runs = [r for r in results if r["temperature"] == temperature and r["status"] == "ok"]
    tag_sets = [frozenset(r["tags"]) for r in runs]
    distinct_sets = set(tag_sets)

    tag_run_counts = Counter()
    for tags in tag_sets:
        for tag in tags:
            tag_run_counts[tag] += 1

    n = len(runs)
    always_present = sorted(tag for tag, count in tag_run_counts.items() if count == n) if n else []
    exactly_one = sorted(tag for tag, count in tag_run_counts.items() if count == 1)

    clean_runs, outlier_runs = split_latency_outliers(runs)
    latency = percentiles([r["latency_ms"] for r in clean_runs])

    return {
        "temperature": temperature,
        "runs_ok": n,
        "runs_failed": RUNS_PER_TEMPERATURE - n,
        "distinct_tag_sets": len(distinct_sets),
        "always_present_tags": always_present,
        "exactly_one_run_tags": exactly_one,
        "latency_p50": round(latency["p50"], 1),
        "latency_p95": round(latency["p95"], 1),
        "latency_p99": round(latency["p99"], 1),
        "latency_n": len(clean_runs),
        "latency_outliers": [(r["run"], r["latency_ms"]) for r in outlier_runs],
    }


def write_metrics(results: List[Dict[str, Any]], title: str) -> None:
    lines: List[str] = []
    lines.append("# HW01 Metrics — Planner/Reviewer Non-Determinism Study")
    lines.append("")
    lines.append(
        f'Fixed input (`reports/hw01/cases/nondeterminism_input.json`, title: "{title}"), run through '
        f"the real Planner -> Reviewer -> Publish pipeline (`qwen3:8b` via Ollama) {RUNS_PER_TEMPERATURE} "
        f"times at each of temperature=0.7 and temperature=0.0 ({RUNS_PER_TEMPERATURE * len(TEMPERATURES)} "
        f"runs total). Source data: [raw/nondeterminism_runs.json](raw/nondeterminism_runs.json), "
        f"[raw/nondeterminism_runs.csv](raw/nondeterminism_runs.csv). Full console transcript: "
        f"[RUN_LOG.txt](RUN_LOG.txt)."
    )
    lines.append("")

    for temperature in TEMPERATURES:
        summary = summarize_temperature(results, temperature)
        lines.append(f"## Temperature = {temperature}")
        lines.append("")
        lines.append(f"- Runs completed: {summary['runs_ok']}/{RUNS_PER_TEMPERATURE} "
                      f"({summary['runs_failed']} failed)")
        lines.append(f"- Distinct tag sets produced: **{summary['distinct_tag_sets']}**")
        lines.append(
            "- Tags that appeared in all "
            f"{summary['runs_ok']} runs: "
            + (", ".join(f"`{t}`" for t in summary["always_present_tags"]) or "*(none)*")
        )
        lines.append(
            "- Tags that appeared in exactly one run: "
            + (", ".join(f"`{t}`" for t in summary["exactly_one_run_tags"]) or "*(none)*")
        )
        lines.append("")
        lines.append(f"| Latency (n={summary['latency_n']}) | p50 | p95 | p99 |")
        lines.append("|---|---|---|---|")
        lines.append(f"| ms | {summary['latency_p50']} | {summary['latency_p95']} | {summary['latency_p99']} |")
        if summary["latency_outliers"]:
            excluded = ", ".join(
                f"run {run} ({ms:,} ms)" for run, ms in summary["latency_outliers"]
            )
            lines.append("")
            lines.append(
                f"> Excluded from the latency stats above: {excluded} — latency this many multiples "
                f"({OUTLIER_MULTIPLE}x+) above the group median indicates the host machine slept "
                f"mid-call (wall-clock time includes sleep time), not real model latency. Still "
                f"included in the tag-set analysis above and present in the raw data."
            )
        lines.append("")

    (REPORT_DIR / "METRICS.md").write_text("\n".join(lines))


def main() -> None:
    fixed_input = load_fixed_input()
    title, content = fixed_input["title"], fixed_input["content"]

    print(f"[{now_iso()}] Starting non-determinism study on fixed input "
          f"(title: {title!r})")
    results = run_all(title, content)
    write_raw(results)
    write_metrics(results, title)

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"[{now_iso()}] Done. {ok}/{len(results)} runs succeeded. "
          f"Wrote raw/nondeterminism_runs.{{json,csv}} and METRICS.md under {REPORT_DIR}")


if __name__ == "__main__":
    main()
