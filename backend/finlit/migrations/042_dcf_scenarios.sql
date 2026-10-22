-- DCF calculator (Gold): a member's named scenarios, the calculator's inputs as entered (see finlit/dcf.py), at most 50 per member.
CREATE TABLE IF NOT EXISTS dcf_scenarios (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       text        NOT NULL,
    symbol     text,
    inputs     jsonb       NOT NULL,
    note       text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, name)
);
CREATE INDEX IF NOT EXISTS dcf_scenarios_user_idx ON dcf_scenarios (user_id, updated_at DESC);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON dcf_scenarios TO finlit_api;
    END IF;
END
$$;
