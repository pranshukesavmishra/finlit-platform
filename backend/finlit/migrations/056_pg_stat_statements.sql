-- Query statistics for finding what reads the most rows (docs/NEON-EGRESS.md, GET /api/admin/db-usage). Never fails the migration:
-- a host without the extension or without the privilege to create it simply leaves the admin endpoint saying "not enabled".
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'pg_stat_statements not enabled: %', SQLERRM;
END
$$;
