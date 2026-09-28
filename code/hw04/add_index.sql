-- HW4 Part 3.8: the one added index. Both N+1 endpoints look violations up
-- by inspection_id (naive: `= ?` once per record; fixed: `IN (...)` once).
USE s7117_rel;
CREATE INDEX ix_violations_inspection_id ON inspection_violations (inspection_id);
