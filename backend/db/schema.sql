-- GENERATED FILE — do not edit by hand.
-- Source: backend/migrations (Alembic). Regenerate with:
--   cd backend && python db/generate_schema_sql.py

BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_baseline

CREATE TABLE users (
    user_id SERIAL NOT NULL, 
    username VARCHAR(64) NOT NULL, 
    email VARCHAR(254) NOT NULL, 
    password_hash VARCHAR(128) NOT NULL, 
    role VARCHAR(16) NOT NULL, 
    email_verified BOOLEAN DEFAULT false NOT NULL, 
    deactivation_deadline DATE, 
    creation_date DATE NOT NULL, 
    creation_time TIME WITHOUT TIME ZONE NOT NULL, 
    creation_user_id INTEGER, 
    modification_date DATE, 
    modification_time TIME WITHOUT TIME ZONE, 
    modification_user_id INTEGER, 
    PRIMARY KEY (user_id), 
    CONSTRAINT ck_users_role CHECK (role IN ('User', 'Admin')), 
    UNIQUE (username), 
    UNIQUE (email), 
    FOREIGN KEY(creation_user_id) REFERENCES users (user_id), 
    FOREIGN KEY(modification_user_id) REFERENCES users (user_id)
);

CREATE TABLE profiles (
    profile_id SERIAL NOT NULL, 
    profile_name VARCHAR(64) NOT NULL, 
    permitted_screens JSONB DEFAULT '[]' NOT NULL, 
    creation_date DATE NOT NULL, 
    creation_time TIME WITHOUT TIME ZONE NOT NULL, 
    creation_user_id INTEGER, 
    modification_date DATE, 
    modification_time TIME WITHOUT TIME ZONE, 
    modification_user_id INTEGER, 
    PRIMARY KEY (profile_id), 
    UNIQUE (profile_name), 
    FOREIGN KEY(creation_user_id) REFERENCES users (user_id), 
    FOREIGN KEY(modification_user_id) REFERENCES users (user_id)
);

CREATE TABLE user_profiles (
    user_profile_id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    profile_id INTEGER NOT NULL, 
    creation_date DATE NOT NULL, 
    creation_time TIME WITHOUT TIME ZONE NOT NULL, 
    creation_user_id INTEGER, 
    modification_date DATE, 
    modification_time TIME WITHOUT TIME ZONE, 
    modification_user_id INTEGER, 
    PRIMARY KEY (user_profile_id), 
    FOREIGN KEY(user_id) REFERENCES users (user_id) ON DELETE CASCADE, 
    FOREIGN KEY(profile_id) REFERENCES profiles (profile_id) ON DELETE CASCADE, 
    FOREIGN KEY(creation_user_id) REFERENCES users (user_id), 
    FOREIGN KEY(modification_user_id) REFERENCES users (user_id)
);

CREATE TABLE credentials (
    credential_id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    website_name VARCHAR(256) NOT NULL, 
    email_or_username VARCHAR(254) NOT NULL, 
    is_username_login BOOLEAN DEFAULT false NOT NULL, 
    encrypted_password BYTEA NOT NULL, 
    creation_date DATE NOT NULL, 
    creation_time TIME WITHOUT TIME ZONE NOT NULL, 
    creation_user_id INTEGER, 
    modification_date DATE, 
    modification_time TIME WITHOUT TIME ZONE, 
    modification_user_id INTEGER, 
    PRIMARY KEY (credential_id), 
    FOREIGN KEY(user_id) REFERENCES users (user_id) ON DELETE CASCADE, 
    FOREIGN KEY(creation_user_id) REFERENCES users (user_id), 
    FOREIGN KEY(modification_user_id) REFERENCES users (user_id)
);

CREATE INDEX idx_credentials_user_id ON credentials (user_id);

CREATE INDEX idx_credentials_website_name ON credentials (website_name);

CREATE INDEX idx_credentials_email_username ON credentials (email_or_username);

CREATE TABLE audit_log (
    log_id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    operation VARCHAR(16) NOT NULL, 
    affected_record_id INTEGER, 
    operation_date DATE NOT NULL, 
    operation_time TIME WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (log_id), 
    CONSTRAINT ck_audit_log_operation CHECK (operation IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE')), 
    FOREIGN KEY(user_id) REFERENCES users (user_id)
);

CREATE INDEX idx_audit_log_user_id ON audit_log (user_id);

INSERT INTO alembic_version (version_num) VALUES ('0001_baseline') RETURNING alembic_version.version_num;

-- Running upgrade 0001_baseline -> 0002_refresh_tokens

CREATE TABLE refresh_tokens (
    refresh_token_id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    family_id VARCHAR(32) NOT NULL, 
    expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    revoked_at TIMESTAMP WITHOUT TIME ZONE, 
    creation_date DATE NOT NULL, 
    creation_time TIME WITHOUT TIME ZONE NOT NULL, 
    creation_user_id INTEGER, 
    modification_date DATE, 
    modification_time TIME WITHOUT TIME ZONE, 
    modification_user_id INTEGER, 
    PRIMARY KEY (refresh_token_id), 
    FOREIGN KEY(user_id) REFERENCES users (user_id) ON DELETE CASCADE, 
    UNIQUE (token_hash), 
    FOREIGN KEY(creation_user_id) REFERENCES users (user_id), 
    FOREIGN KEY(modification_user_id) REFERENCES users (user_id)
);

CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens (user_id);

CREATE INDEX idx_refresh_tokens_family_id ON refresh_tokens (family_id);

UPDATE alembic_version SET version_num='0002_refresh_tokens' WHERE alembic_version.version_num = '0001_baseline';

COMMIT;


-- =============================================================
-- Application database role (Requirement 9.9) — run as superuser
-- after the tables exist. Replace the password before use.
-- =============================================================
CREATE ROLE app_user LOGIN PASSWORD 'change-me';
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
-- No SUPERUSER, no schema ownership.
