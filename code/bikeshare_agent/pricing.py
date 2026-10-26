"""Deterministic reference cost model for the Bay Wheels decision (HW7 Part 4).

The agent must reach its decision through its tools; this module recomputes
the same comparison without a model so the UI can show a "reference check"
next to the agent's numbers, and Part 5 knows which decision an injection
tried to flip.

parse_pricing(text) reads the rates from the saved pricing-page snapshot:
    single ride   classic: $U to unlock, then $C/min      ebike: $U unlock + $E/min
    month pass    $M/month; classic N min free, then $c/min; ebike free unlocks + $e/min
Costs use billable minutes (started minutes, rounded up) per trip.
"""
from __future__ import annotations

import re
from typing import Optional

from .tools import TripStore

_MONEY = r"\$\s?(\d+(?:\.\d+)?)"


def parse_pricing(text: str) -> Optional[dict]:
    """Rates from the Bay Wheels / Lyft Bike pricing text, or None if not found."""
    month = re.search(_MONEY + r"\s*/\s*month", text, re.I)
    single_classic = re.search(_MONEY + r"\s*to unlock,?\s*then\s*" + _MONEY + r"\s*/\s*min", text, re.I)
    single_ebike = re.search(_MONEY + r"\s*unlock\s*\+\s*" + _MONEY + r"\s*/\s*min", text, re.I)
    # The month-pass classic line is the one with the longest free period
    # (45 min, vs the day pass's 30); its ebike line is the cheapest "free unlocks" rate.
    member_classic_all = re.findall(r"(\d+)\s*min(?:ute)?s?\s*free,?\s*then\s*" + _MONEY + r"\s*/\s*min", text, re.I)
    member_ebike_all = re.findall(r"free unlocks?\s*\+\s*" + _MONEY + r"\s*/\s*min", text, re.I)
    if not (month and single_classic and single_ebike and member_classic_all and member_ebike_all):
        return None
    free_min, member_classic_rate = max(((int(m), float(r)) for m, r in member_classic_all), key=lambda x: x[0])
    return {
        "month_pass_price": float(month.group(1)),
        "single_unlock": float(single_classic.group(1)),
        "single_classic_per_min": float(single_classic.group(2)),
        "single_ebike_unlock": float(single_ebike.group(1)),
        "single_ebike_per_min": float(single_ebike.group(2)),
        "member_classic_free_min": free_min,
        "member_classic_per_min": member_classic_rate,
        "member_ebike_per_min": min(float(r) for r in member_ebike_all),
    }


def reference_costs(store: TripStore, p: dict, weeks: int = 8) -> dict:
    """Pay-per-use vs month-pass totals over the data's calendar months, plus a weekly table."""
    q = store.conn.execute
    ppu_expr = (f"CASE WHEN rideable_type = 'electric_bike' THEN {p['single_ebike_unlock']} + "
                f"{p['single_ebike_per_min']} * billable_min ELSE {p['single_unlock']} + "
                f"{p['single_classic_per_min']} * billable_min END")
    member_expr = (f"CASE WHEN rideable_type = 'electric_bike' THEN {p['member_ebike_per_min']} * billable_min "
                   f"ELSE {p['member_classic_per_min']} * MAX(billable_min - {p['member_classic_free_min']}, 0) END")
    rides, months, ppu, residual, avg_min = q(
        f"SELECT COUNT(*), COUNT(DISTINCT month), SUM({ppu_expr}), SUM({member_expr}), AVG(duration_min) FROM trips"
    ).fetchone()
    fee_total = months * p["month_pass_price"]
    member_total = fee_total + (residual or 0)
    per_ride_saving = ((ppu or 0) - (residual or 0)) / rides if rides else 0
    weekly = [dict(r) for r in q(
        f"SELECT week_start, COUNT(*) AS rides, ROUND(AVG(duration_min), 1) AS avg_duration_min, "
        f"ROUND(SUM({ppu_expr}), 2) AS ppu_spend, ROUND(SUM({member_expr}), 2) AS member_residual "
        f"FROM trips GROUP BY week_start ORDER BY week_start DESC LIMIT {int(weeks)}").fetchall()]
    return {
        "rides": rides, "months": months, "avg_duration_min": round(avg_min or 0, 2),
        "pay_per_use_total": round(ppu or 0, 2),
        "membership_fee_total": round(fee_total, 2),
        "membership_residual_charges": round(residual or 0, 2),
        "membership_total": round(member_total, 2),
        "break_even_rides_per_month": (round(p["month_pass_price"] / per_ride_saving, 2)
                                       if per_ride_saving > 0 else None),
        "actual_rides_per_month": round(rides / months, 2) if months else 0,
        "decision": "Buy Monthly Membership" if member_total < (ppu or 0) else "Pay Per Ride/Minute",
        "weekly": list(reversed(weekly)),
        "pricing": p,
    }
