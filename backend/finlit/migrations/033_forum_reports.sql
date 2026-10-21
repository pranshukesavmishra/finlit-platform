-- Member reports. One report per member per post; a post is hidden automatically once enough different members have reported it
-- and the report has not been answered (resolved_at IS NULL) by a moderator.
CREATE TABLE IF NOT EXISTS forum_reports (
    id          bigserial PRIMARY KEY,
    post_id     bigint      NOT NULL REFERENCES forum_posts(id) ON DELETE CASCADE,
    reporter_id uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reason      text        NOT NULL CHECK (reason IN ('advice', 'promotion', 'contact', 'abuse', 'spam', 'misleading', 'other')),
    note        text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    resolved_by uuid REFERENCES users(id) ON DELETE SET NULL,
    resolution  text CHECK (resolution IN ('upheld', 'dismissed')),
    UNIQUE (post_id, reporter_id)
);
CREATE INDEX IF NOT EXISTS forum_reports_open_idx ON forum_reports (post_id) WHERE resolved_at IS NULL;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON forum_profiles, forum_posts, forum_votes, forum_reports TO finlit_api;
        GRANT USAGE, SELECT ON SEQUENCE forum_posts_id_seq, forum_reports_id_seq TO finlit_api;
    END IF;
END
$$;
