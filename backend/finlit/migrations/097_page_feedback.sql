-- "Raise a Query" (a question, an issue or a clarification about one page) and "Share Feedback" (a rating, a suggestion or a UI/UX report about one page).
-- Every row is tagged with the page it was sent from, so the team knows which feature it is about. Queries and feedback are kept apart by `kind`.
CREATE TABLE IF NOT EXISTS page_feedback (
    id          bigserial PRIMARY KEY,
    kind        text        NOT NULL CHECK (kind IN ('query', 'feedback')),
    page_path   text        NOT NULL,                 -- "/stocks/RELIANCE" (address only: no query string, no fragment)
    page_name   text        NOT NULL,                 -- "Company report" as the page names itself
    context     jsonb       NOT NULL DEFAULT '{}',    -- a few short facts about the page (company symbol, section, screen size); never free text from the member
    category    text        NOT NULL DEFAULT 'other', -- query: question | issue | clarification; feedback: suggestion | ui_ux | praise | other
    rating      smallint    CHECK (rating BETWEEN 1 AND 5),
    message     text        NOT NULL DEFAULT '',
    email       text,                                 -- only for visitors who are not signed in (a member is reached through the account)
    user_id     uuid        REFERENCES users(id) ON DELETE SET NULL,
    plan        text,                                 -- the plan the member held when writing
    status      text        NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'read', 'resolved')),
    note        text,                                 -- the team's own note
    handled_by  uuid        REFERENCES users(id) ON DELETE SET NULL,
    handled_at  timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT page_feedback_has_content CHECK (message <> '' OR rating IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS page_feedback_status_idx ON page_feedback (status, created_at DESC);
CREATE INDEX IF NOT EXISTS page_feedback_page_idx   ON page_feedback (page_path, created_at DESC);
CREATE INDEX IF NOT EXISTS page_feedback_user_idx   ON page_feedback (user_id, created_at DESC);
