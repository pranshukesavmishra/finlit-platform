-- Company brief, run end to end without manual work (docs/COMPANY-BRIEF.md).
--   company_brief_sources.annual_report_url stays as the administrator's OVERRIDE. The address found by the nightly lookup is kept beside it:
--     ar_url / ar_year (the financial year the report covers, e.g. 2025 for FY2024-25) / ar_source (nse | bse) / ar_found_at / ar_checked_at
--     ar_state  found | none (the listings hold no annual report) | blocked (the exchange refused us) | error (it did not answer); blocked and error are tried again soon.
--   company_briefs.publish_mode  person (an administrator approved it) | auto (it passed every automatic check; no human read it).
--   company_brief_settings       auto_publish ('on' unless an administrator turns it off), max_writes_per_night; every change is in the audit log.
ALTER TABLE company_brief_sources
    ADD COLUMN IF NOT EXISTS ar_url        text,
    ADD COLUMN IF NOT EXISTS ar_year       smallint,
    ADD COLUMN IF NOT EXISTS ar_source     text,
    ADD COLUMN IF NOT EXISTS ar_found_at   timestamptz,
    ADD COLUMN IF NOT EXISTS ar_checked_at timestamptz,
    ADD COLUMN IF NOT EXISTS ar_state      text,
    ADD COLUMN IF NOT EXISTS ar_detail     text;
ALTER TABLE company_briefs ADD COLUMN IF NOT EXISTS publish_mode text CHECK (publish_mode IN ('person', 'auto'));

CREATE TABLE IF NOT EXISTS company_brief_settings (
    key        text        PRIMARY KEY,
    value      text        NOT NULL,
    updated_by text,
    updated_at timestamptz NOT NULL DEFAULT now()
);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE ON company_brief_settings TO finlit_api;
    END IF;
END
$$;
