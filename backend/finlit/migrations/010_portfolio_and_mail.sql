-- Holdings travel with the account like watchlists; the two tables remember what each email already told the member.
ALTER TABLE user_state ADD COLUMN IF NOT EXISTS portfolio jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS screen_state (
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    screen_name text NOT NULL,
    seen        text[] NOT NULL DEFAULT '{}',
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, screen_name)
);
CREATE TABLE IF NOT EXISTS digest_log (
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    week    date NOT NULL,
    sent_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, week)
);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON screen_state, digest_log TO finlit_api;
    END IF;
END
$$;
