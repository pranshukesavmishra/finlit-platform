-- Ownership insights (docs/OWNERSHIP.md): the output of finlit_technicals.ownership.analyse() for one company, stored whole so the company page
-- reads one row and never calls the slow premium endpoint.
--   body          the analyse() JSON (table, facts, cards, more, quiet_text, signals ...), what the page draws.
--   extra         the part of the pack that comes from the premium fundamentals call (structure: share count, pledge, lock-in, shareholders;
--                 holders: named holders of 1% or more). Kept so the body can be built again, with no call, when a newer filing arrives.
--   premium_state ok (extra is from the premium call) | missing (no premium data yet: the page shows the section without "Also from the filing").
--   premium_reason  why it is missing, in words the page can show.
--   premium_at / premium_tried_at  when the premium call last succeeded / was last attempted (a failed call is tried again after six hours).
--   (pages that were opened without the premium part are queued in Redis, `ownership:wanted`; the nightly job takes those first.)
-- Idempotent. The API role may read and add rows (the page builds a first row itself from the stored shareholding when none exists yet).
CREATE TABLE IF NOT EXISTS ownership_insights (
    symbol         text        NOT NULL,
    statement      text        NOT NULL DEFAULT 'consolidated',
    as_of          text,
    rules_version  text        NOT NULL,
    body           jsonb       NOT NULL,
    extra          jsonb,
    premium_state  text        NOT NULL DEFAULT 'missing' CHECK (premium_state IN ('ok', 'missing')),
    premium_reason text,
    premium_at     timestamptz,
    premium_tried_at timestamptz,
    built_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, statement)
);
CREATE INDEX IF NOT EXISTS ownership_insights_built_idx ON ownership_insights (built_at);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT ON ownership_insights TO finlit_api;
    END IF;
END $$;
