-- Remembers which side of its target price each watched stock was on, so an email goes out only when the price crosses it.
CREATE TABLE IF NOT EXISTS alert_state (
    user_id       uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol        text        NOT NULL,
    target        numeric(14,2) NOT NULL,
    side          smallint    NOT NULL,
    alerted_at    timestamptz,
    PRIMARY KEY (user_id, symbol)
);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON alert_state TO finlit_api;
    END IF;
END
$$;
