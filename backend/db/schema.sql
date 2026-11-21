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

-- Running upgrade 0002_refresh_tokens -> 0003_search_trgm

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_credentials_website_name_trgm ON credentials USING gin (website_name gin_trgm_ops);

CREATE INDEX idx_credentials_email_username_trgm ON credentials USING gin (email_or_username gin_trgm_ops);

UPDATE alembic_version SET version_num='0003_search_trgm' WHERE alembic_version.version_num = '0002_refresh_tokens';

-- Running upgrade 0003_search_trgm -> 0004_email_verification

CREATE TABLE email_verification_tokens (
    email_verification_token_id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    used_at TIMESTAMP WITHOUT TIME ZONE, 
    creation_date DATE NOT NULL, 
    creation_time TIME WITHOUT TIME ZONE NOT NULL, 
    creation_user_id INTEGER, 
    modification_date DATE, 
    modification_time TIME WITHOUT TIME ZONE, 
    modification_user_id INTEGER, 
    PRIMARY KEY (email_verification_token_id), 
    FOREIGN KEY(user_id) REFERENCES users (user_id) ON DELETE CASCADE, 
    UNIQUE (token_hash), 
    FOREIGN KEY(creation_user_id) REFERENCES users (user_id), 
    FOREIGN KEY(modification_user_id) REFERENCES users (user_id)
);

CREATE INDEX idx_email_verification_tokens_user_id ON email_verification_tokens (user_id);

UPDATE alembic_version SET version_num='0004_email_verification' WHERE alembic_version.version_num = '0003_search_trgm';

-- Running upgrade 0004_email_verification -> 0005_verification_reminders

ALTER TABLE users ADD COLUMN preferred_language VARCHAR(8);

ALTER TABLE users ADD COLUMN last_verification_reminder_days SMALLINT;

UPDATE alembic_version SET version_num='0005_verification_reminders' WHERE alembic_version.version_num = '0004_email_verification';

-- Running upgrade 0005_verification_reminders -> 0006_retire_profiles

DROP TABLE user_profiles;

DROP TABLE profiles;

UPDATE alembic_version SET version_num='0006_retire_profiles' WHERE alembic_version.version_num = '0005_verification_reminders';

-- Running upgrade 0006_retire_profiles -> 0007_user_preferences

CREATE TABLE user_preferences (
    user_id INTEGER NOT NULL, 
    list_views JSON NOT NULL, 
    creation_date DATE NOT NULL, 
    creation_time TIME WITHOUT TIME ZONE NOT NULL, 
    creation_user_id INTEGER, 
    modification_date DATE, 
    modification_time TIME WITHOUT TIME ZONE, 
    modification_user_id INTEGER, 
    PRIMARY KEY (user_id), 
    FOREIGN KEY(user_id) REFERENCES users (user_id) ON DELETE CASCADE, 
    FOREIGN KEY(creation_user_id) REFERENCES users (user_id), 
    FOREIGN KEY(modification_user_id) REFERENCES users (user_id)
);

UPDATE alembic_version SET version_num='0007_user_preferences' WHERE alembic_version.version_num = '0006_retire_profiles';

-- Running upgrade 0007_user_preferences -> 0008_settings

ALTER TABLE users ADD COLUMN user_code VARCHAR(9);

ALTER TABLE users ADD COLUMN display_name VARCHAR(60);

ALTER TABLE users ALTER COLUMN user_code SET NOT NULL;

ALTER TABLE users ADD CONSTRAINT uq_users_user_code UNIQUE (user_code);

ALTER TABLE user_preferences ADD COLUMN theme VARCHAR(8) DEFAULT 'system' NOT NULL;

ALTER TABLE user_preferences ADD COLUMN accent VARCHAR(10) DEFAULT 'indigo' NOT NULL;

ALTER TABLE user_preferences ADD COLUMN start_page VARCHAR(16) DEFAULT 'home' NOT NULL;

ALTER TABLE user_preferences ADD COLUMN private_mode BOOLEAN DEFAULT false NOT NULL;

ALTER TABLE user_preferences ADD COLUMN avatar_preset VARCHAR(16);

ALTER TABLE user_preferences ADD COLUMN avatar_image BYTEA;

ALTER TABLE user_preferences ADD COLUMN avatar_mime VARCHAR(16);

ALTER TABLE refresh_tokens ADD COLUMN user_agent VARCHAR(256);

ALTER TABLE refresh_tokens ADD COLUMN client_ip VARCHAR(45);

UPDATE alembic_version SET version_num='0008_settings' WHERE alembic_version.version_num = '0007_user_preferences';

-- Running upgrade 0008_settings -> 0009_user_admin

ALTER TABLE users ADD COLUMN deactivated_at TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE users ADD COLUMN deactivation_reason VARCHAR(500);

ALTER TABLE audit_log ADD COLUMN action VARCHAR(32);

ALTER TABLE audit_log ADD COLUMN target_user_id INTEGER;

ALTER TABLE audit_log ADD COLUMN detail VARCHAR(64);

ALTER TABLE audit_log ADD CONSTRAINT fk_audit_log_target_user_id FOREIGN KEY(target_user_id) REFERENCES users (user_id);

CREATE INDEX idx_audit_log_date ON audit_log (operation_date, operation_time);

UPDATE audit_log SET action = CASE operation WHEN 'INSERT' THEN 'credential.create' WHEN 'UPDATE' THEN 'credential.edit' WHEN 'DELETE' THEN 'credential.delete' ELSE 'credential.reveal' END;

UPDATE alembic_version SET version_num='0009_user_admin' WHERE alembic_version.version_num = '0008_settings';

-- Running upgrade 0009_user_admin -> 0010_lockout_settings

ALTER TABLE users ADD COLUMN failed_attempts SMALLINT DEFAULT '0' NOT NULL;

ALTER TABLE users ADD COLUMN locked_at TIMESTAMP WITHOUT TIME ZONE;

CREATE TABLE account_tokens (
    account_token_id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    purpose VARCHAR(16) NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    used_at TIMESTAMP WITHOUT TIME ZONE, 
    creation_date DATE NOT NULL, 
    creation_time TIME WITHOUT TIME ZONE NOT NULL, 
    creation_user_id INTEGER, 
    modification_date DATE, 
    modification_time TIME WITHOUT TIME ZONE, 
    modification_user_id INTEGER, 
    PRIMARY KEY (account_token_id), 
    CONSTRAINT ck_account_tokens_purpose CHECK (purpose IN ('unlock', 'reset')), 
    FOREIGN KEY(user_id) REFERENCES users (user_id) ON DELETE CASCADE, 
    UNIQUE (token_hash), 
    FOREIGN KEY(creation_user_id) REFERENCES users (user_id), 
    FOREIGN KEY(modification_user_id) REFERENCES users (user_id)
);

CREATE INDEX idx_account_tokens_user_id ON account_tokens (user_id);

CREATE TABLE system_settings (
    key VARCHAR(64) NOT NULL, 
    value VARCHAR(2000) NOT NULL, 
    creation_date DATE NOT NULL, 
    creation_time TIME WITHOUT TIME ZONE NOT NULL, 
    creation_user_id INTEGER, 
    modification_date DATE, 
    modification_time TIME WITHOUT TIME ZONE, 
    modification_user_id INTEGER, 
    PRIMARY KEY (key), 
    FOREIGN KEY(creation_user_id) REFERENCES users (user_id), 
    FOREIGN KEY(modification_user_id) REFERENCES users (user_id)
);

UPDATE alembic_version SET version_num='0010_lockout_settings' WHERE alembic_version.version_num = '0009_user_admin';

-- Running upgrade 0010_lockout_settings -> 0011_two_factor

ALTER TABLE users ADD COLUMN totp_secret BYTEA;

ALTER TABLE users ADD COLUMN totp_pending_secret BYTEA;

ALTER TABLE users ADD COLUMN totp_enabled_at TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE users ADD COLUMN totp_last_step INTEGER;

CREATE TABLE recovery_codes (
    recovery_code_id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    code_hash VARCHAR(64) NOT NULL, 
    used_at TIMESTAMP WITHOUT TIME ZONE, 
    creation_date DATE NOT NULL, 
    creation_time TIME WITHOUT TIME ZONE NOT NULL, 
    creation_user_id INTEGER, 
    modification_date DATE, 
    modification_time TIME WITHOUT TIME ZONE, 
    modification_user_id INTEGER, 
    PRIMARY KEY (recovery_code_id), 
    FOREIGN KEY(user_id) REFERENCES users (user_id) ON DELETE CASCADE, 
    FOREIGN KEY(creation_user_id) REFERENCES users (user_id), 
    FOREIGN KEY(modification_user_id) REFERENCES users (user_id)
);

CREATE INDEX idx_recovery_codes_user_id ON recovery_codes (user_id);

UPDATE alembic_version SET version_num='0011_two_factor' WHERE alembic_version.version_num = '0010_lockout_settings';

-- Running upgrade 0011_two_factor -> 0012_session_limits

ALTER TABLE refresh_tokens ADD COLUMN session_expires_at TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE refresh_tokens ADD COLUMN last_activity_at TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE refresh_tokens ADD COLUMN reauth_at TIMESTAMP WITHOUT TIME ZONE;

UPDATE alembic_version SET version_num='0012_session_limits' WHERE alembic_version.version_num = '0011_two_factor';

-- Running upgrade 0012_session_limits -> 0013_account_deletion

ALTER TABLE users ADD COLUMN deleted_at TIMESTAMP WITHOUT TIME ZONE;

UPDATE alembic_version SET version_num='0013_account_deletion' WHERE alembic_version.version_num = '0012_session_limits';

-- Running upgrade 0013_account_deletion -> 0014_trusted_devices

CREATE TABLE trusted_devices (
    trusted_device_id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    user_agent VARCHAR(256), 
    trusted_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    last_used_at TIMESTAMP WITHOUT TIME ZONE, 
    creation_date DATE NOT NULL, 
    creation_time TIME WITHOUT TIME ZONE NOT NULL, 
    creation_user_id INTEGER, 
    modification_date DATE, 
    modification_time TIME WITHOUT TIME ZONE, 
    modification_user_id INTEGER, 
    PRIMARY KEY (trusted_device_id), 
    FOREIGN KEY(user_id) REFERENCES users (user_id) ON DELETE CASCADE, 
    UNIQUE (token_hash), 
    FOREIGN KEY(creation_user_id) REFERENCES users (user_id), 
    FOREIGN KEY(modification_user_id) REFERENCES users (user_id)
);

CREATE INDEX idx_trusted_devices_user_id ON trusted_devices (user_id);

UPDATE alembic_version SET version_num='0014_trusted_devices' WHERE alembic_version.version_num = '0013_account_deletion';

COMMIT;


-- =============================================================
-- Application database role (Requirement 9.9) — run as superuser
-- after the tables exist. Replace the password before use.
-- =============================================================
CREATE ROLE app_user LOGIN PASSWORD 'change-me';
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
-- No SUPERUSER, no schema ownership.
