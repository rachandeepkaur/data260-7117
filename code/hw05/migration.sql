-- HW5 migration on s7117_rel: adds the related entity (inspectors) and links
-- every inspection to one inspector. Applied by code/hw05/migrate.py, which
-- runs these blocks in order and skips the ALTERs that were already applied
-- (MySQL has no ADD COLUMN IF NOT EXISTS).
--
-- Relationship (book/author style): one inspector performs many inspections.
-- Deleting an inspector that still has inspections is REJECTED (ON DELETE
-- RESTRICT) - no cascade. The API turns that into 409 Conflict.

USE s7117_rel;

-- @block create_inspectors
CREATE TABLE IF NOT EXISTS inspectors (
    id          INT          NOT NULL AUTO_INCREMENT,
    full_name   VARCHAR(120) NOT NULL,                -- primary text field
    district    VARCHAR(120) NOT NULL,                -- secondary text field
    email       VARCHAR(255) NOT NULL,                -- unique field (format validated by the API)
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_inspectors_email (email)
) ENGINE = InnoDB;

-- @block add_inspection_columns
-- Added as NULLable first so the 5,000 existing rows can be backfilled.
ALTER TABLE inspections
    ADD COLUMN inspection_code VARCHAR(16) NULL AFTER id,
    ADD COLUMN score           INT         NOT NULL DEFAULT 100 AFTER site_address,
    ADD COLUMN inspector_id    INT         NULL AFTER score,
    ADD COLUMN created_at      DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN updated_at      DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

-- @block backfill_inspections
-- inspection_code = INS-<6-digit id>; inspector assigned deterministically
-- from SEED (7117); score = 100 minus the points of that inspection's violations.
UPDATE inspections i
LEFT JOIN (
    SELECT inspection_id, SUM(points_deducted) AS pts
    FROM inspection_violations GROUP BY inspection_id
) v ON v.inspection_id = i.id
SET i.inspection_code = CONCAT('INS-', LPAD(i.id, 6, '0')),
    i.inspector_id    = 1 + MOD(i.id * 7117, (SELECT COUNT(*) FROM inspectors)),
    i.score           = GREATEST(0, 100 - COALESCE(v.pts, 0))
WHERE i.inspection_code IS NULL;

-- @block constrain_inspections
ALTER TABLE inspections
    MODIFY inspection_code VARCHAR(16) NOT NULL,
    MODIFY inspector_id    INT         NOT NULL,
    ADD UNIQUE KEY uq_inspections_code (inspection_code),
    ADD CONSTRAINT ck_inspections_score CHECK (score BETWEEN 0 AND 100),
    ADD CONSTRAINT fk_inspections_inspector FOREIGN KEY (inspector_id)
        REFERENCES inspectors (id) ON DELETE RESTRICT ON UPDATE CASCADE;
