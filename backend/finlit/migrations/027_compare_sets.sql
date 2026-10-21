-- Named sets of measures a member keeps for the custom comparison on the Compare page. One row per member; the list is validated by the API.
CREATE TABLE IF NOT EXISTS compare_sets (
    user_id    uuid        PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    sets       jsonb       NOT NULL DEFAULT '[]'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON compare_sets TO finlit_api;
    END IF;
END
$$;
