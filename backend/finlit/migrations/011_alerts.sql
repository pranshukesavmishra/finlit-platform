-- Member alerts and the in-app notification centre.
-- An alert watches one company (or a news keyword) and fires when its condition turns true; each firing becomes a notification row
-- (always) and, if the member chose them, an email and a browser notification.
CREATE TABLE IF NOT EXISTS alerts (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol         text        NOT NULL,
    metric         text        NOT NULL,
    op             text        NOT NULL CHECK (op IN ('above', 'below', 'event')),
    value          numeric(18,4),
    keyword        text,
    channels       text[]      NOT NULL DEFAULT '{app}',
    repeat         text        NOT NULL DEFAULT 'once' CHECK (repeat IN ('once', 'every')),
    status         text        NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'done')),
    note           text,
    met            boolean,
    last_value     numeric(18,4),
    last_checked   timestamptz,
    last_fired_at  timestamptz,
    fired_count    integer     NOT NULL DEFAULT 0,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS alerts_user_idx ON alerts (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS alerts_active_idx ON alerts (status, metric) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS notifications (
    id         bigserial   PRIMARY KEY,
    user_id    uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    alert_id   uuid        REFERENCES alerts(id) ON DELETE SET NULL,
    symbol     text,
    kind       text        NOT NULL DEFAULT 'alert',
    title      text        NOT NULL,
    body       text        NOT NULL DEFAULT '',
    link       text,
    push       boolean     NOT NULL DEFAULT false,
    read_at    timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS notifications_user_idx ON notifications (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS notifications_unread_idx ON notifications (user_id) WHERE read_at IS NULL;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON alerts, notifications TO finlit_api;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO finlit_api;
    END IF;
END
$$;
