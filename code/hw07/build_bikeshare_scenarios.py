"""Build the two Part 4 acceptance datasets from public Bay Wheels trip data.

    make bikeshare-scenarios-hw07    (or: python code/hw07/build_bikeshare_scenarios.py)

Source: the public monthly trip files at https://s3.amazonaws.com/baywheels-data/
(ride_id, rideable_type, started_at, ended_at, stations, lat/lng, member_casual).
Every row in the output is a real public trip row, unchanged; only the
selection is ours. To avoid downloading whole 10-22 MB archives, the script
requests the first RANGE_BYTES of each zip (HTTP Range) and inflates the
start of the CSV inside it.

The public data is anonymized (no rider id), so each scenario treats a
sample of real trips as ONE hypothetical rider's history - an assumption the
agent is told to state:

    membership_wins   13 months x 40 trips: 20 classic (12-40 min) + 20 ebike (10-30 min)
                      per month -> frequent, longer rides, ebike per-minute charges
    ppu_wins          65 months x 8 classic trips of 3-10 min per month -> few, short rides

Sampling is seeded (SEED = 7117 + month), so the same files give the same rows.
Outputs:
    reports/hw07/cases/bikeshare/<scenario>.csv
    reports/hw07/raw/bikeshare/<scenario>_trip_summary.json   (sources, rule, counts, SHA-256)
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import re
import struct
import zlib
from datetime import datetime

import requests

from hw07_config import BIKESHARE_CASES_DIR, BIKESHARE_RAW_DIR, SEED, TRIP_DATA_INDEX

RANGE_BYTES = 1_500_000
QUOTA_KEYS = ("rideable_type", "min_minutes", "max_minutes", "trips")
COLUMNS = ["ride_id", "rideable_type", "started_at", "ended_at", "start_station_name", "start_station_id",
           "end_station_name", "end_station_id", "start_lat", "start_lng", "end_lat", "end_lng", "member_casual"]

SCENARIOS = {
    "membership_wins": {
        "months": 13,
        "description": "Frequent, longer rides: per month 20 classic trips of 12-40 min and 20 ebike trips of "
                       "10-30 min (real public trips).",
        "quota": [("classic_bike", 12, 40, 20), ("electric_bike", 10, 30, 20)],
    },
    "ppu_wins": {
        "months": 65,
        "description": "Few, short rides: per month 8 classic trips of 3-10 min (real public trips).",
        "quota": [("classic_bike", 3, 10, 8)],
    },
}


def list_monthly_files() -> list[tuple[str, str, int]]:
    """(yyyymm, key, size) for every monthly trip archive in the public bucket."""
    xml = requests.get(f"{TRIP_DATA_INDEX}?list-type=2", timeout=30).text
    keys = re.findall(r"<Key>([^<]+)</Key>\s*(?:<[^>]+>[^<]*</[^>]+>\s*)*?<Size>(\d+)</Size>", xml)
    if not keys:
        keys = [(k, "0") for k in re.findall(r"<Key>([^<]+)</Key>", xml)]
    out = []
    for key, size in keys:
        m = re.match(r"^(\d{6})-(?:baywheels|lyftbikes)-tripdata\.(?:csv\.)?zip$", key)
        if m:
            out.append((m.group(1), key, int(size)))
    return sorted(out)


def head_rows(key: str) -> list[dict]:
    """The complete CSV rows contained in the first RANGE_BYTES of a zip archive."""
    blob = requests.get(TRIP_DATA_INDEX + key, headers={"Range": f"bytes=0-{RANGE_BYTES - 1}"}, timeout=60).content
    if blob[:4] != b"PK\x03\x04":
        raise ValueError(f"{key}: not a zip local file header")
    _sig, _ver, _flags, method, _t, _d, _crc, _cs, _us, name_len, extra_len = struct.unpack("<IHHHHHIIIHH", blob[:30])
    name = blob[30:30 + name_len].decode("utf-8", "replace")
    if method != 8 or not name.endswith(".csv"):
        raise ValueError(f"{key}: first entry {name!r} is not a deflated CSV")
    text = zlib.decompressobj(-15).decompress(blob[30 + name_len + extra_len:]).decode("utf-8", "replace")
    text = text[: text.rfind("\n")]  # drop the partial last line
    return list(csv.DictReader(io.StringIO(text)))


def minutes(row: dict) -> float:
    """Trip duration in minutes (-1 if a timestamp is unparseable)."""
    try:
        delta = datetime.fromisoformat(row["ended_at"]) - datetime.fromisoformat(row["started_at"])
        return delta.total_seconds() / 60
    except (KeyError, ValueError):
        return -1.0


def build(name: str, spec: dict, files: list[tuple[str, str, int]]) -> None:
    """Sample one scenario from the most recent `months` archives and write CSV + summary."""
    chosen = files[-spec["months"]:]
    rows_out, sources = [], []
    for yyyymm, key, size in chosen:
        rows = head_rows(key)
        rng = random.Random(SEED + int(yyyymm))
        picked = []
        for bike, lo, hi, n in spec["quota"]:
            pool = [r for r in rows if r.get("rideable_type") == bike and lo <= minutes(r) <= hi and r.get("ended_at")]
            if len(pool) < n:
                raise RuntimeError(f"{key}: only {len(pool)} {bike} trips of {lo}-{hi} min in the first "
                                   f"{RANGE_BYTES} bytes (need {n})")
            picked += rng.sample(pool, n)
        picked.sort(key=lambda r: r["started_at"])
        rows_out += [{c: r.get(c, "") for c in COLUMNS} for r in picked]
        sources.append({"month": yyyymm, "url": TRIP_DATA_INDEX + key, "archive_bytes": size,
                        "rows_scanned": len(rows), "rows_sampled": len(picked)})
        print(f"  {name}: {key} -> scanned {len(rows)} rows, sampled {len(picked)}")

    BIKESHARE_CASES_DIR.mkdir(parents=True, exist_ok=True)
    path = BIKESHARE_CASES_DIR / f"{name}.csv"
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows_out)
    path.write_text(buf.getvalue(), encoding="utf-8")

    durations = [minutes(r) for r in rows_out]
    by_type: dict[str, int] = {}
    for r in rows_out:
        by_type[r["rideable_type"]] = by_type.get(r["rideable_type"], 0) + 1
    summary = {
        "scenario": name, "description": spec["description"], "csv": str(path.relative_to(path.parents[4])),
        "csv_sha256": hashlib.sha256(buf.getvalue().encode()).hexdigest(), "rows": len(rows_out),
        "months": len(chosen), "first_trip": rows_out[0]["started_at"], "last_trip": rows_out[-1]["started_at"],
        "rides_per_month": round(len(rows_out) / len(chosen), 2), "by_rideable_type": by_type,
        "duration_min": {"min": round(min(durations), 2), "max": round(max(durations), 2),
                         "mean": round(sum(durations) / len(durations), 2)},
        "sampling": {"seed_rule": f"random.Random({SEED} + yyyymm)", "range_bytes_per_archive": RANGE_BYTES,
                     "quota_per_month": [dict(zip(QUOTA_KEYS, q, strict=True)) for q in spec["quota"]]},
        "assumption": "Public data has no rider id; the sample is treated as one hypothetical rider's history.",
        "sources": sources,
    }
    BIKESHARE_RAW_DIR.mkdir(parents=True, exist_ok=True)
    (BIKESHARE_RAW_DIR / f"{name}_trip_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"{name}: {len(rows_out)} rows over {len(chosen)} months -> {path} (sha256 {summary['csv_sha256'][:16]}...)")


def main() -> None:
    """Build both scenarios from the newest archives in the bucket."""
    files = list_monthly_files()
    print(f"{len(files)} monthly archives listed; newest {files[-1][1]}")
    for name, spec in SCENARIOS.items():
        build(name, spec, files)


if __name__ == "__main__":
    main()
