-- FinLit Prism: the model inputs of a company's last interactive calculation, packed (zlib + base64), so a repeat calculation within the day
-- needs no provider call. Reused for 24 hours at most (15 minutes for "Recalculate"); rows older than two days are deleted when a new one is
-- written, so the table holds only what members opened lately. The signed snapshot, the PDF and the stored report are elsewhere.
CREATE TABLE IF NOT EXISTS prism_inputs (
    symbol     text        NOT NULL,
    statement  text        NOT NULL CHECK (statement IN ('consolidated', 'standalone')),
    body       text        NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, statement)
);
CREATE INDEX IF NOT EXISTS prism_inputs_fetched_idx ON prism_inputs (fetched_at);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON prism_inputs TO finlit_api;
    END IF;
END
$$;
