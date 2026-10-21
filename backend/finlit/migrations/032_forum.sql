-- Discussion forum (information and opinion only; see finlit/forum.py and finlit/forum_rules.py).
-- A member picks a public handle once (never the email or the account name); every post belongs to one company.
CREATE TABLE IF NOT EXISTS forum_profiles (
    user_id        uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    handle         text        NOT NULL,
    accepted_at    timestamptz NOT NULL DEFAULT now(),   -- when they accepted the community guidelines
    banned_until   timestamptz,                          -- a moderator stopped them posting until then
    banned_reason  text,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS forum_profiles_handle_uq ON forum_profiles (lower(handle));

-- One table for discussion starters (thread_id IS NULL, has a title and a company) and replies (thread_id points at the starter).
-- status: visible | held (waiting for a moderator: keyword flag or first links) | hidden (enough member reports) | deleted (by the author) | removed (by a moderator).
-- Nothing is ever physically deleted by members: the row stays for the moderation trail, the text is simply no longer served.
CREATE TABLE IF NOT EXISTS forum_posts (
    id               bigserial PRIMARY KEY,
    thread_id        bigint REFERENCES forum_posts(id) ON DELETE CASCADE,
    symbol           text        NOT NULL REFERENCES companies(symbol) ON DELETE CASCADE,
    user_id          uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title            text,
    body             text        NOT NULL,
    content_hash     text        NOT NULL,                -- of the normalised text, for the duplicate check
    status           text        NOT NULL DEFAULT 'visible' CHECK (status IN ('visible', 'held', 'hidden', 'deleted', 'removed')),
    flag_reasons     text[]      NOT NULL DEFAULT '{}',   -- why a post was held, in plain words for the moderator
    upvotes          integer     NOT NULL DEFAULT 0,
    created_at       timestamptz NOT NULL DEFAULT now(),
    edited_at        timestamptz,
    last_activity_at timestamptz NOT NULL DEFAULT now(),  -- starters only: moves when a visible reply arrives
    moderated_by     uuid REFERENCES users(id) ON DELETE SET NULL,
    moderated_at     timestamptz,
    moderation_note  text,
    CONSTRAINT forum_posts_kind CHECK ((thread_id IS NULL AND title IS NOT NULL) OR (thread_id IS NOT NULL AND title IS NULL))
);
CREATE INDEX IF NOT EXISTS forum_posts_board_idx   ON forum_posts (last_activity_at DESC) WHERE thread_id IS NULL AND status = 'visible';
CREATE INDEX IF NOT EXISTS forum_posts_company_idx ON forum_posts (symbol, last_activity_at DESC) WHERE thread_id IS NULL AND status = 'visible';
CREATE INDEX IF NOT EXISTS forum_posts_top_idx     ON forum_posts (upvotes DESC, created_at DESC) WHERE thread_id IS NULL AND status = 'visible';
CREATE INDEX IF NOT EXISTS forum_posts_replies_idx ON forum_posts (thread_id, created_at) WHERE thread_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS forum_posts_user_idx    ON forum_posts (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS forum_posts_hash_idx    ON forum_posts (content_hash, created_at DESC);
CREATE INDEX IF NOT EXISTS forum_posts_queue_idx   ON forum_posts (created_at) WHERE status IN ('held', 'hidden');

CREATE TABLE IF NOT EXISTS forum_votes (
    post_id    bigint      NOT NULL REFERENCES forum_posts(id) ON DELETE CASCADE,
    user_id    uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (post_id, user_id)
);
