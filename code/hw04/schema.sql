-- HW4 migration: database s7117_rel (<PREFIX>_rel, PREFIX = "s" + SID4 = s7117).
-- Applied by code/hw04/setup_db.py (or: mysql -u root < code/hw04/schema.sql).

CREATE DATABASE IF NOT EXISTS s7117_rel CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE s7117_rel;

-- Primary domain entity (DOMAIN_ID 5 - local restaurant inspections).
CREATE TABLE IF NOT EXISTS inspections (
    id            INT          NOT NULL AUTO_INCREMENT,
    facility_name VARCHAR(255) NOT NULL,  -- primary field
    site_address  VARCHAR(255) NOT NULL,  -- secondary field
    PRIMARY KEY (id)
) ENGINE = InnoDB;

-- Related test data for the N+1 experiment: each violation belongs to one
-- inspection. There is intentionally NO foreign-key constraint and NO index
-- on inspection_id here: InnoDB silently creates an index for every FK, which
-- would hide the "before" state of the index experiment. The index is added
-- later by code/hw04/add_index.sql (see code/hw04/explain_index.py).
CREATE TABLE IF NOT EXISTS inspection_violations (
    id              INT          NOT NULL AUTO_INCREMENT,
    inspection_id   INT          NOT NULL,
    violation_code  VARCHAR(16)  NOT NULL,
    description     VARCHAR(255) NOT NULL,
    severity        VARCHAR(16)  NOT NULL,
    points_deducted INT          NOT NULL,
    observed_on     DATE         NOT NULL,
    PRIMARY KEY (id)
) ENGINE = InnoDB;

-- Authentication / server-side sessions.
CREATE TABLE IF NOT EXISTS users (
    id            INT          NOT NULL AUTO_INCREMENT,
    name          VARCHAR(120) NOT NULL,
    email         VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_email (email)
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS sessions (
    id         VARCHAR(64) NOT NULL,  -- opaque session token (the cookie value)
    user_id    INT         NOT NULL,
    created_at DATETIME    NOT NULL,
    expires_at DATETIME    NOT NULL,
    PRIMARY KEY (id),
    KEY ix_sessions_user_id (user_id),
    CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE = InnoDB;
