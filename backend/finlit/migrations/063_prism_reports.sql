-- FinLit Prism (finlit/prism.py, docs/prism/CONTRACT.md): the newest report of the Gold plan's financial-health rating, one row per company
-- and statement basis. Written when a report is calculated, read by /api/prism/reports/latest and the stock page.
-- Only the reader view is kept here: the calculation trace and the model inputs stay in the signed snapshot, which lives in Redis for its
-- 30 minutes (for the PDF) and is never stored in the database.
CREATE TABLE IF NOT EXISTS prism_reports (
    symbol        text        NOT NULL,
    statement     text        NOT NULL CHECK (statement IN ('consolidated', 'standalone')),   -- the basis asked for (the report says which it used)
    id            text        NOT NULL,                  -- the calculation id (32 hex), also the PDF's
    report        jsonb       NOT NULL,                  -- what the browser receives, without "cached" and "pdfAvailableUntil"
    model_version text,
    final         double precision,                      -- 0 to 100; null when the company could not be rated
    label         text,                                  -- STRONG | HEALTHY | AVERAGE | WEAK | POOR | NOT RATED
    status        text,                                  -- RATED | PROVISIONAL | NOT RATED
    generated_at  timestamptz NOT NULL DEFAULT now(),    -- reused for 6 hours unless a member asks to recalculate
    pdf_until     timestamptz,                           -- when the signed snapshot in Redis expires (null: it could not be kept)
    PRIMARY KEY (symbol, statement)
);
CREATE INDEX IF NOT EXISTS prism_reports_id_idx ON prism_reports (id);
CREATE INDEX IF NOT EXISTS prism_reports_generated_idx ON prism_reports (generated_at DESC);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON prism_reports TO finlit_api;
    END IF;
END
$$;
