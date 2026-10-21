-- Graph Studio: a member's named chart layouts (which companies and measures sit in which cell, the chart types and the time range).
-- The plan limits (cells, companies, series, chart types, number of views) are enforced by the API when a view is saved.
CREATE TABLE IF NOT EXISTS graph_views (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       text        NOT NULL,
    config     jsonb       NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, name)
);
CREATE INDEX IF NOT EXISTS graph_views_user_idx ON graph_views (user_id, updated_at DESC);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON graph_views TO finlit_api;
    END IF;
END
$$;
