-- Least privilege: the public API process connects as a role that can read snapshots and add
-- to the ingest queue, nothing else. Even a full compromise of the API cannot alter or delete data.
-- Create the login user at deploy time (see deploy/README.md):
--   CREATE USER finlit_api_user PASSWORD '...' IN ROLE finlit_api;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        CREATE ROLE finlit_api NOLOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO finlit_api;
GRANT SELECT ON companies, snapshots, scores TO finlit_api;
GRANT SELECT, INSERT ON ingest_queue TO finlit_api;
