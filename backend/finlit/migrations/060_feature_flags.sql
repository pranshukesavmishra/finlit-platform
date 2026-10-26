-- Switches an administrator turns on without a deploy. A flag that is off shows its feature to administrators only.
CREATE TABLE IF NOT EXISTS feature_flags (
    name        text PRIMARY KEY,
    enabled     boolean NOT NULL DEFAULT false,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    updated_by  text
);
-- Leader / In line / Laggard: administrators first, everyone once the first weekly runs have been checked.
INSERT INTO feature_flags (name, enabled) VALUES ('leadership', false) ON CONFLICT (name) DO NOTHING;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE ON feature_flags TO finlit_api;
    END IF;
END
$$;
