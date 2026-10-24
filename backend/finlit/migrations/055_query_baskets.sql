-- Query builder baskets (finlit/screener/qapi.py): a member's named queries, written in the query language (finlit/screener/ql.py).
-- Limits per plan are in auth/entitlements.py (LIMITS["baskets"]). A name is unique per member, ignoring case.
--
-- query       the query text as the member wrote it (at most 2,000 characters; it is parsed again on every use, never trusted)
-- columns     extra result columns (metric keys) the member added beyond the ones the query uses
-- sort        {"key": ..., "dir": "asc"|"desc"} or null
-- recent      only companies that have reported the latest quarter
-- last_count  how many companies matched when last counted (shown while a fresh count is not ready)
CREATE TABLE IF NOT EXISTS query_baskets (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       text        NOT NULL,
    query      text        NOT NULL,
    note       text,
    columns    jsonb       NOT NULL DEFAULT '[]'::jsonb,
    sort       jsonb,
    recent     boolean     NOT NULL DEFAULT false,
    last_count integer,
    counted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS query_baskets_name_idx ON query_baskets (user_id, lower(name));
CREATE INDEX IF NOT EXISTS query_baskets_user_idx ON query_baskets (user_id, updated_at DESC);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON query_baskets TO finlit_api;
    END IF;
END
$$;
