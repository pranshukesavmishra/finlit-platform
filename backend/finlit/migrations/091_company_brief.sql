-- Company brief (docs/COMPANY-BRIEF.md): the About section of every company page, written overnight from the company's own filings and published only after a person reviews it.
--
-- company_briefs         one row per company: the brief JSON (the shape of finlit_technicals' reliance_brief.json), its status and the checks that were run on it.
--   status       draft (written, waiting for a person) | reviewed (read, not yet shown) | published (shown on the company page) | rejected (a person said no; not rewritten until new filings arrive)
--   brief        the JSON the page draws (about, key_figures, group, segments, mix, recent, gaps, docs).
--   as_of        the date of the newest filing the brief was written from.
--   checks       the citation check: totals, failed citations (path, document, page, missing strings, where they are instead), and the same per part.
--   problems     validate() problems (blocking) and flags (for the reviewer, never blocking), recorded when the brief was written.
--   parts_written which parts the last run (re)wrote; written_at / written_by (model name) / prompt_version say how.
--   published / published_checks / published_at  the copy a person approved: the ONLY thing the company page ever shows. A rewrite lands in `brief` as a new draft and the
--                published copy stays up until the draft is approved, so a nightly rewrite never blanks a page.
--   reviewed_by / reviewed_at, review_note   the person who approved or rejected, and why.
-- company_brief_sources  one row per company: the annual report's address (not in the exchanges' feed; set by an administrator) and why a company has no brief.
-- company_brief_runs     one line per nightly run (counts and the reason it stopped), shown in the Console.
CREATE TABLE IF NOT EXISTS company_briefs (
    symbol         text        PRIMARY KEY,
    status         text        NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'reviewed', 'published', 'rejected')),
    brief          jsonb       NOT NULL,
    as_of          date,
    checks         jsonb       NOT NULL DEFAULT '{}'::jsonb,
    problems       jsonb       NOT NULL DEFAULT '[]'::jsonb,
    flags          jsonb       NOT NULL DEFAULT '[]'::jsonb,
    parts_written  text[]      NOT NULL DEFAULT '{}',
    written_at     timestamptz NOT NULL DEFAULT now(),
    written_by     text,
    prompt_version text,
    published      jsonb,
    published_checks jsonb,
    published_at   timestamptz,
    reviewed_by    text,
    reviewed_at    timestamptz,
    review_note    text,
    rewrite_asked  boolean     NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS company_briefs_status_idx ON company_briefs (status, written_at DESC);

CREATE TABLE IF NOT EXISTS company_brief_sources (
    symbol            text        PRIMARY KEY,
    annual_report_url text,
    set_by            text,
    set_at            timestamptz,
    last_state        text,
    last_reason       text,
    last_tried_at     timestamptz,
    attempts          smallint    NOT NULL DEFAULT 0,
    last_docs         text
);

CREATE TABLE IF NOT EXISTS company_brief_runs (
    id          bigserial   PRIMARY KEY,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status      text        NOT NULL,
    detail      jsonb       NOT NULL DEFAULT '{}'::jsonb
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON company_briefs, company_brief_sources TO finlit_api;
        GRANT SELECT ON company_brief_runs TO finlit_api;
    END IF;
END
$$;
