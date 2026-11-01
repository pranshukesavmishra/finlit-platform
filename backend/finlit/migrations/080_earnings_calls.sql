-- Earnings-call questions and answers (finlit/earnings, docs/EARNINGS-CALLS.md).
--
-- earnings_calls         one row per company, fiscal year and quarter: where the transcript PDF came from and how far the nightly job got with it.
--                        fiscal_year is the year the fiscal year ENDS in (FY27 = 2027, April 2026 to March 2027, as in India).
--                        status: found (link known) | text_ok (text extracted, answers still to do) | answered | unreadable (a scan: no text) | failed.
-- earnings_call_text     the extracted transcript text, one page after another separated by a form feed. Kept so a new prompt version can be
--                        run without downloading the PDF again, and so every quote can be checked against the text it was taken from.
-- earnings_call_answers  one row per call and fixed question. `answer` is {covered: bool, sentences: [{text, quote, quote_ref, source}]}.
--                        Only rows with validated = true are ever shown: every quote was found in the transcript and no advice word is present.
-- earnings_call_usage    which calls a member opened in a month (the Gold allowance). The member is stored as a salted hash, never as an id or email.
CREATE TABLE IF NOT EXISTS earnings_calls (
    id                bigserial   PRIMARY KEY,
    symbol            text        NOT NULL,
    fiscal_year       smallint    NOT NULL,
    quarter           smallint    NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    call_date         date,
    filed_at          timestamptz,
    transcript_url    text,
    transcript_sha256 text,
    source            text        NOT NULL DEFAULT 'feed',
    text_chars        integer     NOT NULL DEFAULT 0,
    pages             integer     NOT NULL DEFAULT 0,
    status            text        NOT NULL DEFAULT 'found' CHECK (status IN ('found', 'text_ok', 'answered', 'unreadable', 'failed')),
    attempts          smallint    NOT NULL DEFAULT 0,
    note              text,
    fetched_at        timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (symbol, fiscal_year, quarter)
);
CREATE INDEX IF NOT EXISTS earnings_calls_symbol_idx ON earnings_calls (symbol, fiscal_year DESC, quarter DESC);
CREATE INDEX IF NOT EXISTS earnings_calls_status_idx ON earnings_calls (status, call_date DESC);

CREATE TABLE IF NOT EXISTS earnings_call_text (
    call_id bigint PRIMARY KEY REFERENCES earnings_calls(id) ON DELETE CASCADE,
    body    text   NOT NULL
);

CREATE TABLE IF NOT EXISTS earnings_call_answers (
    call_id        bigint      NOT NULL REFERENCES earnings_calls(id) ON DELETE CASCADE,
    question_id    text        NOT NULL,
    answer         jsonb       NOT NULL,
    model          text        NOT NULL,
    prompt_version text        NOT NULL,
    generated_at   timestamptz NOT NULL DEFAULT now(),
    validated      boolean     NOT NULL DEFAULT false,
    last_version   text        NOT NULL,              -- the prompt version of the latest attempt (a failed attempt under a new version does not remove a validated older answer)
    attempts       smallint    NOT NULL DEFAULT 1,     -- attempts under last_version
    reject_reason  text,
    PRIMARY KEY (call_id, question_id)
);

CREATE TABLE IF NOT EXISTS earnings_call_usage (
    user_hash text        NOT NULL,
    month     char(7)     NOT NULL,                 -- 2026-11
    call_id   bigint      NOT NULL REFERENCES earnings_calls(id) ON DELETE CASCADE,
    opened_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_hash, month, call_id)
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT ON earnings_calls, earnings_call_answers TO finlit_api;      -- the API reads; the worker writes (and reads the text)
        GRANT SELECT, INSERT ON earnings_call_usage TO finlit_api;
    END IF;
END $$;
