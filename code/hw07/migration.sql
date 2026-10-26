-- HW7 migration on s7117_rel: JWT roles on the existing users table.
-- Applied by code/hw07/migrate.py, which runs these blocks in order and skips
-- the ALTERs that were already applied (MySQL has no ADD COLUMN IF NOT EXISTS).
--
-- users after this migration:
--   id (PK), username (UNIQUE), password_hash (PBKDF2-SHA256, never plain
--   text), role (reader | writer | moderator), plus the HW4 name/email columns.
-- The HW4 `sessions` table is no longer read by the app (JWT is stateless);
-- it is left in place as history and not dropped.

USE s7117_rel;

-- @block add_user_columns
-- username starts NULLable so the existing HW4 rows can be backfilled.
ALTER TABLE users
    ADD COLUMN username VARCHAR(64) NULL AFTER id,
    ADD COLUMN role     VARCHAR(16) NOT NULL DEFAULT 'reader' AFTER password_hash;

-- @block backfill_usernames
-- username = the email's local part; a later duplicate gets "_<id>" appended.
UPDATE users u
JOIN (
    SELECT SUBSTRING_INDEX(email, '@', 1) AS local_part, MIN(id) AS first_id
    FROM users GROUP BY local_part
) f ON f.local_part = SUBSTRING_INDEX(u.email, '@', 1)
SET u.username = IF(u.id = f.first_id, f.local_part, CONCAT(f.local_part, '_', u.id))
WHERE u.username IS NULL;

-- @block constrain_users
ALTER TABLE users
    MODIFY username VARCHAR(64) NOT NULL,
    ADD UNIQUE KEY uq_users_username (username),
    ADD CONSTRAINT ck_users_role CHECK (role IN ('reader', 'writer', 'moderator'));
