-- Built-in alerts (no rule to set up): one row per member, company, kind and quarter, so each is sent once.
CREATE TABLE IF NOT EXISTS auto_alert_sent (
    user_id uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol  text        NOT NULL,
    kind    text        NOT NULL,
    period  text        NOT NULL,
    sent_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, symbol, kind, period)
);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON auto_alert_sent TO finlit_api;
    END IF;
END
$$;
