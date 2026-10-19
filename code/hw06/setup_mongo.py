"""HW6 Part 1.I: create s7117_doc, its collections ($jsonSchema validators +
indexes) and seed sample inspection documents (random.Random(SEED)).

    make setup-mongo-hw06     (MongoDB must be running: make mongo-up)

Seeding is skipped when the inspections collection already has documents,
so re-running never duplicates data. Prints the validator so the report can
show the database-level rules next to the Pydantic ones.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone

from hw06_config import MONGO_DB, SEED

import settings
from doc_schemas import CATEGORIES, STATUSES
from mongo import VALIDATORS, ensure_collections, get_db

FACILITIES = [
    "FA0206933 - YUMMY KITCHEN", "FA0148210 - GOLDEN DRAGON", "FA0177342 - TAQUERIA EL SOL",
    "FA0190015 - PHO SAIGON", "FA0211876 - BAY BBQ", "FA0123456 - SUNRISE DONUTS",
    "FA0165432 - MAMA MIA PIZZERIA", "FA0187654 - SAKURA SUSHI", "FA0199887 - CURRY HOUSE",
    "FA0201122 - GREEN BOWL CAFE", "FA0213344 - LUCKY NOODLE", "FA0225566 - BURGER BARN",
]
NOTES = [
    "Hand-wash sink blocked by storage boxes; corrected on site.",
    "Walk-in cooler at 45F, above the 41F limit; product discarded.",
    "No violations observed. Food handler cards current.",
    "Improper cold holding of cut melons on the prep line.",
    None,
    "Evidence of rodent droppings in dry storage; follow-up scheduled.",
]


def main() -> None:
    db = get_db()
    names = ensure_collections(db)
    print(f"database {MONGO_DB}: collections ready -> {names}")
    coll = db[settings.DOC_COLLECTION]
    if coll.estimated_document_count() == 0:
        rng = random.Random(SEED)
        base = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
        docs = []
        for i, name in enumerate(FACILITIES):
            now = datetime.now(timezone.utc)
            docs.append({
                "facility_name": name,
                "description": rng.choice(NOTES),
                "status": rng.choice(STATUSES),
                "program_element": rng.choice(CATEGORIES),
                "inspection_date": base + timedelta(days=3 * i, hours=rng.randint(0, 7)),
                "created_at": now, "updated_at": now,
            })
        coll.insert_many(docs)
        print(f"seeded {len(docs)} inspection documents (SEED={SEED})")
    else:
        print(f"{coll.estimated_document_count()} inspection documents already present - seeding skipped")
    for name in names:
        print(f"  {name}: {db[name].estimated_document_count()} documents")
    print("validator for 'inspections':")
    print(json.dumps(VALIDATORS[settings.DOC_COLLECTION], indent=2))


if __name__ == "__main__":
    main()
