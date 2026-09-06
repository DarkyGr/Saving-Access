-- =============================================================
-- Password Manager Website — Database Schema
-- PostgreSQL 15
-- =============================================================

-- users
CREATE TABLE users (
    user_id              SERIAL PRIMARY KEY,
    username             VARCHAR(64)  NOT NULL UNIQUE,
    email                VARCHAR(254) NOT NULL UNIQUE,
    password_hash        VARCHAR(128) NOT NULL,
    role                 VARCHAR(16)  NOT NULL CHECK (role IN ('User','Admin')),
    email_verified       BOOLEAN      NOT NULL DEFAULT FALSE,
    deactivation_deadline DATE,
    -- Audit columns
    creation_date        DATE         NOT NULL,
    creation_time        TIME         NOT NULL,
    creation_user_id     INTEGER      REFERENCES users(user_id),
    modification_date    DATE,
    modification_time    TIME,
    modification_user_id INTEGER      REFERENCES users(user_id)
);

-- profiles
CREATE TABLE profiles (
    profile_id            SERIAL      PRIMARY KEY,
    profile_name          VARCHAR(64) NOT NULL UNIQUE,
    permitted_screens     JSONB       NOT NULL DEFAULT '[]',
    -- Audit columns
    creation_date         DATE        NOT NULL,
    creation_time         TIME        NOT NULL,
    creation_user_id      INTEGER     REFERENCES users(user_id),
    modification_date     DATE,
    modification_time     TIME,
    modification_user_id  INTEGER     REFERENCES users(user_id)
);

-- user_profiles
CREATE TABLE user_profiles (
    user_profile_id      SERIAL  PRIMARY KEY,
    user_id              INTEGER NOT NULL REFERENCES users(user_id),
    profile_id           INTEGER NOT NULL REFERENCES profiles(profile_id),
    -- Audit columns
    creation_date        DATE    NOT NULL,
    creation_time        TIME    NOT NULL,
    creation_user_id     INTEGER REFERENCES users(user_id),
    modification_date    DATE,
    modification_time    TIME,
    modification_user_id INTEGER REFERENCES users(user_id)
);

-- credentials
CREATE TABLE credentials (
    credential_id        SERIAL       PRIMARY KEY,
    user_id              INTEGER      NOT NULL REFERENCES users(user_id),
    website_name         VARCHAR(256) NOT NULL,
    email_or_username    VARCHAR(254) NOT NULL,
    is_username_login    BOOLEAN      NOT NULL DEFAULT FALSE,
    encrypted_password   BYTEA        NOT NULL,
    -- Audit columns
    creation_date        DATE         NOT NULL,
    creation_time        TIME         NOT NULL,
    creation_user_id     INTEGER      REFERENCES users(user_id),
    modification_date    DATE,
    modification_time    TIME,
    modification_user_id INTEGER      REFERENCES users(user_id)
);

-- audit_log (no audit columns on this table by design)
CREATE TABLE audit_log (
    log_id             SERIAL  PRIMARY KEY,
    user_id            INTEGER NOT NULL REFERENCES users(user_id),
    operation          VARCHAR(16) NOT NULL CHECK (operation IN ('SELECT','INSERT','UPDATE','DELETE')),
    affected_record_id INTEGER,
    operation_date     DATE    NOT NULL,
    operation_time     TIME    NOT NULL
);

-- =============================================================
-- Indexes
-- =============================================================
CREATE INDEX idx_credentials_user_id        ON credentials(user_id);
CREATE INDEX idx_credentials_website_name   ON credentials(website_name);
CREATE INDEX idx_credentials_email_username ON credentials(email_or_username);
CREATE INDEX idx_audit_log_user_id          ON audit_log(user_id);

-- =============================================================
-- Application database role (run as superuser during setup)
-- =============================================================
CREATE ROLE app_user LOGIN PASSWORD '...';
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
-- No SUPERUSER, no schema ownership
