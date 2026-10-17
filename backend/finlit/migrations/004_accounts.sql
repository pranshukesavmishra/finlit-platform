-- Accounts, sessions and per-user state. Passwords are argon2id hashes; session and email tokens are stored only as SHA-256 hashes.
CREATE TABLE IF NOT EXISTS users (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email               text        NOT NULL,
    name                text,
    password_hash       text        NOT NULL,
    role                text        NOT NULL DEFAULT 'investor' CHECK (role IN ('investor', 'admin')),
    plan                text        NOT NULL DEFAULT 'basic'    CHECK (plan IN ('basic', 'bronze', 'gold')),
    plan_until          timestamptz,
    status              text        NOT NULL DEFAULT 'active'   CHECK (status IN ('active', 'disabled')),
    email_verified_at   timestamptz,
    totp_secret_enc     text,
    totp_enabled_at     timestamptz,
    totp_last_step      bigint      NOT NULL DEFAULT 0,
    failed_logins       integer     NOT NULL DEFAULT 0,
    locked_until        timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    last_login_at       timestamptz,
    password_changed_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS users_email_uq ON users (lower(email));

CREATE TABLE IF NOT EXISTS sessions (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash   text        NOT NULL UNIQUE,
    csrf         text        NOT NULL,
    mfa_ok       boolean     NOT NULL DEFAULT false,
    created_at   timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    expires_at   timestamptz NOT NULL,
    ip           text,
    user_agent   text
);
CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions (user_id);

CREATE TABLE IF NOT EXISTS email_tokens (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind       text        NOT NULL CHECK (kind IN ('verify', 'reset')),
    token_hash text        NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    used_at    timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS email_tokens_user_idx ON email_tokens (user_id, kind);

CREATE TABLE IF NOT EXISTS audit_events (
    id       bigserial PRIMARY KEY,
    at       timestamptz NOT NULL DEFAULT now(),
    actor_id uuid,
    action   text        NOT NULL,
    target   text,
    ip       text,
    meta     jsonb       NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS audit_at_idx ON audit_events (at DESC);

-- Watchlists, saved screens and appearance/dashboard preferences travel with the account (and later, the mobile app).
CREATE TABLE IF NOT EXISTS user_state (
    user_id    uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    watchlist  jsonb       NOT NULL DEFAULT '{}'::jsonb,
    screens    jsonb       NOT NULL DEFAULT '[]'::jsonb,
    prefs      jsonb       NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS plan_requests (
    id          bigserial PRIMARY KEY,
    user_id     uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan        text        NOT NULL CHECK (plan IN ('bronze', 'gold')),
    note        text,
    status      text        NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'granted', 'declined')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz
);

-- Development mail sink (ConsoleMailer). Production sends through the mail provider and never writes here.
CREATE TABLE IF NOT EXISTS outbox (
    id       bigserial PRIMARY KEY,
    at       timestamptz NOT NULL DEFAULT now(),
    to_email text        NOT NULL,
    subject  text        NOT NULL,
    body     text        NOT NULL
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON users, sessions, email_tokens, user_state TO finlit_api;
        GRANT SELECT, INSERT, UPDATE ON plan_requests TO finlit_api;
        GRANT SELECT, INSERT ON audit_events, outbox TO finlit_api;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO finlit_api;
    END IF;
END
$$;
