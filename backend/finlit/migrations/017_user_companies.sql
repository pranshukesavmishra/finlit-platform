-- The companies each member has opened: they are kept stored and refreshed for as long as the member keeps using them, so a company outside the
-- always-loaded set takes its few seconds to build once and then opens instantly for that member from then on.
CREATE TABLE IF NOT EXISTS user_companies (
    user_id      uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol       text        NOT NULL,
    first_opened timestamptz NOT NULL DEFAULT now(),
    last_opened  timestamptz NOT NULL DEFAULT now(),
    opens        integer     NOT NULL DEFAULT 1,
    PRIMARY KEY (user_id, symbol)
);
CREATE INDEX IF NOT EXISTS user_companies_symbol_idx ON user_companies (symbol, last_opened DESC);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON user_companies TO finlit_api;
    END IF;
END
$$;
