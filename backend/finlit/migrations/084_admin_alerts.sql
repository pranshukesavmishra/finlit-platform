-- One OPEN admin alert per problem key (for example 'failing:facts', 'stale:results'): the notification bell gets one notification when the problem starts,
-- another only if it changes materially or as a single reminder after 24 hours, and a short 'resolved' one when it clears (finlit/jobs/alerts.py).
CREATE TABLE IF NOT EXISTS admin_alerts (
    key          text        PRIMARY KEY,
    subject      text        NOT NULL,
    body         text        NOT NULL DEFAULT '',
    opened_at    timestamptz NOT NULL DEFAULT now(),
    last_sent_at timestamptz NOT NULL DEFAULT now(),
    sent_count   integer     NOT NULL DEFAULT 1,
    resolved_at  timestamptz
);

-- Collapse the duplicates the old six-hourly repeat left in the bell: of the unread system notifications with the same title for the same person, keep the newest.
DELETE FROM notifications n USING notifications m
 WHERE n.kind = 'system' AND m.kind = 'system' AND n.user_id = m.user_id AND n.title = m.title
   AND n.read_at IS NULL AND m.read_at IS NULL AND n.id < m.id;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT ON admin_alerts TO finlit_api;
    END IF;
END $$;
